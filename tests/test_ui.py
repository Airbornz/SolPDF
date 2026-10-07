import os
import sys
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
import pymupdf as fitz
from PySide6.QtCore import Qt, QPointF, QPoint
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton, QFileDialog, QDialog, QDoubleSpinBox, QComboBox, QCheckBox, QMessageBox, QInputDialog

from sol_pdf.app import MainWindow, STYLE


@pytest.fixture(scope="module")
def app():
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    return app


def test_merged_toolbar_resize_and_crop(app, monkeypatch):
    window = MainWindow()
    monkeypatch.setattr(window, "error", lambda error: pytest.fail(str(error)))
    window.show()
    window.new_file()
    app.processEvents()
    assert window.scroll.parentWidget().layout().count() == 1
    for control in (window.filename, window.page_number, window.page_total, window.zoom_box):
        assert control.parentWidget() == window.document_toolbar
    window.set_mode("view")
    assert window.a_resize.isEnabled() and window.a_crop.isEnabled()
    def accept_resize(dialog):
        combos = dialog.findChildren(QComboBox)
        combos[0].setCurrentText("US Legal")
        combos[1].setCurrentText("Landscape")
        combos[2].setCurrentText("Millimeters")
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(QDialog, "exec", accept_resize)
    window.a_resize.trigger()
    assert window.model.doc[0].rect.width == pytest.approx(1008, abs=.1)
    assert window.model.doc[0].rect.height == pytest.approx(612, abs=.1)
    window.undo()
    def accept_custom(dialog):
        for field, value in zip(dialog.findChildren(QDoubleSpinBox), (5, 7)):
            field.setValue(value)
        dialog.findChild(QCheckBox).setChecked(False)
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(QDialog, "exec", accept_custom)
    window.a_resize.trigger()
    assert window.model.doc[0].rect == fitz.Rect(0, 0, 360, 504)
    window.undo()
    def accept_crop(dialog):
        for field in dialog.findChildren(QDoubleSpinBox):
            field.setValue(10)
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(QDialog, "exec", accept_crop)
    width = window.model.doc[0].rect.width
    window.a_crop.trigger()
    assert window.model.doc[0].rect.width == width - 20
    window.model.saved_revision = window.model.revision
    window.close()


