"""PDF operations, independent of the desktop interface."""
from __future__ import annotations

import os
import math
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pymupdf as fitz


class PDFError(ValueError):
    pass


class PasswordRequired(PDFError):
    pass


@dataclass(frozen=True)
class TextSpan:
    text: str
    rect: tuple[float, float, float, float]
    origin: tuple[float, float]
    size: float
    font: str
    color: int
    direction: tuple[float, float]


@dataclass
class Snapshot:
    data: bytes
    revision: str
    label: str


class PDFDocument:
    MAX_HISTORY_BYTES = 128 * 1024 * 1024

    def __init__(self):
        self.doc = None
        self.path: Path | None = None
        self.revision = ""
        self.saved_revision = ""
        self.undo_stack: list[Snapshot] = []
        self.redo_stack: list[Snapshot] = []
        self.was_encrypted = False

    @property
    def count(self):
        return len(self.doc) if self.doc else 0

    @property
    def dirty(self):
        return self.doc is not None and self.revision != self.saved_revision

    def _install(self, doc, path=None, encrypted=False):
        if self.doc is not None:
            self.doc.close()
        self.doc = doc
        self.path = path
        self.was_encrypted = encrypted
        self.revision = uuid.uuid4().hex
        self.saved_revision = self.revision if path else ""
        self.undo_stack.clear()
        self.redo_stack.clear()

    def open(self, path, password=""):
        doc = fitz.open(stream=Path(path).read_bytes(), filetype="pdf")
        try:
            encrypted = doc.needs_pass
            if encrypted and not doc.authenticate(password):
                raise PasswordRequired("This PDF needs a valid password.")
            if not doc.is_pdf or len(doc) == 0:
                raise PDFError("Please choose a PDF with at least one page.")
            if encrypted and not (doc.permissions & fitz.PDF_PERM_MODIFY):
                raise PDFError("This password does not grant permission to modify the PDF.")
        except Exception:
            doc.close()
            raise
        self._install(doc, Path(path), encrypted)

    def new(self, width=612, height=792):
        doc = fitz.open()
        doc.new_page(width=width, height=height)
        self._install(doc)

    def _bytes(self):
        return self.doc.tobytes(garbage=3, deflate=True, encryption=fitz.PDF_ENCRYPT_NONE)

    def change(self, label: str, operation: Callable):
        if self.doc is None:
            raise PDFError("Open a PDF first.")
        before = Snapshot(self._bytes(), self.revision, label)
        # Work in a separate document: a failed edit never damages the live PDF.
        candidate = fitz.open(stream=before.data, filetype="pdf")
        try:
            operation(candidate)
            if len(candidate) < 1:
                raise PDFError("Keep at least one page in the document.")
        except Exception:
            candidate.close()
            raise
        self.doc.close()
        self.doc = candidate
        self.undo_stack.append(before)
        self.redo_stack.clear()
        self.revision = uuid.uuid4().hex
        while len(self.undo_stack) > 1 and (len(self.undo_stack) > 30 or
                sum(len(s.data) for s in self.undo_stack) > self.MAX_HISTORY_BYTES):
            self.undo_stack.pop(0)

    def undo(self):
        self._restore(self.undo_stack, self.redo_stack)

    def redo(self):
        self._restore(self.redo_stack, self.undo_stack)

    def _restore(self, source, destination):
        if not source:
            return
        state = source.pop()
        destination.append(Snapshot(self._bytes(), self.revision, state.label))
        self.doc.close()
        self.doc = fitz.open(stream=state.data, filetype="pdf")
        self.revision = state.revision

    def blank(self, after: int, width=None, height=None):
        rect = self.doc[after].rect
        self.change("Add blank page", lambda doc: doc.new_page(
            pno=after + 1, width=width or rect.width, height=height or rect.height))

    def delete(self, pages: list[int]):
        pages = sorted(set(pages))
        if len(pages) >= self.count:
            raise PDFError("Keep at least one page in the document.")
        self.change("Delete pages", lambda doc: doc.delete_pages(pages))

    def reorder(self, order: list[int]):
        if sorted(order) != list(range(self.count)):
            raise PDFError("The page order must contain every page exactly once.")
        if order != list(range(self.count)):
            self.change("Reorder pages", lambda doc: doc.select(order))

    def rotate(self, pages, degrees=90):
        def operation(doc):
            for index in pages:
                page = doc[index]
                page.set_rotation((page.rotation + degrees) % 360)
        self.change("Rotate pages", operation)

    def flip(self, pages, horizontal=True):
        selected = sorted(set(pages))
        if not selected or any(index < 0 or index >= self.count for index in selected):
            raise PDFError("Choose valid pages to flip.")
        def operation(doc):
            transforms = {}
            # Keep interactive annotations intact rather than flattening them.
            for index in selected:
                page = doc[index]
                if page.first_annot is not None or page.first_widget is not None:
                    raise PDFError("Flipping pages with annotations or form fields is not supported yet.")
                reflection = (fitz.Matrix(-1, 0, 0, 1, page.rect.width, 0) if horizontal else
                              fitz.Matrix(1, 0, 0, -1, 0, page.rect.height))
                transforms[index] = page.rotation_matrix * reflection * page.derotation_matrix
            links = [(index, page.get_links()) for index, page in enumerate(doc)]
            for index, reflection in transforms.items():
                page = doc[index]
                # Convert the visible-page reflection into PDF's coordinate system.
                rotation = page.rotation
                page.set_rotation(0)
                transform = page.transformation_matrix
                pdf_matrix = transform * reflection * ~transform
                page.set_rotation(rotation)
                page.wrap_contents()
                contents = page.read_contents()
                matrix = " ".join(f"{value:.9g}" for value in pdf_matrix)
                stream = b"q\n" + matrix.encode("ascii") + b" cm\n" + contents + b"\nQ\n"
                xref = doc.get_new_xref()
                doc.update_object(xref, "<<>>")
                doc.update_stream(xref, stream)
                page.set_contents(xref)
            # Move hyperlink hit areas and internal destinations with their content.
            for index, page_links in links:
                page = doc[index]
                for link in page_links:
                    changed = False
                    if index in transforms:
                        link["from"] = link["from"] * transforms[index]
                        changed = True
                    target = link.get("page", -1)
                    if link["kind"] == fitz.LINK_GOTO and target in transforms and isinstance(link.get("to"), fitz.Point):
                        link["to"] = link["to"] * transforms[target]
                        changed = True
                    if changed:
                        page.update_link(link)
        self.change("Flip horizontally" if horizontal else "Flip vertically", operation)

    def duplicate(self, index):
        self.duplicate_pages([index])

    def duplicate_pages(self, pages):
        selected = sorted(set(pages), reverse=True)
        if not selected or any(index < 0 or index >= self.count for index in selected):
            raise PDFError("Choose valid pages to duplicate.")
        def operation(doc):
            for index in selected:
                destination = index + 1 if index + 1 < len(doc) else -1
                doc.fullcopy_page(index, destination)
        self.change("Duplicate pages" if len(selected) > 1 else "Duplicate page", operation)

    def import_pages(self, path, after, pages=None, password=""):
        source = fitz.open(stream=Path(path).read_bytes(), filetype="pdf")
        try:
            if source.needs_pass and not source.authenticate(password):
                raise PasswordRequired("The imported PDF needs a valid password.")
            selected = list(range(len(source))) if pages is None else pages
            if not selected or any(i < 0 or i >= len(source) for i in selected):
                raise PDFError("Choose valid pages to import.")
            def operation(doc):
                for offset, index in enumerate(selected):
                    doc.insert_pdf(source, from_page=index, to_page=index,
                                   start_at=after + 1 + offset, final=offset == len(selected) - 1)
            self.change("Import pages", operation)
            return len(selected)
        finally:
            source.close()

    def extract(self, pages, path):
        output = fitz.open()
        try:
            for index in sorted(set(pages)):
                output.insert_pdf(self.doc, from_page=index, to_page=index)
            self._atomic_write(output, path)
        finally:
            output.close()

    def spans(self, index):
        result = []
        for block in self.doc[index].get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for span in line["spans"]:
                    if span["text"].strip():
                        result.append(TextSpan(span["text"], tuple(span["bbox"]),
                            tuple(span["origin"]), span["size"], span["font"],
                            span["color"], tuple(line["dir"])))
        return result

    @staticmethod
    def standard_font(original):
        name = original.lower()
        bold = "bold" in name
        italic = "italic" in name or "oblique" in name
        if "courier" in name or "mono" in name:
            return {(False, False): "cour", (True, False): "cobo",
                    (False, True): "coit", (True, True): "cobi"}[bold, italic]
        if "times" in name or "serif" in name:
            return {(False, False): "tiro", (True, False): "tibo",
                    (False, True): "tiit", (True, True): "tibi"}[bold, italic]
        return {(False, False): "helv", (True, False): "hebo",
                (False, True): "heit", (True, True): "hebi"}[bold, italic]

    @staticmethod
    def _font(text, name):
        font = fitz.Font(name)
        if any(not font.has_glyph(ord(char)) for char in text if not char.isspace()):
            font = fitz.Font("cjk")
            name = "sol-unicode"
        if any(not font.has_glyph(ord(char)) for char in text if not char.isspace()):
            raise PDFError("This text includes characters the available fonts cannot display.")
        return font, name

    @staticmethod
    def _insert(page, text, origin, fontsize, fontname, color):
        font, name = PDFDocument._font(text, fontname)
        if name == "sol-unicode":
            page.insert_font(fontname=name, fontbuffer=font.buffer)
        page.insert_text(origin, text, fontsize=fontsize, fontname=name, color=color)

    def replace_text(self, index, span: TextSpan, text, size=None, fontname=None, color=None, origin=None):
        if span.direction != (1.0, 0.0):
            raise PDFError("Editing mirrored, angled or vertical text is not supported yet.")
        if "\n" in text or "\r" in text:
            raise PDFError("Replace one text run at a time; use Add text for multiple lines.")
        size = size or span.size
        fontname = fontname or self.standard_font(span.font)
        color = color or tuple(((span.color >> shift) & 255) / 255 for shift in (16, 8, 0))
        font, _ = self._font(text, fontname)
        origin = origin or span.origin
        page = self.doc[index]
        neighbors = [other.rect[0] for other in self.spans(index) if other != span and
            other.rect[2] > origin[0] and abs(other.origin[1] - origin[1]) < size * .5]
        max_width = min(neighbors + [page.cropbox.width]) - origin[0] - 1
        if font.text_length(text, fontsize=size) > max_width:
            raise PDFError("The replacement is too wide. Shorten it or choose a smaller font size.")
        if (origin[0] < 0 or origin[1] - font.ascender * size < 0 or
                origin[1] - font.descender * size > page.cropbox.height):
            raise PDFError("This text would extend beyond the page.")
        def operation(doc):
            page = doc[index]
            # A narrow band through the glyphs avoids erasing neighboring lines.
            rect = fitz.Rect(span.rect[0], span.origin[1] - span.size * .65,
                             span.rect[2], span.origin[1] - span.size * .1)
            for annot in page.annots() or []:
                if annot.type[0] == fitz.PDF_ANNOT_REDACT:
                    raise PDFError("Apply or remove existing redaction annotations before editing text.")
            page.add_redact_annot(rect, fill=False, cross_out=False)
            page.apply_redactions(images=0, graphics=0, text=0)
            if text:
                self._insert(page, text, origin, size, fontname, color)
        self.change("Edit text", operation)

    def add_text(self, index, origin, text, size=12, fontname="helv", color=(0, 0, 0), line_spacing=1.2, align=0):
        if not text.strip():
            raise PDFError("Enter some text first.")
        font, _ = self._font(text, fontname)
        page = self.doc[index]
        lines = text.splitlines()
        widths = [font.text_length(line, fontsize=size) for line in lines]
        width = max(widths)
        if not .8 <= line_spacing <= 3 or align not in (0, 1, 2):
            raise PDFError("Choose valid line spacing and alignment.")
        x, y = origin
        if (x < 0 or y - font.ascender * size < 0 or
            x + width > page.cropbox.width or
            y + (len(lines) - 1) * size * line_spacing - font.descender * size > page.cropbox.height):
            raise PDFError("This text would extend beyond the page. Use a smaller size or another position.")
        def operation(doc):
            for number, line in enumerate(lines):
                offset = 0 if align == 0 else (width - widths[number]) * (.5 if align == 1 else 1)
                self._insert(doc[index], line, (x + offset, y + number * size * line_spacing), size, fontname, color)
        self.change("Add text", operation)

    def add_image(self, index, path, origin, width):
        data = Path(path).read_bytes()
        image = fitz.Pixmap(data)
        height = width * image.height / image.width
        x, y = origin
        page = self.doc[index]
        if width <= 0 or x < 0 or y < 0 or x + width > page.cropbox.width or y + height > page.cropbox.height:
            raise PDFError("The image would extend beyond the page. Adjust its position or width.")
        self.change("Add image", lambda doc: doc[index].insert_image(
            fitz.Rect(x, y, x + width, y + height), stream=data, overlay=True))

    def crop(self, index, margins):
        left, top, right, bottom = margins
        page = self.doc[index]
        if min(margins) < 0 or left + right > page.rect.width - 20 or top + bottom > page.rect.height - 20:
            raise PDFError("Keep at least 20 pt of page width and height.")
        visible = fitz.Rect(left, top, page.rect.width - right, page.rect.height - bottom)
        unrotated = visible * page.derotation_matrix
        box = page.cropbox
        cropped = fitz.Rect(box.x0 + unrotated.x0, box.y0 + unrotated.y0,
                            box.x0 + unrotated.x1, box.y0 + unrotated.y1)
        self.change("Crop page", lambda doc: doc[index].set_cropbox(cropped))

    def resize_page(self, index, width, height, scale_content=True):
        if not all(math.isfinite(value) and 20 <= value <= 14400 for value in (width, height)):
            raise PDFError("Choose page dimensions between 20 and 14,400 pt.")
        def operation(doc):
            page = doc[index]
            if page.first_annot is not None or page.first_widget is not None:
                raise PDFError("Resizing pages with annotations or form fields is not supported yet.")
            rotation = page.rotation
            old_width, old_height = page.rect.width, page.rect.height
            old_rotation = page.rotation_matrix
            links = [(number, item.get_links()) for number, item in enumerate(doc)]
            page.set_rotation(0)
            old_transform = page.transformation_matrix
            clip = page.rect * ~old_transform
            page.wrap_contents()
            contents = page.read_contents()
            scale = min(width / old_width, height / old_height) if scale_content else 1
            # Fit proportionally and center; keep original-size content at top left.
            dx, dy = ((width - old_width * scale) / 2, (height - old_height * scale) / 2) if scale_content else (0, 0)
            visible = fitz.Matrix(scale, 0, 0, scale, dx, dy)
            size = (height, width) if rotation in (90, 270) else (width, height)
            page.set_mediabox(fitz.Rect(0, 0, *size))
            new_transform = page.transformation_matrix
            page.set_rotation(rotation)
            unrotated = old_rotation * visible * page.derotation_matrix
            pdf_matrix = old_transform * unrotated * ~new_transform
            matrix = " ".join(f"{value:.9g}" for value in pdf_matrix)
            # Retain the old crop when changing the physical page boundary.
            rectangle = f"{clip.x0:.9g} {clip.y0:.9g} {clip.width:.9g} {clip.height:.9g} re W n\n"
            stream = b"q\n" + matrix.encode("ascii") + b" cm\n" + rectangle.encode("ascii") + contents + b"\nQ\n"
            xref = doc.get_new_xref()
            doc.update_object(xref, "<<>>")
            doc.update_stream(xref, stream)
            page.set_contents(xref)
            for number, page_links in links:
                for link in page_links:
                    changed = False
                    if number == index:
                        link["from"] = link["from"] * unrotated
                        changed = True
                    if link["kind"] == fitz.LINK_GOTO and link.get("page") == index and isinstance(link.get("to"), fitz.Point):
                        link["to"] = link["to"] * unrotated
                        changed = True
                    if changed:
                        doc[number].update_link(link)
        self.change("Resize page", operation)

    @staticmethod
    def _atomic_write(doc, path):
        path = Path(path)
        fd, temp = tempfile.mkstemp(prefix=".sol-", suffix=".pdf", dir=path.parent)
        os.close(fd)
        try:
            doc.save(temp, garbage=4, deflate=True, encryption=fitz.PDF_ENCRYPT_NONE)
            # Validate the complete output before replacing an existing file.
            with fitz.open(temp) as check:
                if check.page_count != doc.page_count:
                    raise PDFError("The saved PDF did not pass verification.")
            with open(temp, "rb") as saved:
                os.fsync(saved.fileno())
            os.replace(temp, path)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)

    def save(self, path=None):
        destination = Path(path) if path else self.path
        if destination is None:
            raise PDFError("Choose a location for the PDF.")
        if self.was_encrypted and self.path and destination.resolve() == self.path.resolve():
            raise PDFError("Use Save As to save an unlocked copy of this password-protected PDF.")
        self._atomic_write(self.doc, destination)
        self.path = destination
        self.was_encrypted = False
        self.saved_revision = self.revision


def parse_pages(text: str, count: int) -> list[int]:
    """Convert a human page range such as 1, 3-5 into unique zero-based indices."""
    result = []
    try:
        for part in text.split(","):
            bounds = [int(n.strip()) for n in part.strip().split("-")]
            if len(bounds) == 1:
                values = bounds
            elif len(bounds) == 2 and bounds[0] <= bounds[1]:
                if bounds[1] > count or bounds[0] < 1:
                    raise ValueError()
                values = range(bounds[0], bounds[1] + 1)
            else:
                raise ValueError()
            for value in values:
                if not 1 <= value <= count:
                    raise ValueError()
                if value - 1 not in result:
                    result.append(value - 1)
    except ValueError:
        raise PDFError(f"Enter pages from 1 to {count}, for example 1, 3-5.") from None
    return result
