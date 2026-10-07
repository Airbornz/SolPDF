import os

import pymupdf as fitz
import pytest

from sol_pdf.document import PDFDocument, PDFError, PasswordRequired, parse_pages


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "source.pdf"
    with fitz.open() as doc:
        for name in ("First page", "Second page", "Third page"):
            page = doc.new_page()
            page.insert_text((72, 90), name, fontsize=18)
            page.insert_text((72, 130), "Untouched nearby text", fontsize=12)
        doc.save(path)
    return path


@pytest.fixture
def model(source):
    model = PDFDocument()
    model.open(source)
    yield model
    model.doc.close()


def text(model, page=0):
    return model.doc[page].get_text()


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_resize_cropped_rotated_page_preserves_content(model, tmp_path, rotation):
    page = model.doc[0]
    page.draw_rect(fitz.Rect(60, 70, 200, 150), fill=(.8, .4, .2), overlay=False)
    page.set_cropbox(fitz.Rect(30, 40, 550, 700))
    page.set_rotation(rotation)
    original = page.get_pixmap()
    width, height = page.rect.width, page.rect.height
    model.resize_page(0, width * 2, height * 2)
    result = model.doc[0]
    assert result.rotation == rotation
    assert result.rect.width == width * 2 and result.rect.height == height * 2
    rendered = result.get_pixmap(matrix=fitz.Matrix(.5, .5))
    assert rendered.samples == original.samples
    assert "First page" in result.get_text()
    assert len(result.get_drawings()) > 0
    path = tmp_path / "resized.pdf"
    model.save(path)
    with fitz.open(path) as saved:
        assert saved[0].get_pixmap(matrix=fitz.Matrix(.5, .5)).samples == original.samples
    model.undo()
    assert model.doc[0].rect.width == width
    model.redo()
    assert model.doc[0].rect.width == width * 2


def test_resize_original_size_links_and_atomic_failure(model):
    page = model.doc[0]
    page.insert_link({"kind": fitz.LINK_URI, "from": fitz.Rect(72, 150, 180, 180), "uri": "https://example.com"})
    model.doc.reload_page(page)
    before = model.spans(0)[0]
    model.resize_page(0, 700, 1000, scale_content=False)
    assert model.spans(0)[0].origin == before.origin
    assert model.spans(0)[0].size == before.size
    assert model.doc[0].get_links()[0]["from"] == fitz.Rect(72, 150, 180, 180)
    model.resize_page(0, 350, 500)
    assert model.doc[0].get_links()[0]["from"] == fitz.Rect(36, 75, 90, 90)
    model.doc[0].add_text_annot((30, 30), "Keep this note")
    pixels = model.doc[0].get_pixmap().samples
    revision = model.revision
    with pytest.raises(PDFError, match="annotations"):
        model.resize_page(0, 612, 792)
    assert model.revision == revision and model.doc[0].get_pixmap().samples == pixels
    with pytest.raises(PDFError):
        model.resize_page(0, float("nan"), 792)


def test_page_operations_and_saved_output(model, source, tmp_path):
    model.reorder([2, 0, 1])
    assert "Third page" in text(model)
    model.blank(0)
    assert model.count == 4 and not text(model, 1)
    model.duplicate(0)
    assert model.count == 5 and "Third page" in text(model, 1)
    model.delete([1, 2])
    model.import_pages(source, 0, [1, 0])
    assert [text(model, i).splitlines()[0] for i in range(model.count)] == [
        "Third page", "Second page", "First page", "First page", "Second page"]
    model.rotate([0, 1])
    assert model.doc[0].rotation == 90
    path = tmp_path / "result.pdf"
    model.save(path)
    assert not model.dirty
    with fitz.open(path) as result:
        assert result.page_count == 5
        assert result[0].rotation == 90
        assert "Third page" in result[0].get_text()


def test_replacement_removes_original_and_preserves_neighbors(model, tmp_path):
    span = model.spans(0)[0]
    model.replace_text(0, span, "New title")
    assert "First page" not in text(model)
    assert "New title" in text(model)
    assert "Untouched nearby text" in text(model)
    path = tmp_path / "edited.pdf"
    model.save(path)
    with fitz.open(path) as result:
        assert "First page" not in result[0].get_text()
        assert "New title" in result[0].get_text()


def test_empty_replacement_deletes_text(model):
    model.replace_text(0, model.spans(0)[0], "")
    assert "First page" not in text(model)
    assert "Untouched nearby text" in text(model)