def test_collapsed_sidebar_has_reopen_control_in_both_modes(app):
    window = MainWindow()
    window.show()
    window.new_file()
    app.processEvents()
    assert window.workspace.count() == 2
    for mode in ("view", "edit"):
        window.set_mode(mode)
        app.processEvents()
        window.workspace.setSizes([window.workspace.width(), 320])
        app.processEvents()
        width = window.workspace.sizes()[1]
        window.workspace.setSizes([window.workspace.width(), 0])
        QTest.qWait(20)
        assert window.workspace.sizes()[1] == 0
        assert window.sidebar_reopen.isVisible()
        assert window.workspace.height() > 500
        window.resize(1050, 720)
        app.processEvents()
        assert window.sidebar_reopen.geometry().right() < window.workspace.width()
        window.sidebar_reopen.click()
        app.processEvents()
        assert window.workspace.sizes()[1] == pytest.approx(width, abs=2)
        assert window.sidebar_reopen.isHidden()
        assert window.mode == mode
        window.workspace.setSizes([window.workspace.width(), 0])
        app.processEvents()
        window.a_show_sidebar.trigger()
        assert window.workspace.sizes()[1] > 0
    window.model.saved_revision = window.model.revision
    window.close()


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_on_page_typing_live_preview_matches_applied_pdf(app, tmp_path, monkeypatch, rotation):
    window = MainWindow()
    monkeypatch.setattr(window, "error", lambda error: pytest.fail(str(error)))
    window.show()
    window.new_file()
    app.processEvents()
    assert window.mode == "view" and window.workspace_tabs.currentIndex() == 0
    window.model.rotate([0], rotation)
    window.refresh()
    window.set_mode("add")
    app.processEvents()
    point = fitz.Point(72, 120) * window.model.doc[0].rotation_matrix
    QTest.mouseClick(window.canvas, Qt.MouseButton.LeftButton,
        pos=QPoint(round(point.x * window.canvas.scale), round(point.y * window.canvas.scale)))
    app.processEvents()
    assert window.inline_editor.hasFocus() and window.inline_view.isVisible()
    assert window.editor.isHidden()
    revision = window.model.revision
    QTest.keyClicks(window.inline_editor, "Live preview")
    QTest.keyClick(window.inline_editor, Qt.Key.Key_Return)
    QTest.keyClicks(window.inline_editor, "Second line")
    window.font_size.setValue(20)
    window.bold_button.setChecked(True)
    QTest.qWait(120)
    assert window.editor.toPlainText() == "Live preview\nSecond line"
    assert not window.model.doc[0].get_text() and window.model.revision == revision
    assert window.canvas.image.toImage() != window.canvas.base_image.toImage()
    assert window.inline_proxy.rotation() == rotation
    preview = window.canvas.image.toImage()
    QTest.keyClick(window.inline_editor, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
    app.processEvents()
    assert "Live preview" in window.model.doc[0].get_text()
    assert window.canvas.image.toImage() == preview
    assert window.inline_view.isHidden() and window.target is None
    path = tmp_path / f"inline-{rotation}.pdf"
    window.model.save(path)
    with fitz.open(path) as saved:
        assert saved[0].rotation == rotation and "Second line" in saved[0].get_text()
    window.close()


def test_inline_draft_cancel_reposition_zoom_and_tab_restore(app, monkeypatch):
    window = MainWindow()
    monkeypatch.setattr(window, "error", lambda error: pytest.fail(str(error)))
    window.show()
    window.new_file()
    first = window.model
    window.set_mode("add")
    app.processEvents()
    window.text_clicked((72, 120))
    window.inline_editor.setPlainText("Keep this draft")
    window.text_clicked((100, 150))
    QTest.qWait(100)
    assert window.inline_editor.toPlainText() == "Keep this draft"
    window.zoom_box.setCurrentText("150%")
    QTest.qWait(100)
    assert window.inline_view.geometry() == window.canvas.rect()
    window.new_file()
    assert window.mode == "view" and window.inline_view.isHidden()
    window.activate_document(0)
    QTest.qWait(100)
    assert window.model is first and window.mode == "add"
    assert window.inline_view.isVisible() and window.inline_editor.toPlainText() == "Keep this draft"
    assert window.text_x.value() == 100 and window.text_y.value() == 150
    QTest.keyClick(window.inline_editor, Qt.Key.Key_Escape)
    assert window.inline_view.isHidden() and not first.doc[0].get_text()
    assert window.canvas.image.toImage() == window.canvas.base_image.toImage()
    for document in window.documents:
        document["model"].saved_revision = document["model"].revision
    window.close()


@pytest.mark.parametrize("size,zoom", [(12, "Fit page"), (12, "150%"), (24, "50%")])
def test_highlighting_inline_text_keeps_glyph_size(app, size, zoom):
    window = MainWindow()
    window.show()
    window.new_file()
    window.set_mode("add")
    app.processEvents()
    window.zoom_box.setCurrentText(zoom)
    window.text_clicked((72, 120))
    window.font_size.setValue(size)
    window.inline_editor.setPlainText("Selecting this text")
    QTest.qWait(100)
    font = window.inline_editor.document().defaultFont()
    assert font.pointSizeF() * window.inline_editor.logicalDpiY() / 72 == pytest.approx(size * window.canvas.scale)
    window.inline_editor.clearFocus()
    app.processEvents()
    before = window.canvas.grab().toImage()
    image = window.canvas.image.toImage()
    revision = window.model.revision
    window.inline_editor.selectAll()
    app.processEvents()
    after = window.canvas.grab().toImage()
    area = window.inline_proxy.sceneBoundingRect().toAlignedRect().intersected(window.canvas.rect())
    def glyph_bounds(snapshot):
        pixels = [(x, y) for y in range(area.top(), area.bottom()) for x in range(area.left(), area.right())
            if max(snapshot.pixelColor(x, y).red(), snapshot.pixelColor(x, y).green(), snapshot.pixelColor(x, y).blue()) < 200]
        assert pixels
        return min(x for x, y in pixels), min(y for x, y in pixels), max(x for x, y in pixels), max(y for x, y in pixels)
    assert glyph_bounds(after) == pytest.approx(glyph_bounds(before), abs=1)
    assert window.canvas.image.toImage() == image and window.model.revision == revision
    assert window.font_size.value() == size
    assert not window.preview_timer.isActive()
    window.model.saved_revision = window.model.revision
    window.close()


def test_document_tabs_keep_independent_edits_drafts_and_view_state(app, tmp_path, monkeypatch):
    paths = []
    for name in ("First", "Second"):
        path = tmp_path / f"{name}.pdf"
        with fitz.open() as doc:
            for number in range(2):
                doc.new_page().insert_text((72, 90), f"{name} page {number + 1}")
            doc.save(path)
        paths.append(path)
    window = MainWindow()
    monkeypatch.setattr(window, "error", lambda error: pytest.fail(str(error)))
    window.show()
    window.open_file(paths[0])
    first = window.model
    window.mutate(lambda: first.rotate([0]))
    window.go_page(1)
    window.zoom_box.setCurrentText("100%")
    window.focus_search()
    window.search.setText("First")
    window.find_next()
    window.go_page(1)
    window.set_mode("edit")
    window.text_clicked(window.model.spans(1)[0])
    window.editor.setPlainText("Unapplied first draft")
    window.font_size.setValue(19)
    window.text_x.setValue(100)
    window.bounds_check.setChecked(False)
    window.open_file(paths[1])  # Opening does not ask to close/save the first PDF.
    second = window.model
    assert window.document_tabs.count() == 2 and second is not first
    assert window.current_page == 0 and window.mode == "view"
    assert window.zoom_box.currentText() == "Fit page"
    assert window.find_panel.isHidden() and not window.search.text()
    window.mutate(lambda: second.blank(0))
    window.a_undo.trigger()
    assert second.count == 2 and first.doc[0].rotation == 90
    window.document_tabs.setCurrentIndex(0)
    app.processEvents()
    assert window.model is first and window.current_page == 1
    assert window.mode == "edit" and window.zoom_box.currentText() == "100%"
    assert window.target is not None and window.editor.toPlainText() == "Unapplied first draft"
    assert window.font_size.value() == 19 and window.text_x.value() == 100
    assert not window.canvas.show_bounds
    assert window.find_panel.isVisible() and window.search.text() == "First"
    assert len(window.search_hits) == 2
    window.apply_text()
    assert "Unapplied first draft" in first.doc[1].get_text()
    assert "Second page 2" in second.doc[1].get_text()
    window.a_undo.trigger()
    assert "First page 2" in first.doc[1].get_text()
    window.open_file(paths[1])
    assert window.document_tabs.count() == 2 and window.model is second
    window.a_previous_document.trigger()
    assert window.model is first
    modifier = Qt.KeyboardModifier.MetaModifier if sys.platform == "darwin" else Qt.KeyboardModifier.ControlModifier
    QTest.keyClick(window, Qt.Key.Key_Tab, modifier)
    app.processEvents()
    assert window.model is second
    QTest.keyClick(window, Qt.Key.Key_Tab, modifier | Qt.KeyboardModifier.ShiftModifier)
    app.processEvents()
    assert window.model is first
    for document in window.documents:
        document["model"].saved_revision = document["model"].revision
    window.close()


def test_document_tab_close_save_cancel_and_window_close(app, tmp_path, monkeypatch):
    window = MainWindow()
    window.show()
    window.new_file()
    first = window.model
    window.new_file()
    second = window.model
    assert window.document_tabs.count() == 2
    assert window.document_tabs.tabText(0) != window.document_tabs.tabText(1)
    assert "•" in window.document_tabs.tabText(0)
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Cancel)
    window.close_document_tab(0)
    assert window.document_tabs.count() == 2 and not first.doc.is_closed
    output = tmp_path / "first saved.pdf"
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Save)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(output), ""))
    window.close_document_tab(0)
    assert first.doc.is_closed and output.exists()
    assert window.document_tabs.count() == 1 and window.model is second
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Cancel)
    window.close()
    assert window.isVisible() and not second.doc.is_closed
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Discard)
    window.a_close.trigger()
    assert not window.documents and window.document_tabs.isHidden()
    assert window.stack.currentIndex() == 0 and window.model.doc is None
    window.close()


