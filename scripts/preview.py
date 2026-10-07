"""Generate a sample PDF and UI snapshots for visual verification."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path

import pymupdf as fitz
from PySide6.QtWidgets import QApplication
from sol_pdf.app import MainWindow, STYLE, sol_icon

root = Path(__file__).resolve().parents[1]
(root / "tmp").mkdir(exist_ok=True)
(root / "examples").mkdir(exist_ok=True)
(root / "assets").mkdir(exist_ok=True)
path = root / "examples" / "Welcome to Sol PDF.pdf"
with fitz.open() as doc:
    for number, title in enumerate(["A brighter way to work with PDFs.", "Your pages, in the right order.", "Make the words your own."]):
        page = doc.new_page(width=612, height=792)
        page.draw_rect(fitz.Rect(0, 0, 612, 15), color=None, fill=(1, .73, .3))
        page.insert_text((54, 74), "SOL PDF  /  GETTING STARTED", fontname="hebo", fontsize=10, color=(.3, .4, .44))
        page.insert_text((54, 136), title, fontname="hebo", fontsize=24, color=(.12, .18, .21))
        page.insert_text((54, 185), "A local workspace for the documents that get work done.", fontsize=12, color=(.36, .43, .46))
        page.draw_line((54, 218), (558, 218), color=(.82, .86, .83))
        sections = [
            [("01  Start with your document", "Open an existing PDF, or start with a blank page."),
             ("02  Put every page in its place", "Drag page thumbnails to reorder them. Add, remove or rotate pages."),
             ("03  Make a change", "Choose Edit text, click a text run, then apply your replacement."),
             ("04  Keep your work", "Save your PDF. Use Save As to create a separate copy.")],
            [("Bring documents together", "Insert pages from another PDF, including selected page ranges."),
             ("Leave a little room", "Add blank pages with matching, Letter, Legal or A4 dimensions."),
             ("Keep what matters", "Select multiple thumbnails, then delete or extract the selected pages."),
             ("Change your mind", "Undo and redo your changes while the document remains open.")],
            [("Try editing this text", "Project status: Draft"),
             ("Replace a text run", "Click Edit text, select the status above, and try a shorter replacement."),
             ("Add a note", "Choose Add text and click a blank area of this page."),
             ("Review your result", "Standard replacement fonts can look different from embedded fonts.")]
        ][number]
        for index, (heading, body) in enumerate(sections):
            y = 272 + index * 90
            page.insert_text((54, y), heading, fontname="hebo", fontsize=14, color=(.14, .23, .26))
            page.insert_text((54, y + 25), body, fontsize=10, color=(.36, .43, .46))
        page.draw_rect(fitz.Rect(54, 664, 558, 711), color=None, fill=(.97, .95, .9))
        page.insert_text((70, 691), "No account. No subscription. Your documents stay on this computer.", fontsize=10)
        page.insert_text((54, 751), "SOL PDF", fontsize=9, color=(.4, .47, .48))
        page.insert_text((550, 751), str(number + 1), fontsize=9, color=(.4, .47, .48))
    doc.save(path)

app = QApplication([])
app.setStyle("Fusion")
app.setStyleSheet(STYLE)
window = MainWindow()
window.show()
for _ in range(10):
    app.processEvents()
window.grab().save(str(root / "tmp" / "welcome.png"))
window.open_file(path)
for _ in range(20):
    app.processEvents()
window.grab().save(str(root / "tmp" / "workspace.png"))
window.go_page(2)
window.set_mode("edit")
target = next(span for span in window.model.spans(2) if span.text == "Project status: Draft")
window.text_clicked(target)
window.canvas.selected = target
window.editor.setPlainText("Project status: Final")
window.apply_text()
window.model.save(root / "tmp" / "edited.pdf")
for _ in range(10):
    app.processEvents()
window.grab().save(str(root / "tmp" / "text-edit.png"))
with fitz.open(root / "tmp" / "edited.pdf") as edited:
    edited[2].get_pixmap(matrix=fitz.Matrix(1.5, 1.5)).save(str(root / "tmp" / "edited-page.png"))
sol_icon().pixmap(1024, 1024).save(str(root / "assets" / "sol.png"))
window.close()