def test_replacement_preserves_image_and_vector_background(model):
    page = model.doc[0]
    page.draw_rect(fitz.Rect(60, 60, 300, 145), fill=(.9, .9, .8), overlay=False)
    image = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 10, 10), False)
    image.clear_with(128)
    page.insert_image(fitz.Rect(60, 60, 300, 145), pixmap=image, overlay=False)
    model.replace_text(0, model.spans(0)[0], "New title")
    assert len(model.doc[0].get_images()) == 1
    assert len(model.doc[0].get_drawings()) > 0
    assert "Untouched nearby text" in text(model)


def test_failed_edits_are_atomic(model):
    before = model.doc[0].get_pixmap().samples
    with pytest.raises(PDFError, match="too wide"):
        model.replace_text(0, model.spans(0)[0], "A replacement far too long to fit on this page " * 4)
    assert model.doc[0].get_pixmap().samples == before
    assert not model.dirty
    with pytest.raises(RuntimeError):
        def fail(doc):
            doc.delete_page(0)
            raise RuntimeError("failed")
        model.change("Failure", fail)
    assert model.count == 3 and not model.dirty


def test_undo_redo_and_saved_revision(model, tmp_path):
    model.blank(0)
    model.save(tmp_path / "saved.pdf")
    assert not model.dirty
    model.rotate([0])
    assert model.dirty
    model.undo()
    assert not model.dirty
    model.undo()
    assert model.count == 3 and model.dirty
    model.redo()
    assert model.count == 4 and not model.dirty
    model.rotate([0])
    assert not model.redo_stack


def test_unicode_and_multiline_text(model):
    model.add_text(0, (72, 200), "Résumé\n中文 Ελληνικά", 12)
    assert "Résumé" in text(model)
    assert "中文" in text(model)
    assert "Ελληνικά" in text(model)


def test_bounds_and_last_page(model):
    with pytest.raises(PDFError):
        model.delete([0, 1, 2])
    with pytest.raises(PDFError):
        model.reorder([0, 0, 1])
    with pytest.raises(PDFError):
        model.add_text(0, (590, 90), "Outside the page", 18)
    assert model.count == 3 and not model.dirty


def test_page_ranges():
    assert parse_pages("1, 3-5, 3", 5) == [0, 2, 3, 4]
    for bad in ("", "0", "6", "5-2", "1-99999999999", "abc", "1,", "-1"):
        with pytest.raises(PDFError):
            parse_pages(bad, 5)


def test_password_and_unlocked_copy(tmp_path):
    original = tmp_path / "locked.pdf"
    with fitz.open() as doc:
        doc.new_page().insert_text((72, 90), "Secret content")
        doc.save(original, encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="owner",
            user_pw="reader", permissions=fitz.PDF_PERM_MODIFY)
    model = PDFDocument()
    with pytest.raises(PasswordRequired):
        model.open(original)
    model.open(original, "reader")
    with pytest.raises(PDFError, match="unlocked copy"):
        model.save()
    model.save(tmp_path / "unlocked.pdf")
    assert fitz.open(original).needs_pass
    assert not fitz.open(tmp_path / "unlocked.pdf").needs_pass


def test_extract(model, tmp_path):
    output = tmp_path / "extract.pdf"
    model.extract([2, 0], output)
    with fitz.open(output) as doc:
        assert len(doc) == 2
        assert "First page" in doc[0].get_text()
        assert "Third page" in doc[1].get_text()
    assert not model.dirty


def test_duplicate_last_page(model):
    model.duplicate(2)
    assert model.count == 4
    assert "Third page" in text(model, 3)


def test_duplicate_multiple_pages_is_one_undo(model):
    model.duplicate_pages([0, 2])
    assert [text(model, i).splitlines()[0] for i in range(model.count)] == [
        "First page", "First page", "Second page", "Third page", "Third page"]
    model.undo()
    assert model.count == 3


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
@pytest.mark.parametrize("horizontal", [True, False])
def test_flip_matches_visible_page_and_roundtrips(tmp_path, rotation, horizontal):
    path = tmp_path / "flip.pdf"
    with fitz.open() as doc:
        page = doc.new_page(width=140, height=180)
        page.draw_rect(fitz.Rect(15, 20, 52, 45), color=None, fill=(1, 0, 0))
        page.draw_rect(fitz.Rect(80, 110, 125, 150), color=None, fill=(0, 0, 1))
        page.insert_text((17, 80), "Mirror text", fontsize=10)
        page.set_cropbox(fitz.Rect(5, 7, 135, 170))
        page.set_rotation(rotation)
        doc.save(path)
    model = PDFDocument()
    model.open(path)
    original = model.doc[0].get_pixmap(alpha=False)
    model.flip([0], horizontal)
    flipped = model.doc[0].get_pixmap(alpha=False)
    assert flipped.width == original.width and flipped.height == original.height
    expected = bytearray(len(original.samples))
    pixels = original.samples
    for y in range(original.height):
        for x in range(original.width):
            old_x = original.width - x - 1 if horizontal else x
            old_y = y if horizontal else original.height - y - 1
            src = (old_y * original.width + old_x) * 3
            dest = (y * original.width + x) * 3
            expected[dest:dest + 3] = pixels[src:src + 3]
    # Font hinting can differ slightly after reflection; geometry must match.
    mean_error = sum(abs(a - b) for a, b in zip(flipped.samples, expected)) / len(expected)
    assert mean_error < 2
    assert "Mirror text" in model.doc[0].get_text()
    model.flip([0], horizontal)
    assert model.doc[0].get_pixmap(alpha=False).samples == original.samples
    model.flip([0], horizontal)
    output = tmp_path / "flipped.pdf"
    model.save(output)
    with fitz.open(output) as saved:
        assert saved[0].get_pixmap(alpha=False).samples == flipped.samples
    model.undo()
    assert model.doc[0].get_pixmap(alpha=False).samples == original.samples