def test_open_multiple_files_and_failed_open_keeps_existing_tab(app, tmp_path, monkeypatch):
    paths = []
    for number in range(2):
        path = tmp_path / f"open {number}.pdf"
        with fitz.open() as doc:
            doc.new_page()
            doc.save(path)
        paths.append(str(path))
    window = MainWindow()
    window.show()
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *args: (paths, ""))
    window.open_dialog()
    assert len(window.documents) == 2 and window.model.path == Path(paths[1])
    active = window.model
    errors = []
    monkeypatch.setattr(window, "error", errors.append)
    window.open_file(tmp_path / "missing.pdf")
    assert errors and window.model is active and len(window.documents) == 2
    window.close_document_tab(0)
    assert window.model is active and len(window.documents) == 1
    window.close()


def test_window_close_checks_all_documents_without_losing_cancelled_tabs(app, monkeypatch):
    window = MainWindow()
    window.show()
    window.new_file()
    first = window.model
    window.new_file()
    second = window.model
    answers = iter((QMessageBox.StandardButton.Discard, QMessageBox.StandardButton.Cancel))
    monkeypatch.setattr(QMessageBox, "question", lambda *args: next(answers))
    window.close()
    assert window.isVisible() and len(window.documents) == 2
    assert not first.doc.is_closed and not second.doc.is_closed
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Discard)
    window.close()
    assert first.doc.is_closed and second.doc.is_closed


def test_empty_page_sidebar_context_menu_inserts_into_active_document(app, tmp_path, monkeypatch):
    window = MainWindow()
    window.show()
    window.new_file()
    first = window.model
    window.new_file()
    second = window.model
    window.set_mode("view")
    app.processEvents()
    assert not {"+ Blank page", "+ Insert PDF"}.intersection(button.text() for button in window.findChildren(QPushButton))
    empty = window.pages.viewport().rect().bottomRight() - QPoint(2, 2)
    assert window.pages.itemAt(empty) is None
    window.show_page_menu(empty)
    assert [action.text() for action in window.page_popup.actions()] == ["Add blank page…", "Insert PDF…"]
    window.page_popup.close()
    monkeypatch.setattr(QDialog, "exec", lambda dialog: QDialog.DialogCode.Accepted)
    window.a_blank.trigger()
    assert second.count == 2 and first.count == 1
    path = tmp_path / "insert.pdf"
    with fitz.open() as doc:
        doc.new_page().insert_text((72, 90), "Inserted into active tab")
        doc.save(path)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: (str(path), ""))
    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: ("1", True))
    window.a_import.trigger()
    assert second.count == 3 and first.count == 1
    assert "Inserted into active tab" in second.doc[2].get_text()
    for document in window.documents:
        document["model"].saved_revision = document["model"].revision
    window.close()