def test_flip_preserves_hyperlinks_and_rejects_annotations(model):
    rect = fitz.Rect(72, 70, 180, 95)
    model.doc[0].insert_link({"kind": fitz.LINK_URI, "from": rect, "uri": "https://example.com"})
    width = model.doc[0].rect.width
    model.flip([0], True)
    link = model.doc[0].get_links()[0]
    assert link["uri"] == "https://example.com"
    assert abs(link["from"].x0 - (width - rect.x1)) < .01
    model.undo()
    model.doc[0].add_rect_annot(rect)
    revision = model.revision
    with pytest.raises(PDFError, match="annotations"):
        model.flip([0])
    assert model.revision == revision


def test_move_and_style_text_and_multiline_alignment(model):
    span = model.spans(0)[0]
    model.replace_text(0, span, "Moved title", fontname="hebi", origin=(100, 220))
    moved = next(s for s in model.spans(0) if s.text == "Moved title")
    assert moved.origin == (100, 220)
    assert "BoldOblique" in moved.font
    assert "First page" not in text(model)
    model.undo()
    assert "First page" in text(model)
    model.add_text(0, (100, 220), "Longer line\nA", size=12, line_spacing=2, align=1)
    added = {s.text: s for s in model.spans(0)}
    assert added["A"].origin[0] > added["Longer line"].origin[0]
    assert added["A"].origin[1] - added["Longer line"].origin[1] == 24


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_crop_uses_visible_margins_and_preserves_content(model, tmp_path, rotation):
    model.rotate([0], rotation)
    original = model.doc[0].rect
    model.crop(0, (10, 20, 30, 40))
    assert model.doc[0].rect.width == original.width - 40
    assert model.doc[0].rect.height == original.height - 60
    assert "First page" in text(model)
    path = tmp_path / "cropped.pdf"
    model.save(path)
    with fitz.open(path) as saved:
        assert saved[0].rect == model.doc[0].rect
    model.undo()
    assert model.doc[0].rect == original


def test_add_image_save_and_undo(model, tmp_path):
    image = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 40, 20), False)
    image.clear_with(80)
    path = tmp_path / "image.png"
    image.save(path)
    model.add_image(0, path, (72, 200), 120)
    assert len(model.doc[0].get_images()) == 1
    assert model.doc[0].get_image_rects(model.doc[0].get_images()[0][0])[0] == fitz.Rect(72, 200, 192, 260)
    pdf = tmp_path / "image.pdf"
    model.save(pdf)
    with fitz.open(pdf) as saved:
        assert len(saved[0].get_images()) == 1
    model.undo()
    assert not model.doc[0].get_images()
    with pytest.raises(PDFError, match="beyond"):
        model.add_image(0, path, (550, 200), 120)


def test_save_failure_keeps_original(model, source, monkeypatch):
    before = source.read_bytes()
    model.blank(0)
    def fail(*args):
        raise OSError("Disk write failed")
    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(OSError):
        model.save()
    assert source.read_bytes() == before
    assert model.dirty
    assert not list(source.parent.glob(".sol-*"))


def test_rotated_page_coordinates(model):
    model.rotate([0])
    span = model.spans(0)[0]
    point = fitz.Point(span.origin)
    rotated = point * model.doc[0].rotation_matrix
    restored = rotated * model.doc[0].derotation_matrix
    assert abs(restored.x - point.x) < .01
    model.replace_text(0, span, "New title")
    assert model.doc[0].rotation == 90 and "New title" in text(model)


def test_existing_redactions_not_silently_applied(model):
    model.doc[0].add_redact_annot(fitz.Rect(60, 110, 300, 145))
    with pytest.raises(PDFError, match="redaction"):
        model.replace_text(0, model.spans(0)[0], "New title")
    assert "Untouched nearby text" in text(model)