def test_editor_workflow_and_rotation(app, tmp_path):
    path = tmp_path / "ui.pdf"
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((72, 90), "Original title", fontsize=18)
        doc.new_page().insert_text((72, 90), "Second page", fontsize=18)
        doc.save(path)
    window = MainWindow()
    window.show()
    window.open_file(path)
    app.processEvents()
    assert window.pages.count() == 2
    window.set_mode("edit")
    span = window.model.spans(0)[0]
    window.text_clicked(span)
    window.editor.setPlainText("New title")
    window.apply_text()
    assert "New title" in window.model.doc[0].get_text()
    window.undo()
    assert "Original title" in window.model.doc[0].get_text()
    window.redo()
    window.move_page(1)
    assert window.current_page == 1
    window.mutate(lambda: window.model.rotate([1]))
    span = window.model.spans(1)[0]
    rect = fitz.Rect(span.rect) * window.canvas.rotation
    display = QPointF((rect.x0 + rect.x1) * .5 * window.canvas.scale,
                      (rect.y0 + rect.y1) * .5 * window.canvas.scale)
    event = QMouseEvent(QMouseEvent.Type.MouseButtonPress, display, display,
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    window.canvas.mousePressEvent(event)
    assert window.target.text == "New title"
    window.search.setText("New title")
    window.find_next()
    assert len(window.search_hits) == 1
    output = tmp_path / "saved.pdf"
    window.model.save(output)
    window.close()


def test_welcome_and_blank_document(app):
    window = MainWindow()
    assert not window.a_save.isEnabled()
    window.new_file()
    app.processEvents()
    assert window.model.count == 1
    assert not window.a_delete.isEnabled()
    window.set_mode("add")
    window.text_clicked((72, 90))
    window.editor.setPlainText("Hello Sol PDF")
    window.apply_text()
    assert "Hello Sol PDF" in window.model.doc[0].get_text()
    window.model.saved_revision = window.model.revision
    window.close()


def test_reorder_retains_selected_page_identity(app, tmp_path):
    path = tmp_path / "reorder.pdf"
    with fitz.open() as doc:
        for title in ("One", "Two", "Three"):
            doc.new_page().insert_text((72, 90), title)
        doc.save(path)
    window = MainWindow()
    window.open_file(path)
    window.set_mode("edit")
    window.pages.blockSignals(True)
    item = window.pages.takeItem(0)
    window.pages.insertItem(2, item)
    window.pages.setCurrentItem(item)
    window.pages.blockSignals(False)
    window.current_page = 2  # Qt changes the current row before dropEvent fires.
    window.pages.reordered.emit([1, 2, 0])
    assert window.current_page == 2
    assert "One" in window.model.doc[2].get_text()
    window.model.saved_revision = window.model.revision
    window.close()


def test_view_and_edit_modes(app, tmp_path):
    path = tmp_path / "modes.pdf"
    with fitz.open() as doc:
        doc.new_page().insert_text((72, 90), "Original title")
        doc.new_page()
        doc.save(path)
    window = MainWindow()
    window.show()
    window.open_file(path)
    app.processEvents()
    assert window.a_view_mode.isChecked()
    assert not window.a_edit_mode.isChecked()
    assert not window.inspector.isVisible() and window.page_sidebar.isVisible()
    assert window.page_sidebar.isVisible() and window.workspace_tabs.currentIndex() == 0
    assert window.workspace.widget(0) is not window.workspace_tabs
    assert window.workspace.widget(1) is window.workspace_tabs
    assert not window.a_edit.isVisible() and not window.a_add.isVisible()
    assert window.a_rotate.isEnabled() and not window.a_undo.isEnabled()
    assert window.pages.dragEnabled()
    assert window.canvas.mode == "view"
    view_width = window.scroll.width()
    revision = window.model.revision
    window.text_clicked(window.model.spans(0)[0])
    assert window.model.revision == revision and window.target is None

    window.a_edit_mode.trigger()
    app.processEvents()
    assert window.a_edit_mode.isChecked() and window.mode == "edit"
    assert window.inspector.isVisible() and not window.page_sidebar.isVisible()
    assert window.workspace_tabs.currentIndex() == 1
    assert window.a_edit.isVisible() and window.a_add.isVisible()
    assert window.a_rotate.isEnabled() and window.pages.dragEnabled()
    assert window.scroll.width() == view_width
    window.a_add.trigger()
    assert window.mode == "add"
    window.text_clicked((72, 150))
    window.editor.setPlainText("Unapplied text")
    window.a_view_mode.trigger()
    app.processEvents()
    assert window.mode == "view" and window.canvas.mode == "view"
    assert window.target is None and window.editor.toPlainText() == ""
    assert not window.inspector.isVisible() and window.canvas.selected is None
    assert window.page_sidebar.isVisible()
    assert window.scroll.width() == view_width
    window.a_edit_mode.trigger()
    assert window.mode == "add"  # The last editing tool is remembered.
    window.a_view_mode.trigger()
    window.search.setText("Original")
    window.find_next()
    assert len(window.search_hits) == 1
    window.close()


def test_thumbnail_context_actions_target_clicked_and_selected_pages(app, tmp_path, monkeypatch):
    path = tmp_path / "context.pdf"
    with fitz.open() as doc:
        for title in ("One", "Two", "Three"):
            doc.new_page().insert_text((72, 90), title)
        doc.save(path)
    window = MainWindow()
    window.show()
    window.open_file(path)
    window.set_mode("edit")
    app.processEvents()
    menu = window.page_context_menu(1)
    assert window.current_page == 1 and window.selected_pages() == [1]
    assert [a.text() for a in menu.actions() if not a.isSeparator()] == ["Rotate", "Resize page…", "Crop page…", "Delete page", "Duplicate page", "Extract page…"]
    rotation = menu.actions()[0].menu()
    assert [a.text() for a in rotation.actions()][:3] == ["90° clockwise", "180°", "90° counterclockwise"]
    assert [a.text() for a in rotation.actions()][4:] == ["Flip horizontally", "Flip vertically"]
    rotation.actions()[2].trigger()
    assert window.model.doc[0].rotation == 0 and window.model.doc[1].rotation == 270
    window.undo()
    window.page_context_menu(1)
    original = window.model.doc[1].get_pixmap().samples
    window.a_flip_horizontal.trigger()
    assert window.model.doc[1].get_pixmap().samples != original
    assert "Two" in window.model.doc[1].get_text()
    window.undo()
    assert window.model.doc[1].get_pixmap().samples == original
    window.page_context_menu(1)
    window.a_duplicate.trigger()
    assert window.model.count == 4 and "Two" in window.model.doc[2].get_text()
    window.undo()

    window.pages.clearSelection()
    window.pages.item(0).setSelected(True)
    window.pages.item(2).setSelected(True)
    window.page_context_menu(2)
    assert window.selected_pages() == [0, 2]  # Right-click preserves an existing multiselection.
    window.a_rotate.trigger()
    assert [page.rotation for page in window.model.doc] == [90, 0, 90]
    window.undo()

    window.page_context_menu(1)
    output = tmp_path / "extracted.pdf"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(output), ""))
    window.a_extract.trigger()
    with fitz.open(output) as extracted:
        assert len(extracted) == 1 and "Two" in extracted[0].get_text()
    window.a_delete.trigger()
    assert window.model.count == 2
    assert "Three" in window.model.doc[1].get_text()
    window.undo()
    assert window.page_context_menu(-1) is None
    buttons = {button.text() for button in window.findChildren(QPushButton)}
    assert not buttons.intersection({"↶", "↷", "Delete", "Rotate selected pages",
        "Duplicate page", "Extract selected pages"})
    window.set_mode("view")
    window.page_context_menu(0)
    assert window.a_rotate.isEnabled() and window.a_delete.isEnabled()
    window.model.saved_revision = window.model.revision
    window.close()


def test_floating_find_shortcut_navigation_and_dismissal(app, tmp_path):
    path = tmp_path / "find.pdf"
    with fitz.open() as doc:
        doc.new_page().insert_text((72, 90), "Needle One Needle Two")
        doc.new_page().insert_text((72, 90), "Needle Three")
        doc.save(path)
    window = MainWindow()
    window.show()
    window.activateWindow()
    window.open_file(path)
    app.processEvents()
    assert window.find_panel.isHidden()
    initial_size = window.scroll.viewport().size()
    shortcut = window.a_find.shortcut()[0]
    QTest.keyClick(window, shortcut.key(), shortcut.keyboardModifiers())
    app.processEvents()
    assert window.find_panel.isVisible() and window.search.hasFocus()
    assert window.scroll.viewport().size() == initial_size
    assert window.find_panel.parentWidget() is window.scroll.viewport()
    window.search.setText("Needle")
    QTest.qWait(220)
    assert len(window.search_hits) == 3 and window.find_panel.count.text() == "1/3"
    QTest.keyClick(window.search, Qt.Key.Key_Return)
    assert window.find_panel.count.text() == "2/3"
    QTest.keyClick(window.search, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
    assert window.find_panel.count.text() == "1/3"
    buttons = {button.accessibleName(): button for button in window.find_panel.findChildren(QPushButton)}
    buttons["Previous match"].click()
    assert window.find_panel.count.text() == "3/3" and window.current_page == 1
    buttons["Next match"].click()
    assert window.find_panel.count.text() == "1/3" and window.current_page == 0
    QTest.keyClick(window.search, Qt.Key.Key_Escape)
    assert window.find_panel.isHidden() and not window.canvas.search_rects
    assert window.scroll.viewport().size() == initial_size
    window.a_find.trigger()
    assert window.search.selectedText() == "Needle"
    window.search.setText("Missing text")
    QTest.qWait(220)
    assert window.find_panel.count.text() == "0/0"
    window.search.clear()
    assert window.find_panel.count.text() == ""
    window.search.setText("Needle")
    window.find_next(-1)
    assert window.find_panel.count.text() == "3/3"
    buttons["Close Find"].click()
    assert window.find_panel.isHidden()
    window.a_find.trigger()
    window.set_mode("edit")
    app.processEvents()
    assert window.find_panel.isVisible()
    assert window.find_panel.geometry().right() <= window.scroll.viewport().width()
    window.close_document()
    assert window.find_panel.isHidden() and not window.search.text()
    window.close()


def test_edit_tab_formatting_image_and_crop(app, tmp_path, monkeypatch):
    window = MainWindow()
    monkeypatch.setattr(window, "error", lambda error: pytest.fail(str(error)))
    window.show()
    window.new_file()
    app.processEvents()
    window.workspace_tabs.setCurrentIndex(0)
    assert window.mode == "view" and window.page_sidebar.isVisible()
    window.workspace_tabs.setCurrentIndex(1)
    app.processEvents()
    assert window.mode == "edit" and window.inspector.isVisible()
    assert not window.page_sidebar.isVisible() and window.edit_toolbar.isVisible()
    window.a_add.trigger()
    window.text_clicked((72, 90))
    window.bold_button.click()
    window.italic_button.click()
    assert window.fonts.currentData() == "hebi"
    window.editor.setPlainText("Styled text")
    window.text_x.setValue(100)
    window.text_y.setValue(140)
    window.resize(1050, 720)
    app.processEvents()
    assert window.editor.toPlainText() == "Styled text"  # Resizing retains the draft.
    window.apply_text()
    span = window.model.spans(0)[0]
    assert span.origin == (100, 140) and "BoldOblique" in span.font
    window.bounds_check.click()
    assert not window.canvas.show_bounds
    image = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 40, 20), False)
    image.clear_with(100)
    path = tmp_path / "photo.png"
    image.save(path)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: (str(path), ""))
    monkeypatch.setattr(QDialog, "exec", lambda dialog: QDialog.DialogCode.Accepted)
    window.a_image.trigger()
    assert len(window.model.doc[0].get_images()) == 1
    def accept_crop(dialog):
        for field, value in zip(dialog.findChildren(QDoubleSpinBox), (10, 20, 30, 40)):
            field.setValue(value)
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(QDialog, "exec", accept_crop)
    original = window.model.doc[0].rect
    window.a_crop.trigger()
    assert window.model.doc[0].rect.width == original.width - 40
    window.model.saved_revision = window.model.revision
    window.close()
