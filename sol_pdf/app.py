from __future__ import annotations

import math
import json
import os
import sys
from pathlib import Path

if os.environ.get("SOL_PDF_SMOKE_OUTPUT"):
    os.environ["QT_QPA_PLATFORM"] = "offscreen"

import pymupdf as fitz
from PySide6.QtCore import Qt, QSize, Signal, QTimer, QRectF, QRect, QItemSelectionModel, QEvent, QPointF
from PySide6.QtGui import (QAction, QActionGroup, QColor, QFont, QIcon, QImage, QKeySequence,
                          QPainter, QPen, QPixmap, QFontMetricsF, QTextBlockFormat, QTextCursor)
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QComboBox,
    QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout,
    QFrame, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QMessageBox, QPushButton, QScrollArea,
    QSizePolicy, QSpinBox, QSplitter, QStackedWidget, QTextEdit, QStyle, QStyledItemDelegate,
    QToolBar, QVBoxLayout, QWidget, QColorDialog, QMenu, QTabWidget, QTabBar, QCheckBox,
    QGraphicsView, QGraphicsScene)

from sol_pdf.document import PDFDocument, PDFError, PasswordRequired, parse_pages


STYLE = """
QMainWindow, QWidget { background: #f6f5f1; color: #292d32; font-size: 13px; }
QMenuBar, QMenu { background: #ffffff; }
QMenu::item:selected { background: #fff0d6; }
QToolBar { background: #fafafa; border: 0; border-bottom: 1px solid #dce0db; padding: 8px; spacing: 8px; }
QToolBar QLabel { background: transparent; color: #292d32; }
QToolBar QToolButton { color: #39434b; background: transparent; border-radius: 4px; padding: 7px 10px; }
QToolBar QToolButton:hover { background: #e8edf2; }
QToolBar QToolButton:checked { color: #1765b5; background: #e6f0fc; }
QToolBar QToolButton:disabled { color: #a3aab0; }
QToolBar::separator { background: #d4dbe0; width: 1px; margin: 5px; }
QTabWidget::pane { background: #ffffff; border: 0; border-left: 1px solid #dce0db; }
QTabBar::tab { background: #f3f5f6; color: #5b6770; border-bottom: 3px solid transparent; padding: 13px 16px; }
QTabBar::tab:selected { color: #1765b5; background: #ffffff; border-bottom-color: #2475db; }
QTabBar::tab:hover { background: #eaf0f5; }
QTabBar#documentTabs::tab { padding: 9px 14px; border-right: 1px solid #dce0db; }
QTabBar#documentTabs::tab:selected { background: #ffffff; color: #1765b5; }
QPushButton:checked { background: #e6f0fc; color: #1765b5; border-color: #8eb8e4; }
QPushButton { background: #ffffff; border: 1px solid #d8dcd9; border-radius: 6px; padding: 8px 12px; }
QPushButton:hover { background: #fff5e4; border-color: #d4ad6d; }
QPushButton:disabled { color: #9da3a5; background: #eceeea; border-color: #e0e3df; }
QPushButton#primary { background: #f5ad3c; color: #202d36; border: 1px solid #f5ad3c; font-weight: 600; }
QPushButton#primary:hover { background: #ffc565; }
QPushButton#primary:disabled { background: #eceeea; color: #9da3a5; border-color: #e0e3df; }
QLabel#eyebrow { color: #737e82; font-size: 11px; font-weight: 600; }
QLabel#title { font-size: 24px; font-weight: 600; }
QLabel#muted { color: #68757a; }
QFrame#panel { background: #ffffff; border-right: 1px solid #dce0db; }
QFrame#panel QLabel { background: #ffffff; }
QListWidget { border: 0; background: #ffffff; outline: 0; padding: 8px; }
QListWidget::item { border: 2px solid transparent; border-radius: 7px; padding: 12px; margin: 3px; }
QListWidget::item:selected { background: #fff1d9; border-color: #e9af50; color: #202d36; }
QLineEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    border: 1px solid #d6dcd7; background: #ffffff; border-radius: 5px; padding: 7px; selection-background-color: #ffda99;
}
QComboBox QAbstractItemView { background: #ffffff; color: #292d32; }
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {
    background: #f1f3f3; color: #9da3a5;
}
QScrollArea { border: 0; background: #dfe4e2; }
QWidget#canvasHost { background: #dfe4e2; }
QStatusBar { background: #ffffff; border-top: 1px solid #dce0db; color: #637077; }
QSplitter::handle { background: #dce0db; width: 1px; }
QScrollBar:vertical { background: #eef0eb; width: 12px; margin: 0; }
QScrollBar::handle:vertical { background: #b9c3c0; border-radius: 5px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QToolTip { background: #202d36; color: white; border: 0; padding: 6px; }
QFrame#findPanel { background: #ffffff; border: 1px solid #bcc7c1; border-radius: 8px; }
QFrame#findPanel QLabel { background: #ffffff; border: 0; color: #68757a; }
QFrame#findPanel QPushButton { padding: 5px; min-width: 24px; }
"""


def pixmap(page, scale):
    image = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
    qimage = QImage(image.samples, image.width, image.height, image.stride,
                    QImage.Format.Format_RGB888).copy()
    return QPixmap.fromImage(qimage)


def sol_icon():
    image = QPixmap(128, 128)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#202d36"))
    painter.drawRoundedRect(0, 0, 128, 128, 28, 28)
    painter.setBrush(QColor("#ffbc52"))
    painter.drawEllipse(35, 35, 58, 58)
    painter.setPen(QPen(QColor("#ffbc52"), 5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    for angle in range(0, 360, 45):
        radians = math.radians(angle)
        painter.drawLine(round(64 + 39 * math.cos(radians)), round(64 + 39 * math.sin(radians)),
                         round(64 + 48 * math.cos(radians)), round(64 + 48 * math.sin(radians)))
    painter.end()
    return QIcon(image)


class PageList(QListWidget):
    reordered = Signal(list)

    def dropEvent(self, event):
        super().dropEvent(event)
        self.reordered.emit([self.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.count())])


class PageDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = option.rect.adjusted(4, 3, -4, -3)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        painter.setPen(QPen(QColor("#e9af50" if selected else "#e2e7e1"), 2 if selected else 1))
        painter.setBrush(QColor("#fff1d9" if selected else "#fafbf8"))
        painter.drawRoundedRect(rect, 6, 6)
        icon = index.data(Qt.ItemDataRole.DecorationRole)
        if icon:
            size = icon.actualSize(QSize(126, 150))
            icon.paint(painter, QRect(rect.center().x() - size.width() // 2,
                rect.top() + 10, size.width(), size.height()), mode=QIcon.Mode.Normal)
        painter.setPen(QColor("#46555d"))
        painter.drawText(QRect(rect.left(), rect.bottom() - 26, rect.width(), 21),
            Qt.AlignmentFlag.AlignCenter, index.data(Qt.ItemDataRole.DisplayRole))
        painter.restore()


class Canvas(QWidget):
    clicked = Signal(object)

    def __init__(self):
        super().__init__()
        self.image = None
        self.scale = 1
        self.rotation = fitz.Matrix(1, 1)
        self.derotation = fitz.Matrix(1, 1)
        self.spans = []
        self.selected = None
        self.search_rects = []
        self.mode = "view"
        self.show_bounds = True
        self.hovered = None
        self.setMouseTracking(True)

    def set_page(self, page, scale, spans):
        self.scale = scale
        self.rotation = page.rotation_matrix
        self.derotation = page.derotation_matrix
        self.image = pixmap(page, scale)
        self.base_image = self.image
        self.spans = spans
        self.selected = None
        self.hovered = None
        self.setFixedSize(self.image.size())
        self.update()

    def point(self, event):
        return fitz.Point(event.position().x() / self.scale,
                          event.position().y() / self.scale) * self.derotation

    def span_at(self, point):
        candidates = [s for s in self.spans if fitz.Rect(s.rect).contains(point)]
        return min(candidates, key=lambda s: fitz.Rect(s.rect).get_area()) if candidates else None

    def mouseMoveEvent(self, event):
        hovered = self.span_at(self.point(event)) if self.mode == "edit" else None
        if hovered != self.hovered:
            self.hovered = hovered
            self.update()
        self.setCursor(Qt.CursorShape.IBeamCursor if hovered or self.mode == "add" else Qt.CursorShape.ArrowCursor)

    def leaveEvent(self, event):
        self.hovered = None
        self.update()

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        point = self.point(event)
        if self.mode == "edit":
            self.selected = self.span_at(point)
            self.update()
            self.clicked.emit(self.selected)
        elif self.mode == "add":
            self.clicked.emit((point.x, point.y))

    def draw_rect(self, painter, rect, stroke, fill):
        rect = fitz.Rect(rect) * self.rotation
        painter.setPen(QPen(QColor(stroke), 1.5))
        painter.setBrush(QColor(fill))
        painter.drawRoundedRect(QRectF(rect.x0 * self.scale, rect.y0 * self.scale,
            rect.width * self.scale, rect.height * self.scale), 2, 2)

    def paintEvent(self, event):
        painter = QPainter(self)
        if self.image:
            painter.drawPixmap(0, 0, self.image)
        for rect in self.search_rects:
            self.draw_rect(painter, rect, "#d99a26", "#55ffc356")
        if self.mode == "edit" and self.show_bounds:
            for span in self.spans:
                self.draw_rect(painter, span.rect, "#44779195", "#05779195")
        if self.hovered:
            self.draw_rect(painter, self.hovered.rect, "#f0a331", "#25ffbd4b")
        if self.selected:
            self.draw_rect(painter, self.selected.rect, "#d78a19", "#35ffc356")
        painter.end()


class PageTextEditor(QTextEdit):
    apply_requested = Signal()
    cancel_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setAcceptRichText(False)
        self.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setCursorWidth(0)
        self.caret_color = QColor("#202d36")
        self.setAccessibleName("Add text on page")
        self.setPlaceholderText("Type here…")
        self.document().setDocumentMargin(4)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.cancel_requested.emit()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.apply_requested.emit()
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        selection = self.textCursor()
        if selection.hasSelection():
            painter = QPainter(self.viewport())
            block = self.document().findBlock(selection.selectionStart())
            while block.isValid() and block.position() < selection.selectionEnd():
                start = max(block.position(), selection.selectionStart())
                end = min(block.position() + block.length() - 1, selection.selectionEnd())
                cursor = QTextCursor(self.document())
                cursor.setPosition(start)
                first = self.cursorRect(cursor)
                cursor.setPosition(end)
                last = self.cursorRect(cursor)
                painter.fillRect(QRectF(first.left(), first.top(), max(1, last.left() - first.left()), first.height()), QColor(36, 117, 219, 45))
                block = block.next()
        elif self.hasFocus():
            painter = QPainter(self.viewport())
            painter.setPen(QPen(self.caret_color, 1))
            rect = self.cursorRect()
            painter.drawLine(rect.topLeft(), rect.bottomLeft())


class PageTextView(QGraphicsView):
    def __init__(self, canvas):
        super().__init__(canvas)
        self.canvas = canvas
        self.setScene(QGraphicsScene(self))
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet("QGraphicsView { background: transparent; border: 0; }")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.viewport().setAutoFillBackground(False)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setCursor(Qt.CursorShape.IBeamCursor)

    def mousePressEvent(self, event):
        if self.itemAt(event.position().toPoint()) is None:
            self.canvas.mousePressEvent(event)
        else:
            super().mousePressEvent(event)


class FindPanel(QFrame):
    next_requested = Signal()
    previous_requested = Signal()
    close_requested = Signal()

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("findPanel")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Find…")
        self.search.setAccessibleName("Find text")
        self.search.installEventFilter(self)
        self.search.returnPressed.connect(self.next_requested.emit)
        layout.addWidget(self.search, 1)
        self.count = QLabel()
        self.count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.count.setMinimumWidth(48)
        layout.addWidget(self.count)
        for text, name, signal in (("‹", "Previous match", self.previous_requested),
                ("›", "Next match", self.next_requested), ("×", "Close Find", self.close_requested)):
            button = QPushButton(text)
            button.setToolTip(name)
            button.setAccessibleName(name)
            button.clicked.connect(lambda checked=False, requested=signal: requested.emit())
            layout.addWidget(button)
        parent.installEventFilter(self)
        self.hide()

    def position_panel(self):
        viewport = self.parentWidget()
        self.setFixedWidth(min(400, max(300, viewport.width() - 24)))
        self.adjustSize()
        self.move(max(12, viewport.width() - self.width() - 12), 12)

    def eventFilter(self, watched, event):
        if watched is self.parentWidget() and event.type() == QEvent.Type.Resize:
            self.position_panel()
        elif watched is self.search and event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Escape:
                self.close_requested.emit()
                return True
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self.previous_requested.emit()
                return True
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close_requested.emit()
            event.accept()
        else:
            super().keyPressEvent(event)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.model = PDFDocument()
        self.documents = []
        self.active_document = None
        self.untitled_count = 0
        self.current_page = 0
        self.mode = "view"
        self.last_edit_tool = "edit"
        self.target = None
        self.text_color = QColor("#202d36")
        self.zoom = 1.0
        self.fit = True
        self.generation = 0
        self.search_hits = []
        self.search_index = -1
        self.setWindowTitle("Sol PDF")
        self.setWindowIcon(sol_icon())
        self.resize(1370, 900)
        self.setMinimumSize(980, 640)
        self.setAcceptDrops(True)
        self.make_actions()
        self.make_toolbar()
        self.make_body()
        self.make_menus()
        self.statusBar().showMessage("Ready")
        self.update_actions()

    def action(self, name, text, callback, shortcut=None, checkable=False):
        action = QAction(text, self)
        action.setCheckable(checkable)
        if shortcut:
            action.setShortcut(shortcut)
        action.triggered.connect(callback)
        setattr(self, name, action)
        return action

    def make_actions(self):
        self.action("a_new", "New PDF", self.new_file, QKeySequence.StandardKey.New)
        self.action("a_open", "Open PDF", self.open_dialog, QKeySequence.StandardKey.Open)
        self.action("a_save", "Save", self.save_file, QKeySequence.StandardKey.Save)
        self.action("a_save_as", "Save As…", lambda: self.save_file(True), QKeySequence.StandardKey.SaveAs)
        self.action("a_undo", "Undo", self.undo, QKeySequence.StandardKey.Undo)
        self.action("a_redo", "Redo", self.redo, QKeySequence.StandardKey.Redo)
        self.action("a_view_mode", "View / Organize", lambda: self.set_mode("view"), checkable=True)
        self.action("a_edit_mode", "Edit", lambda: self.set_mode(self.last_edit_tool), checkable=True)
        self.mode_actions = QActionGroup(self)
        self.mode_actions.addAction(self.a_view_mode)
        self.mode_actions.addAction(self.a_edit_mode)
        self.action("a_edit", "Edit text", lambda: self.set_mode("edit"), checkable=True)
        self.action("a_add", "Add text", lambda: self.set_mode("add"), checkable=True)
        self.text_actions = QActionGroup(self)
        self.text_actions.addAction(self.a_edit)
        self.text_actions.addAction(self.a_add)
        self.action("a_image", "Add image…", self.add_image)
        self.action("a_crop", "Crop page…", self.crop_page)
        self.action("a_resize", "Resize page…", self.resize_page)
        self.action("a_blank", "Add blank page…", self.blank_page)
        self.action("a_import", "Insert PDF…", self.import_pdf)
        self.action("a_delete", "Delete pages", self.delete_pages)
        self.action("a_rotate", "90° clockwise", lambda: self.rotate_pages(90))
        self.action("a_rotate_left", "90° counterclockwise", lambda: self.rotate_pages(-90))
        self.action("a_rotate_180", "180°", lambda: self.rotate_pages(180))
        self.rotation_actions = (self.a_rotate, self.a_rotate_180, self.a_rotate_left)
        self.action("a_flip_horizontal", "Flip horizontally", lambda: self.flip_pages(True))
        self.action("a_flip_vertical", "Flip vertically", lambda: self.flip_pages(False))
        self.flip_actions = (self.a_flip_horizontal, self.a_flip_vertical)
        self.action("a_duplicate", "Duplicate page", self.duplicate_pages)
        self.action("a_extract", "Extract pages…", self.extract_pages)
        self.action("a_find", "Find…", self.focus_search, QKeySequence.StandardKey.Find)
        self.action("a_close", "Close document", self.close_document, QKeySequence("Ctrl+W"))
        self.action("a_show_sidebar", "Show right sidebar", self.restore_sidebar)
        next_tab = QKeySequence("Meta+Tab") if sys.platform == "darwin" else QKeySequence.StandardKey.NextChild
        previous_tab = QKeySequence("Meta+Shift+Tab") if sys.platform == "darwin" else QKeySequence.StandardKey.PreviousChild
        self.action("a_next_document", "Next document", lambda: self.cycle_document(1), next_tab)
        self.action("a_previous_document", "Previous document", lambda: self.cycle_document(-1), previous_tab)

    def make_toolbar(self):
        toolbar = QToolBar("Document tools")
        self.document_toolbar = toolbar
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.addToolBar(toolbar)
        brand = QLabel("  ☀  SOL PDF  ")
        brand.setFont(QFont("", 16, QFont.Weight.Bold))
        toolbar.addWidget(brand)
        toolbar.addSeparator()
        for action in (self.a_open, self.a_save, self.a_undo, self.a_redo):
            toolbar.addAction(action)
        self.filename = QLabel()
        self.filename.setFixedWidth(160)
        self.filename_action = toolbar.addWidget(self.filename)
        spacer = QWidget()
        spacer.setStyleSheet("background: transparent;")
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)
        self.navigation_actions = []
        self.previous_page = QPushButton("‹")
        self.previous_page.setToolTip("Previous page")
        self.previous_page.clicked.connect(lambda: self.go_page(self.current_page - 1))
        self.page_number = QSpinBox()
        self.page_number.setPrefix("Page ")
        self.page_number.setFixedWidth(105)
        self.page_number.valueChanged.connect(lambda number: self.go_page(number - 1))
        self.page_total = QLabel()
        self.next_page = QPushButton("›")
        self.next_page.setToolTip("Next page")
        self.next_page.clicked.connect(lambda: self.go_page(self.current_page + 1))
        self.zoom_box = QComboBox()
        self.zoom_box.addItems(["Fit page", "Fit width", "50%", "75%", "100%", "125%", "150%", "200%"])
        self.zoom_box.currentTextChanged.connect(self.zoom_changed)
        for widget in (self.previous_page, self.page_number, self.page_total, self.next_page, self.zoom_box):
            self.navigation_actions.append(toolbar.addWidget(widget))
        self.edit_toolbar = QToolBar("Edit PDF")
        self.edit_toolbar.setMovable(False)
        self.edit_toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.addToolBarBreak()
        self.addToolBar(self.edit_toolbar)
        self.edit_toolbar.addWidget(QLabel("  Edit PDF  "))
        self.edit_toolbar.addSeparator()
        self.edit_toolbar.addActions([self.a_edit, self.a_add, self.a_image, self.a_resize, self.a_crop])

    def make_body(self):
        self.stack = QStackedWidget()
        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.document_tabs = QTabBar()
        self.document_tabs.setObjectName("documentTabs")
        self.document_tabs.setExpanding(False)
        self.document_tabs.setUsesScrollButtons(True)
        self.document_tabs.setElideMode(Qt.TextElideMode.ElideMiddle)
        self.document_tabs.setTabsClosable(True)
        self.document_tabs.currentChanged.connect(self.activate_document)
        self.document_tabs.tabCloseRequested.connect(self.close_document_tab)
        self.document_tabs.hide()
        outer.addWidget(self.document_tabs)
        outer.addWidget(self.stack)
        self.setCentralWidget(central)
        welcome = QWidget()
        layout = QVBoxLayout(welcome)
        layout.addStretch()
        icon = QLabel()
        icon.setPixmap(sol_icon().pixmap(86, 86))
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon)
        label = QLabel("Sol PDF")
        label.setObjectName("title")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
        layout.addSpacing(22)
        row = QHBoxLayout()
        row.addStretch()
        open_button = QPushButton("Open a PDF")
        open_button.setObjectName("primary")
        open_button.setMinimumWidth(180)
        open_button.clicked.connect(self.open_dialog)
        row.addWidget(open_button)
        new_button = QPushButton("New PDF")
        new_button.clicked.connect(self.new_file)
        row.addWidget(new_button)
        row.addStretch()
        layout.addLayout(row)
        layout.addStretch()
        self.stack.addWidget(welcome)

        workspace = QSplitter()
        self.workspace = workspace
        sidebar = QFrame()
        sidebar.setObjectName("panel")
        side = QVBoxLayout(sidebar)
        title = QLabel("PAGES")
        title.setObjectName("eyebrow")
        side.addWidget(title)
        self.pages = PageList()
        self.pages.setItemDelegate(PageDelegate(self.pages))
        self.pages.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.pages.setIconSize(QSize(126, 164))
        self.pages.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.pages.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.pages.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.pages.setSpacing(4)
        self.pages.currentRowChanged.connect(self.page_changed)
        self.pages.itemSelectionChanged.connect(self.update_actions)
        self.pages.reordered.connect(self.reorder)
        self.pages.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.pages.customContextMenuRequested.connect(self.show_page_menu)
        side.addWidget(self.pages)
        self.page_sidebar = sidebar
        sidebar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        sidebar.customContextMenuRequested.connect(lambda position: self.show_insert_menu(sidebar.mapToGlobal(position)))

        center = QWidget()
        middle = QVBoxLayout(center)
        middle.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        host = QWidget()
        host.setObjectName("canvasHost")
        host_layout = QVBoxLayout(host)
        host_layout.setContentsMargins(24, 24, 24, 24)
        self.canvas = Canvas()
        self.canvas.clicked.connect(self.text_clicked)
        host_layout.addWidget(self.canvas, 0, Qt.AlignmentFlag.AlignCenter)
        self.scroll.setWidget(host)
        middle.addWidget(self.scroll)
        self.find_panel = FindPanel(self.scroll.viewport())
        self.search = self.find_panel.search
        self.find_panel.next_requested.connect(self.find_next)
        self.find_panel.previous_requested.connect(lambda: self.find_next(-1))
        self.find_panel.close_requested.connect(self.close_find)
        self.search.textChanged.connect(self.search_changed)
        self.find_timer = QTimer(self)
        self.find_timer.setSingleShot(True)
        self.find_timer.setInterval(180)
        self.find_timer.timeout.connect(self.find_next)
        self.scroll.viewport().installEventFilter(self)
        workspace.addWidget(center)
        self.inspector = QFrame()
        self.inspector.setObjectName("panel")
        self.inspector.setMinimumWidth(245)
        inspector = QVBoxLayout(self.inspector)
        inspector.setContentsMargins(18, 20, 18, 18)
        label = QLabel("FORMAT")
        label.setObjectName("eyebrow")
        inspector.addWidget(label)
        self.editor = QTextEdit()
        self.editor.setAcceptRichText(False)
        self.editor.setPlaceholderText("Text")
        self.editor.setMinimumHeight(90)
        self.editor.setMaximumHeight(160)
        self.inline_view = PageTextView(self.canvas)
        self.inline_editor = PageTextEditor()
        self.inline_proxy = self.inline_view.scene().addWidget(self.inline_editor)
        self.inline_view.hide()
        self.inline_controls = QWidget(self.canvas)
        self.inline_controls.setStyleSheet("background: transparent;")
        inline_layout = QHBoxLayout(self.inline_controls)
        inline_layout.setContentsMargins(0, 0, 0, 0)
        inline_layout.setSpacing(4)
        for text, callback in (("Apply", self.apply_text), ("Cancel", self.clear_target)):
            button = QPushButton(text)
            button.setToolTip("Command+Enter" if sys.platform == "darwin" and text == "Apply" else "Ctrl+Enter" if text == "Apply" else "Escape")
            button.clicked.connect(callback)
            inline_layout.addWidget(button)
        self.inline_controls.hide()
        self.inline_editor.apply_requested.connect(self.apply_text)
        self.inline_editor.cancel_requested.connect(self.clear_target)
        self.inline_editor.textChanged.connect(self.inline_text_changed)
        self.editor.textChanged.connect(self.side_text_changed)
        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.setInterval(60)
        self.preview_timer.timeout.connect(self.update_text_preview)
        form = QFormLayout()
        self.fonts = QComboBox()
        for label, value in (("Sans serif", "helv"), ("Sans bold", "hebo"),
                ("Sans italic", "heit"), ("Sans bold italic", "hebi"),
                ("Serif", "tiro"), ("Serif bold", "tibo"), ("Serif italic", "tiit"),
                ("Serif bold italic", "tibi"), ("Monospace", "cour"),
                ("Mono bold", "cobo"), ("Mono italic", "coit"), ("Mono bold italic", "cobi")):
            self.fonts.addItem(label, value)
        form.addRow("Font", self.fonts)
        self.font_size = QDoubleSpinBox()
        self.font_size.setRange(4, 144)
        self.font_size.setValue(12)
        self.font_size.setSuffix(" pt")
        form.addRow("Size", self.font_size)
        self.color_button = QPushButton("Text color")
        self.color_button.clicked.connect(self.choose_color)
        form.addRow("Color", self.color_button)
        inspector.addLayout(form)
        style_row = QHBoxLayout()
        self.bold_button = QPushButton("B")
        self.bold_button.setCheckable(True)
        self.bold_button.setFont(QFont("", 13, QFont.Weight.Bold))
        self.bold_button.setToolTip("Bold")
        self.italic_button = QPushButton("I")
        self.italic_button.setCheckable(True)
        italic_font = QFont()
        italic_font.setItalic(True)
        self.italic_button.setFont(italic_font)
        self.italic_button.setToolTip("Italic")
        style_row.addWidget(self.bold_button)
        style_row.addWidget(self.italic_button)
        self.bold_button.toggled.connect(self.set_font_style)
        self.italic_button.toggled.connect(self.set_font_style)
        self.fonts.currentIndexChanged.connect(self.sync_font_style)
        inspector.addLayout(style_row)
        position = QFormLayout()
        self.text_x = QDoubleSpinBox()
        self.text_y = QDoubleSpinBox()
        for field in (self.text_x, self.text_y):
            field.setRange(0, 10000)
            field.setDecimals(2)
            field.setSuffix(" pt")
        position.addRow("X", self.text_x)
        position.addRow("Y", self.text_y)
        self.line_spacing = QDoubleSpinBox()
        self.line_spacing.setRange(.8, 3)
        self.line_spacing.setSingleStep(.1)
        self.line_spacing.setValue(1.2)
        position.addRow("Line spacing", self.line_spacing)
        self.alignment = QComboBox()
        self.alignment.addItems(["Left", "Center", "Right"])
        position.addRow("Alignment", self.alignment)
        inspector.addLayout(position)
        text_label = QLabel("TEXT")
        self.text_label = text_label
        text_label.setObjectName("eyebrow")
        inspector.addWidget(text_label)
        inspector.addWidget(self.editor)
        self.apply_button = QPushButton("Apply text")
        self.apply_button.setObjectName("primary")
        self.apply_button.clicked.connect(self.apply_text)
        inspector.addWidget(self.apply_button)
        cancel_button = QPushButton("Clear selection")
        self.clear_selection_button = cancel_button
        cancel_button.clicked.connect(self.clear_target)
        inspector.addWidget(cancel_button)
        self.bounds_check = QCheckBox("Show text outlines")
        self.bounds_check.setChecked(True)
        self.bounds_check.toggled.connect(self.toggle_bounds)
        inspector.addWidget(self.bounds_check)
        inspector.addStretch()
        for field in (self.font_size, self.text_x, self.text_y, self.line_spacing):
            field.valueChanged.connect(self.schedule_text_preview)
        self.fonts.currentIndexChanged.connect(self.schedule_text_preview)
        self.alignment.currentIndexChanged.connect(self.schedule_text_preview)
        self.workspace_tabs = QTabWidget()
        self.workspace_tabs.setMinimumWidth(280)
        self.workspace_tabs.setMaximumWidth(400)
        self.workspace_tabs.addTab(sidebar, "View / Organize")
        self.inspector_scroll = QScrollArea()
        self.inspector_scroll.setWidgetResizable(True)
        self.inspector_scroll.setWidget(self.inspector)
        self.inspector_scroll.setStyleSheet("QScrollArea { background: white; border: 0; }")
        self.workspace_tabs.addTab(self.inspector_scroll, "Edit")
        self.workspace_tabs.currentChanged.connect(self.workspace_tab_changed)
        workspace.addWidget(self.workspace_tabs)
        workspace.setSizes([1050, 300])
        workspace.setStretchFactor(0, 1)
        self.sidebar_width = 300
        self.sidebar_reopen = QPushButton("‹", center)
        self.sidebar_reopen.setFixedSize(32, 48)
        self.sidebar_reopen.setToolTip("Show right sidebar")
        self.sidebar_reopen.setAccessibleName("Show right sidebar")
        self.sidebar_reopen.setStyleSheet("QPushButton { background: white; color: #1765b5; font-size: 24px; padding: 0; border: 1px solid #bcc7c1; border-radius: 4px; }")
        self.sidebar_reopen.clicked.connect(self.restore_sidebar)
        self.sidebar_reopen.hide()
        self.workspace_tabs.installEventFilter(self)
        workspace.splitterMoved.connect(self.sync_sidebar)
        self.stack.addWidget(workspace)
        self.set_mode("view")

    def sync_sidebar(self, *args):
        if not hasattr(self, "sidebar_reopen"):
            return
        width = self.workspace.sizes()[1]
        if width:
            self.sidebar_width = width
        self.sidebar_reopen.move(max(0, self.workspace.widget(0).width() - 34), 12)
        self.sidebar_reopen.setVisible(width == 0 and self.model.doc is not None)
        self.sidebar_reopen.raise_()

    def restore_sidebar(self):
        if not self.model.doc:
            return
        width = max(280, min(400, self.sidebar_width))
        self.workspace.setSizes([max(1, self.workspace.width() - width), width])
        self.sync_sidebar()

    def make_menus(self):
        file = self.menuBar().addMenu("File")
        file.addActions([self.a_new, self.a_open, self.a_save, self.a_save_as, self.a_close])
        file.addSeparator()
        quit_action = file.addAction("Quit")
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        edit = self.menuBar().addMenu("Edit")
        edit.addActions([self.a_undo, self.a_redo, self.a_edit, self.a_add, self.a_image, self.a_find])
        pages = self.menuBar().addMenu("Pages")
        self.pages_menu = pages
        pages.addActions([self.a_blank, self.a_import])
        pages.addActions([self.a_resize, self.a_crop])
        pages.addSeparator()
        self.add_rotation_menu(pages)
        pages.addActions([self.a_delete, self.a_duplicate, self.a_extract])
        view = self.menuBar().addMenu("View")
        view.addActions([self.a_view_mode, self.a_edit_mode])
        view.addAction(self.a_show_sidebar)
        view.addActions([self.a_next_document, self.a_previous_document])
        help_menu = self.menuBar().addMenu("Help")
        help_menu.addAction("About Sol PDF", lambda: QMessageBox.about(self, "Sol PDF",
            "<b>Sol PDF 0.1.0</b><br>Local PDF editing for everyday work.<br><br>"
            "Page management, text editing, undo and redo.<br>"
            "Open-source software · AGPL-3.0-or-later<br>"
            "Powered by PySide6 and PyMuPDF.<br><br>"
            "Text editing supports horizontal selectable text. OCR, complex text reflow, "
            "signature preservation and form editing are not included."))

    def error(self, error):
        QMessageBox.warning(self, "Sol PDF", str(error))

    def guard_unsaved(self):
        if not self.model.dirty:
            return True
        name = self.document_name()
        answer = QMessageBox.question(self, "Save your changes?", f"{name} has unsaved changes.",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save)
        if answer == QMessageBox.StandardButton.Save:
            return self.save_file()
        return answer == QMessageBox.StandardButton.Discard

    def open_dialog(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Open PDFs", "", "PDF files (*.pdf)")
        for path in paths:
            self.open_file(path)

    def open_file(self, path):
        path = Path(path)
        for index, document in enumerate(self.documents):
            if document["model"].path and document["model"].path.resolve() == path.resolve():
                self.activate_document(index)
                return
        model = PDFDocument()
        password = ""
        while True:
            try:
                model.open(path, password)
                break
            except PasswordRequired:
                password, ok = QInputDialog.getText(self, "Unlock PDF", "PDF password:", QLineEdit.EchoMode.Password)
                if not ok:
                    return
            except Exception as error:
                self.error(error)
                return
        self.add_document(model, "view")
        if self.model.was_encrypted:
            self.statusBar().showMessage("Password-protected PDF opened · Save As creates an unlocked copy")
        else:
            self.statusBar().clearMessage()

    def new_file(self):
        model = PDFDocument()
        model.new()
        self.add_document(model, "view")

    def add_document(self, model, mode):
        title = ""
        if model.path is None:
            self.untitled_count += 1
            title = "Untitled.pdf" if self.untitled_count == 1 else f"Untitled {self.untitled_count}.pdf"
        document = {"model": model, "state": None, "initial_mode": mode, "title": title}
        self.documents.append(document)
        self.document_tabs.blockSignals(True)
        self.document_tabs.addTab(self.document_name(document))
        self.document_tabs.blockSignals(False)
        self.document_tabs.show()
        self.activate_document(len(self.documents) - 1)

    def document_name(self, document=None):
        document = document or self.active_document
        if document is None:
            return "Untitled.pdf"
        return document["model"].path.name if document["model"].path else document["title"]

    def remember_document(self):
        if self.active_document is None:
            return
        self.find_timer.stop()
        self.active_document["state"] = {
            "page": self.current_page, "mode": self.mode, "tool": self.last_edit_tool,
            "zoom": self.zoom_box.currentText(), "target": self.target,
            "draft": self.editor.toPlainText(), "font": self.fonts.currentIndex(),
            "size": self.font_size.value(), "color": QColor(self.text_color),
            "x": self.text_x.value(), "y": self.text_y.value(),
            "spacing": self.line_spacing.value(), "alignment": self.alignment.currentIndex(),
            "bounds": self.bounds_check.isChecked(), "selection": self.selected_pages(),
            "scroll": (self.scroll.horizontalScrollBar().value(), self.scroll.verticalScrollBar().value()),
            "query": self.search.text(), "find_visible": self.find_panel.isVisible(),
            "hits": list(self.search_hits), "hit_index": self.search_index,
            "find_count": self.find_panel.count.text(),
        }

    def activate_document(self, index):
        if not 0 <= index < len(self.documents):
            return
        document = self.documents[index]
        self.document_tabs.blockSignals(True)
        self.document_tabs.setCurrentIndex(index)
        self.document_tabs.blockSignals(False)
        if document is self.active_document:
            return
        self.remember_document()
        if getattr(self, "page_popup", None):
            self.page_popup.close()
        self.close_find(clear_query=True)
        self.active_document = document
        self.model = document["model"]
        self.statusBar().clearMessage()
        state = document["state"]
        self.current_page = state["page"] if state else 0
        self.last_edit_tool = state["tool"] if state else "edit"
        self.zoom_box.blockSignals(True)
        self.zoom_box.setCurrentText(state["zoom"] if state else "Fit page")
        self.zoom_box.blockSignals(False)
        if self.zoom_box.currentText().endswith("%"):
            self.zoom = int(self.zoom_box.currentText()[:-1]) / 100
        self.set_mode(state["mode"] if state else document["initial_mode"])
        self.refresh()
        if state:
            self.pages.blockSignals(True)
            self.pages.clearSelection()
            for page in state["selection"]:
                self.pages.item(page).setSelected(True)
            self.pages.blockSignals(False)
            self.fonts.setCurrentIndex(state["font"])
            self.font_size.setValue(state["size"])
            self.text_color = QColor(state["color"])
            self.update_color_button()
            self.text_x.setValue(state["x"])
            self.text_y.setValue(state["y"])
            self.line_spacing.setValue(state["spacing"])
            self.alignment.setCurrentIndex(state["alignment"])
            self.bounds_check.setChecked(state["bounds"])
            self.target = state["target"]
            self.editor.setPlainText(state["draft"])
            self.canvas.selected = self.target if self.mode == "edit" else None
            self.search.blockSignals(True)
            self.search.setText(state["query"])
            self.search.blockSignals(False)
            self.search_hits = list(state["hits"])
            self.search_index = state["hit_index"]
            self.find_panel.count.setText(state["find_count"])
            self.canvas.search_rects = [rect for page, rect in self.search_hits if page == self.current_page]
            if state["find_visible"]:
                self.find_panel.position_panel()
                self.find_panel.show()
                self.find_panel.raise_()
                if state["query"].strip() and not state["hits"]:
                    self.find_timer.start()
            def restore_scroll():
                if self.active_document is document:
                    self.scroll.horizontalScrollBar().setValue(state["scroll"][0])
                    self.scroll.verticalScrollBar().setValue(state["scroll"][1])
            QTimer.singleShot(0, restore_scroll)
        else:
            self.fonts.setCurrentIndex(0)
            self.font_size.setValue(12)
            self.text_color = QColor("#202d36")
            self.update_color_button()
            self.text_x.setValue(0)
            self.text_y.setValue(0)
            self.line_spacing.setValue(1.2)
            self.alignment.setCurrentIndex(0)
            self.bounds_check.setChecked(True)
            self.scroll.horizontalScrollBar().setValue(0)
            self.scroll.verticalScrollBar().setValue(0)
        self.line_spacing.setEnabled(self.mode == "add")
        self.alignment.setEnabled(self.mode == "add")
        self.update_actions()
        self.schedule_text_preview()

    def cycle_document(self, direction):
        if self.documents:
            self.activate_document((self.documents.index(self.active_document) + direction) % len(self.documents))

    def save_file(self, save_as=False):
        if not self.model.doc:
            return False
        path = None
        if save_as or self.model.path is None or self.model.was_encrypted:
            default = str(self.model.path.with_name(self.model.path.stem + " - edited.pdf")) if self.model.path else self.document_name()
            path, _ = QFileDialog.getSaveFileName(self, "Save PDF", default, "PDF files (*.pdf)")
            if not path:
                return False
            if not path.lower().endswith(".pdf"):
                path += ".pdf"
        try:
            self.model.save(path)
            self.update_actions()
            self.statusBar().showMessage("Saved · " + str(self.model.path))
            return True
        except Exception as error:
            self.error(error)
            return False

    def close_document(self):
        if self.active_document is not None:
            self.close_document_tab(self.documents.index(self.active_document))

    def close_document_tab(self, index):
        if not 0 <= index < len(self.documents):
            return
        previous = self.active_document
        self.activate_document(index)
        if self.guard_unsaved():
            closing = self.active_document
            self.close_find(clear_query=True)
            self.generation += 1
            closing["model"].doc.close()
            self.active_document = None
            self.documents.pop(index)
            self.document_tabs.blockSignals(True)
            self.document_tabs.removeTab(index)
            self.document_tabs.blockSignals(False)
            if self.documents:
                target = next((i for i, document in enumerate(self.documents) if document is previous), min(index, len(self.documents) - 1))
                self.activate_document(target)
                return
            self.model = PDFDocument()
            self.set_mode("view")
            self.document_tabs.hide()
            self.stack.setCurrentIndex(0)
            self.update_actions()

    def closeEvent(self, event):
        for index, document in enumerate(self.documents):
            if document["model"].dirty:
                self.activate_document(index)
                if not self.guard_unsaved():
                    event.ignore()
                    return
        self.find_timer.stop()
        self.generation += 1
        for document in self.documents:
            document["model"].doc.close()
        self.model = PDFDocument()
        self.active_document = None
        self.documents.clear()
        event.accept()

    def selected_pages(self):
        return sorted(self.pages.row(item) for item in self.pages.selectedItems()) or [self.current_page]

    def add_rotation_menu(self, menu):
        rotation = QMenu("Rotate", menu)
        menu.addMenu(rotation)
        menu.rotation_menu = rotation
        rotation.addActions(self.rotation_actions)
        rotation.addSeparator()
        rotation.addActions(self.flip_actions)
        return rotation

    def page_context_menu(self, row):
        if not self.model.doc or not 0 <= row < self.pages.count():
            return None
        item = self.pages.item(row)
        if item.isSelected():
            self.pages.setCurrentItem(item, QItemSelectionModel.SelectionFlag.NoUpdate)
        else:
            self.pages.setCurrentItem(item, QItemSelectionModel.SelectionFlag.ClearAndSelect)
        self.update_actions()
        multiple = len(self.selected_pages()) > 1
        self.a_delete.setText("Delete pages" if multiple else "Delete page")
        self.a_duplicate.setText("Duplicate pages" if multiple else "Duplicate page")
        self.a_extract.setText("Extract pages…" if multiple else "Extract page…")
        menu = QMenu(self.pages)
        self.add_rotation_menu(menu)
        menu.addActions([self.a_resize, self.a_crop])
        menu.addSeparator()
        menu.addActions([self.a_delete, self.a_duplicate, self.a_extract])
        return menu

    def show_page_menu(self, position):
        item = self.pages.itemAt(position)
        if item is None:
            self.show_insert_menu(self.pages.viewport().mapToGlobal(position))
            return
        menu = self.page_context_menu(self.pages.row(item))
        if menu is not None:
            previous = getattr(self, "page_popup", None)
            if previous is not None:
                previous.close()
                previous.deleteLater()
            self.page_popup = menu
            menu.popup(self.pages.viewport().mapToGlobal(position))

    def insert_context_menu(self):
        menu = QMenu(self.page_sidebar)
        menu.addActions([self.a_blank, self.a_import])
        return menu

    def show_insert_menu(self, position):
        if not self.model.doc or self.mode != "view":
            return
        previous = getattr(self, "page_popup", None)
        if previous is not None:
            previous.close()
            previous.deleteLater()
        self.page_popup = self.insert_context_menu()
        self.page_popup.popup(position)

    def rotate_pages(self, degrees):
        self.mutate(lambda: self.model.rotate(self.selected_pages(), degrees))

    def flip_pages(self, horizontal):
        self.mutate(lambda: self.model.flip(self.selected_pages(), horizontal))

    def duplicate_pages(self):
        pages = self.selected_pages()
        self.mutate(lambda: self.model.duplicate_pages(pages), min(pages) + 1)

    def mutate(self, operation, target=None):
        if not self.model.doc:
            return False
        try:
            operation()
            if target is not None:
                self.current_page = target
            self.clear_search()
            self.refresh()
            self.statusBar().clearMessage()
            return True
        except Exception as error:
            self.error(error)
            return False

    def undo(self):
        self.mutate(self.model.undo)

    def redo(self):
        self.mutate(self.model.redo)

    def delete_pages(self):
        if not self.model.doc:
            return
        pages = self.selected_pages()
        self.mutate(lambda: self.model.delete(pages), min(pages))

    def blank_page(self):
        if not self.model.doc:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Add a blank page")
        layout = QFormLayout(dialog)
        sizes = QComboBox()
        sizes.addItems(["Match current page", "US Letter", "A4", "US Legal"])
        layout.addRow("Page size", sizes)
        landscape = QComboBox()
        landscape.addItems(["Portrait", "Landscape"])
        layout.addRow("Orientation", landscape)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            dimensions = [None, (612, 792), (595.28, 841.89), (612, 1008)][sizes.currentIndex()]
            if dimensions and landscape.currentIndex():
                dimensions = dimensions[::-1]
            self.mutate(lambda: self.model.blank(self.current_page, *(dimensions or (None, None))), self.current_page + 1)

    def import_pdf(self):
        if not self.model.doc:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Insert pages from PDF", "", "PDF files (*.pdf)")
        if not path:
            return
        password = ""
        while True:
            try:
                with fitz.open(path) as source:
                    if source.needs_pass and not source.authenticate(password):
                        raise PasswordRequired()
                    count = len(source)
                break
            except PasswordRequired:
                password, ok = QInputDialog.getText(self, "Unlock imported PDF", "PDF password:", QLineEdit.EchoMode.Password)
                if not ok:
                    return
            except Exception as error:
                self.error(error)
                return
        ranges, ok = QInputDialog.getText(self, "Choose pages to insert",
            f"Pages (1-{count}), e.g. 1, 3-5. Insert after page {self.current_page + 1}:",
            text=f"1-{count}")
        if ok:
            try:
                pages = parse_pages(ranges, count)
                self.mutate(lambda: self.model.import_pages(path, self.current_page, pages, password), self.current_page + 1)
            except Exception as error:
                self.error(error)

    def extract_pages(self):
        if not self.model.doc:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Extract selected pages", "Extracted pages.pdf", "PDF files (*.pdf)")
        if path:
            if not path.lower().endswith(".pdf"):
                path += ".pdf"
            if self.model.path and Path(path).resolve() == self.model.path.resolve():
                self.error("Choose a different file for extracted pages.")
                return
            try:
                self.model.extract(self.selected_pages(), path)
                self.statusBar().showMessage("Selected pages saved to " + path)
            except Exception as error:
                self.error(error)

    def reorder(self, order):
        item = self.pages.currentItem()
        original = item.data(Qt.ItemDataRole.UserRole) if item else self.current_page
        if not self.mutate(lambda: self.model.reorder(order), order.index(original)):
            self.refresh()

    def move_page(self, direction):
        if not self.model.doc:
            return
        target = self.current_page + direction
        if 0 <= target < self.model.count:
            order = list(range(self.model.count))
            order[self.current_page], order[target] = order[target], order[self.current_page]
            self.mutate(lambda: self.model.reorder(order), target)

    def refresh(self):
        self.generation += 1
        generation = self.generation
        self.stack.setCurrentIndex(1)
        self.current_page = min(max(0, self.current_page), self.model.count - 1)
        self.pages.blockSignals(True)
        self.pages.clear()
        for index in range(self.model.count):
            item = QListWidgetItem(f"Page {index + 1}")
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item.setData(Qt.ItemDataRole.UserRole, index)
            item.setSizeHint(QSize(160, 194))
            self.pages.addItem(item)
        self.pages.setCurrentRow(self.current_page)
        self.pages.blockSignals(False)
        self.page_number.blockSignals(True)
        self.page_number.setRange(1, self.model.count)
        self.page_number.setValue(self.current_page + 1)
        self.page_number.blockSignals(False)
        self.page_total.setText(f"of {self.model.count}")
        self.render_page()
        self.update_actions()
        # Render thumbnails in event-loop batches, starting with the current page.
        queue = [self.current_page] + [i for i in range(self.model.count) if i != self.current_page]
        def batch():
            if generation != self.generation or not self.model.doc:
                return
            for _ in range(min(3, len(queue))):
                index = queue.pop(0)
                try:
                    page = self.model.doc[index]
                    scale = min(126 / page.rect.width, 150 / page.rect.height)
                    self.pages.item(index).setIcon(QIcon(pixmap(page, scale)))
                except Exception:
                    self.pages.item(index).setToolTip("Preview unavailable")
            if queue:
                QTimer.singleShot(0, batch)
        QTimer.singleShot(0, batch)

    def update_actions(self):
        active = self.model.doc is not None
        self.a_show_sidebar.setEnabled(active)
        self.sync_sidebar()
        editing = active and self.mode != "view"
        for action in (self.a_save, self.a_save_as, self.a_find, self.a_close,
                       self.a_view_mode, self.a_edit_mode):
            action.setEnabled(active)
        for action in (self.a_edit, self.a_add, self.a_image):
            action.setEnabled(editing)
        for action in (self.a_blank,
                self.a_import, self.a_delete, *self.rotation_actions, *self.flip_actions,
                self.a_duplicate, self.a_extract, self.a_resize, self.a_crop):
            action.setEnabled(active)
        self.filename_action.setVisible(False)
        self.a_next_document.setEnabled(len(self.documents) > 1)
        self.a_previous_document.setEnabled(len(self.documents) > 1)
        for index, document in enumerate(self.documents):
            model = document["model"]
            label = self.document_name(document)
            self.document_tabs.setTabText(index, label + (" •" if model.dirty else ""))
            self.document_tabs.setTabToolTip(index, str(model.path or label))
        for action in self.navigation_actions:
            action.setVisible(active)
        self.previous_page.setEnabled(active and self.current_page > 0)
        self.next_page.setEnabled(active and self.current_page < self.model.count - 1)
        self.a_undo.setEnabled(active and bool(self.model.undo_stack))
        self.a_redo.setEnabled(active and bool(self.model.redo_stack))
        if self.model.undo_stack:
            self.a_undo.setToolTip("Undo: " + self.model.undo_stack[-1].label)
        if active:
            self.a_delete.setEnabled(len(self.selected_pages()) < self.model.count)
        name = self.document_name()
        marker = " •" if self.model.dirty else ""
        self.setWindowTitle(f"{name}{marker} — Sol PDF" if active else "Sol PDF")
        if hasattr(self, "filename"):
            self.filename.setText(self.filename.fontMetrics().elidedText(name + marker, Qt.TextElideMode.ElideMiddle, 156))
            self.filename.setToolTip(str(self.model.path or name))
        if hasattr(self, "apply_button"):
            self.apply_button.setEnabled(editing and self.target is not None)

    def render_page(self, preserve_target=False):
        if not self.model.doc:
            return
        page = self.model.doc[self.current_page]
        width = max(200, self.scroll.viewport().width() - 64)
        height = max(200, self.scroll.viewport().height() - 64)
        if self.zoom_box.currentText() == "Fit page":
            scale = min(width / page.rect.width, height / page.rect.height)
        elif self.zoom_box.currentText() == "Fit width":
            scale = width / page.rect.width
        else:
            scale = self.zoom
        # Bound memory for very large-format drawings.
        scale = min(scale, math.sqrt(16_000_000 / page.rect.get_area()))
        try:
            target = self.target if preserve_target else None
            spans = self.model.spans(self.current_page)
            self.canvas.set_page(page, scale, spans)
            self.canvas.search_rects = [rect for index, rect in self.search_hits if index == self.current_page]
            if target is not None:
                self.canvas.selected = target if self.mode == "edit" else None
            elif not preserve_target:
                self.clear_target()
            if self.mode == "edit" and not spans:
                self.statusBar().showMessage("No selectable text on this page · Scans require OCR")
            self.schedule_text_preview()
        except Exception as error:
            self.error(error)

    def page_changed(self, row):
        if row >= 0 and self.model.doc:
            self.current_page = row
            self.page_number.blockSignals(True)
            self.page_number.setValue(row + 1)
            self.page_number.blockSignals(False)
            self.render_page()
            self.scroll.verticalScrollBar().setValue(0)
            self.update_actions()

    def go_page(self, index):
        if self.model.doc and 0 <= index < self.model.count:
            if self.pages.currentRow() != index:
                self.pages.setCurrentRow(index)

    def zoom_changed(self, value):
        if value.endswith("%"):
            self.zoom = int(value[:-1]) / 100
        self.render_page(preserve_target=True)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.sync_sidebar()
        if hasattr(self, "zoom_box") and self.zoom_box.currentText().startswith("Fit"):
            QTimer.singleShot(0, lambda: self.render_page(preserve_target=True))

    def eventFilter(self, watched, event):
        if hasattr(self, "workspace_tabs") and watched is self.workspace_tabs and event.type() == QEvent.Type.Resize:
            QTimer.singleShot(0, self.sync_sidebar)
        if hasattr(self, "scroll") and watched is self.scroll.viewport() and event.type() == QEvent.Type.Resize:
            self.sync_sidebar()
            QTimer.singleShot(0, lambda: self.render_page(preserve_target=True))
        return super().eventFilter(watched, event)

    def set_mode(self, mode):
        if mode not in ("view", "edit", "add"):
            raise ValueError("Unknown mode")
        self.mode = mode
        editing = mode != "view"
        if editing:
            self.last_edit_tool = mode
        self.a_view_mode.setChecked(not editing)
        self.a_edit_mode.setChecked(editing)
        self.a_edit.setChecked(mode == "edit")
        self.a_add.setChecked(mode == "add")
        for action in (self.a_edit, self.a_add, self.a_image):
            action.setVisible(editing)
        self.edit_toolbar.setVisible(editing)
        if hasattr(self, "canvas"):
            self.workspace_tabs.blockSignals(True)
            self.workspace_tabs.setCurrentIndex(1 if editing else 0)
            self.workspace_tabs.blockSignals(False)
            self.pages.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
            self.pages.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
            self.canvas.mode = mode
            self.clear_target()
            for widget in (self.editor, self.text_label, self.apply_button, self.clear_selection_button):
                widget.setVisible(mode != "add")
            self.canvas.update()
            self.update_actions()
            # Fit against the expanded/collapsed workspace after Qt lays it out.
            QTimer.singleShot(0, lambda: self.render_page(preserve_target=True))

    def workspace_tab_changed(self, index):
        self.set_mode(self.last_edit_tool if index == 1 else "view")

    def sync_font_style(self):
        font = self.fonts.currentData()
        self.bold_button.blockSignals(True)
        self.italic_button.blockSignals(True)
        self.bold_button.setChecked(font in ("hebo", "hebi", "tibo", "tibi", "cobo", "cobi"))
        self.italic_button.setChecked(font in ("heit", "hebi", "tiit", "tibi", "coit", "cobi"))
        self.bold_button.blockSignals(False)
        self.italic_button.blockSignals(False)

    def set_font_style(self):
        current = self.fonts.currentData()
        family = ("cour", "cobo", "coit", "cobi") if current in ("cour", "cobo", "coit", "cobi") else (
            ("tiro", "tibo", "tiit", "tibi") if current in ("tiro", "tibo", "tiit", "tibi") else
            ("helv", "hebo", "heit", "hebi"))
        style = int(self.bold_button.isChecked()) + 2 * int(self.italic_button.isChecked())
        self.fonts.setCurrentIndex(self.fonts.findData(family[style]))

    def toggle_bounds(self, checked):
        self.canvas.show_bounds = checked
        self.canvas.update()

    def clear_target(self):
        self.target = None
        if hasattr(self, "preview_timer"):
            self.preview_timer.stop()
            self.inline_view.hide()
            self.inline_controls.hide()
            if hasattr(self.canvas, "base_image"):
                self.canvas.image = self.canvas.base_image
        self.canvas.selected = None
        self.editor.clear()
        self.apply_button.setEnabled(False)
        self.canvas.update()

    def text_clicked(self, target):
        if self.mode == "view":
            return
        self.target = target
        self.apply_button.setEnabled(target is not None)
        if target is None:
            return
        if self.mode == "edit":
            self.editor.setPlainText(target.text)
            self.font_size.setValue(target.size)
            self.fonts.setCurrentIndex(max(0, self.fonts.findData(self.model.standard_font(target.font))))
            self.text_color = QColor.fromRgb(target.color)
            origin = target.origin
        else:
            origin = target
        self.text_x.setValue(origin[0])
        self.text_y.setValue(origin[1])
        self.update_color_button()
        self.line_spacing.setEnabled(self.mode == "add")
        self.alignment.setEnabled(self.mode == "add")
        if self.mode == "add":
            self.update_text_preview()
            self.inline_editor.setFocus()
        else:
            self.editor.setFocus()

    def choose_color(self):
        color = QColorDialog.getColor(self.text_color, self, "Text color")
        if color.isValid():
            self.text_color = color
            self.update_color_button()

    def update_color_button(self):
        swatch = QPixmap(16, 16)
        swatch.fill(self.text_color)
        self.color_button.setIcon(QIcon(swatch))
        self.color_button.setText("Text color")
        self.schedule_text_preview()

    def inline_text_changed(self):
        self.editor.blockSignals(True)
        self.editor.setPlainText(self.inline_editor.toPlainText())
        self.editor.blockSignals(False)
        self.schedule_text_preview()

    def side_text_changed(self):
        if self.inline_editor.toPlainText() != self.editor.toPlainText():
            self.inline_editor.blockSignals(True)
            self.inline_editor.setPlainText(self.editor.toPlainText())
            self.inline_editor.blockSignals(False)
        self.schedule_text_preview()

    def schedule_text_preview(self, *args):
        if hasattr(self, "preview_timer") and self.mode == "add" and self.target is not None:
            self.preview_timer.start()

    def update_text_preview(self):
        if self.mode != "add" or self.target is None or not self.model.doc:
            return
        self.preview_timer.stop()
        page = self.model.doc[self.current_page]
        text = self.editor.toPlainText()
        size = self.font_size.value()
        fontname = self.fonts.currentData()
        origin = (self.text_x.value(), self.text_y.value())
        color = (self.text_color.redF(), self.text_color.greenF(), self.text_color.blueF())
        scale = self.canvas.scale
        font, _ = self.model._font(text, fontname)
        widths = [font.text_length(line, fontsize=size) for line in text.splitlines() or [""]]
        family = "Courier" if fontname.startswith("co") or fontname == "cour" else "Times New Roman" if fontname.startswith("ti") else "Helvetica"
        qt_font = QFont(family)
        qt_font.setPointSizeF(max(.1, size * scale * 72 / self.inline_editor.logicalDpiY()))
        qt_font.setBold(self.bold_button.isChecked())
        qt_font.setItalic(self.italic_button.isChecked())
        self.inline_editor.blockSignals(True)
        self.inline_editor.setFont(qt_font)
        self.inline_editor.caret_color = QColor(self.text_color)
        # Keep PDF-rendered glyphs visible through selection instead of painting
        # a second, differently sized set of Qt glyphs over the preview.
        self.inline_editor.setStyleSheet("QTextEdit { background: transparent; color: transparent; border: 1px dashed #2475db; border-radius: 0; padding: 0; selection-color: transparent; selection-background-color: transparent; }")
        # The application stylesheet sets a UI font size. Restore the document's
        # page-scaled font after styling so caret and selection follow the PDF.
        self.inline_editor.document().setDefaultFont(qt_font)
        block = QTextBlockFormat()
        block.setLineHeight(size * scale * self.line_spacing.value(), QTextBlockFormat.LineHeightTypes.FixedHeight.value)
        block.setAlignment((Qt.AlignmentFlag.AlignLeft, Qt.AlignmentFlag.AlignHCenter, Qt.AlignmentFlag.AlignRight)[self.alignment.currentIndex()])
        cursor = self.inline_editor.textCursor()
        saved_cursor = self.inline_editor.textCursor()
        cursor.select(cursor.SelectionType.Document)
        self.inline_editor.blockSignals(True)
        cursor.mergeBlockFormat(block)
        self.inline_editor.setTextCursor(saved_cursor)
        self.inline_editor.blockSignals(False)
        lines = max(1, len(text.split("\n")))
        width = max(130 if not text else 24, max(widths) * scale + 12)
        height = max(32, size * scale * (self.line_spacing.value() * (lines - 1) + font.ascender - font.descender) + 12)
        self.inline_editor.setFixedSize(math.ceil(width), math.ceil(height))
        self.inline_view.setGeometry(self.canvas.rect())
        self.inline_view.setSceneRect(QRectF(self.canvas.rect()))
        top_left = fitz.Point(origin[0] - 5 / scale, origin[1] - (QFontMetricsF(qt_font).ascent() + 5) / scale) * page.rotation_matrix
        self.inline_proxy.setRotation(page.rotation)
        self.inline_proxy.setPos(top_left.x * scale, top_left.y * scale)
        self.inline_view.show()
        self.inline_view.raise_()
        bounds = self.inline_proxy.sceneBoundingRect()
        self.inline_controls.adjustSize()
        self.inline_controls.move(max(0, min(round(bounds.left()), self.canvas.width() - self.inline_controls.width())),
            max(0, min(round(bounds.bottom() + 5), self.canvas.height() - self.inline_controls.height())))
        self.inline_controls.show()
        self.inline_controls.raise_()
        self.canvas.image = self.canvas.base_image
        if text.strip():
            preview = PDFDocument()
            preview.doc = fitz.open()
            try:
                preview.doc.insert_pdf(self.model.doc, from_page=self.current_page, to_page=self.current_page)
                preview.add_text(0, origin, text, size, fontname, color,
                    line_spacing=self.line_spacing.value(), align=self.alignment.currentIndex())
                self.canvas.image = pixmap(preview.doc[0], scale)
                self.statusBar().clearMessage()
            except PDFError as error:
                self.statusBar().showMessage(str(error))
                # Show the clipped draft even when its current bounds cannot be applied.
                for number, line in enumerate(text.splitlines()):
                    offset = 0 if self.alignment.currentIndex() == 0 else (max(widths) - widths[number]) * (.5 if self.alignment.currentIndex() == 1 else 1)
                    preview._insert(preview.doc[0], line,
                        (origin[0] + offset, origin[1] + number * size * self.line_spacing.value()), size, fontname, color)
                self.canvas.image = pixmap(preview.doc[0], scale)
            finally:
                preview.doc.close()
        self.canvas.update()

    def apply_text(self):
        if self.target is None:
            return
        text = self.editor.toPlainText()
        color = (self.text_color.redF(), self.text_color.greenF(), self.text_color.blueF())
        if self.mode == "edit":
            self.mutate(lambda: self.model.replace_text(self.current_page, self.target, text,
                self.font_size.value(), self.fonts.currentData(), color,
                origin=(self.text_x.value(), self.text_y.value())))
        elif self.mode == "add":
            self.mutate(lambda: self.model.add_text(self.current_page,
                (self.text_x.value(), self.text_y.value()), text,
                self.font_size.value(), self.fonts.currentData(), color,
                line_spacing=self.line_spacing.value(), align=self.alignment.currentIndex()))

    def add_image(self):
        if not self.model.doc:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Add image", "", "Images (*.png *.jpg *.jpeg)")
        if not path:
            return
        image = QImage(path)
        if image.isNull():
            self.error("This image could not be opened.")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Add image")
        form = QFormLayout(dialog)
        fields = []
        for label, value in (("X", 54), ("Y", 54), ("Width", min(240, self.model.doc[self.current_page].cropbox.width - 108))):
            field = QDoubleSpinBox()
            field.setRange(0 if label != "Width" else 1, 10000)
            field.setSuffix(" pt")
            field.setValue(value)
            form.addRow(label, field)
            fields.append(field)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.mutate(lambda: self.model.add_image(self.current_page, path,
                (fields[0].value(), fields[1].value()), fields[2].value()))

    def resize_page(self):
        if not self.model.doc:
            return
        page = self.model.doc[self.current_page]
        dialog = QDialog(self)
        dialog.setWindowTitle("Resize current page")
        form = QFormLayout(dialog)
        sizes = QComboBox()
        sizes.addItems(["Custom", "US Letter", "A4", "US Legal"])
        form.addRow("Page size", sizes)
        orientation = QComboBox()
        orientation.addItems(["Portrait", "Landscape"])
        orientation.setCurrentIndex(int(page.rect.width > page.rect.height))
        form.addRow("Orientation", orientation)
        units = QComboBox()
        units.addItems(["Inches", "Millimeters", "Points"])
        form.addRow("Units", units)
        dimensions = []
        for label, value in (("Width", page.rect.width), ("Height", page.rect.height)):
            field = QDoubleSpinBox()
            field.setObjectName(label.lower())
            field.setDecimals(3)
            field.setRange(20 / 72, 14400 / 72)
            field.setValue(value / 72)
            form.addRow(label, field)
            dimensions.append(field)
        factors = [72, 72 / 25.4, 1]
        current_factor = [72]
        def change_units(index):
            factor = factors[index]
            for field in dimensions:
                value = field.value() * current_factor[0]
                field.setRange(20 / factor, 14400 / factor)
                field.setValue(value / factor)
            current_factor[0] = factor
        units.currentIndexChanged.connect(change_units)
        def preset():
            if sizes.currentIndex():
                width, height = {1: (612, 792), 2: (595.276, 841.89), 3: (612, 1008)}[sizes.currentIndex()]
                if orientation.currentIndex():
                    width, height = height, width
                for field, value in zip(dimensions, (width, height)):
                    field.setValue(value / current_factor[0])
            elif (dimensions[0].value() > dimensions[1].value()) != bool(orientation.currentIndex()):
                width, height = [field.value() for field in dimensions]
                dimensions[0].setValue(height)
                dimensions[1].setValue(width)
        sizes.currentIndexChanged.connect(preset)
        orientation.currentIndexChanged.connect(preset)
        fit_content = QCheckBox("Scale content to fit")
        fit_content.setChecked(True)
        form.addRow(fit_content)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            width, height = [field.value() * current_factor[0] for field in dimensions]
            self.mutate(lambda: self.model.resize_page(self.current_page, width, height, fit_content.isChecked()))

    def crop_page(self):
        if not self.model.doc:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Crop current page")
        form = QFormLayout(dialog)
        fields = []
        for label in ("Left", "Top", "Right", "Bottom"):
            field = QDoubleSpinBox()
            field.setRange(0, 10000)
            field.setSuffix(" pt")
            form.addRow(label, field)
            fields.append(field)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.mutate(lambda: self.model.crop(self.current_page, [field.value() for field in fields]))

    def focus_search(self):
        if not self.model.doc:
            return
        self.find_panel.position_panel()
        self.find_panel.show()
        self.find_panel.raise_()
        self.search.setFocus()
        self.search.selectAll()
        if self.search.text().strip() and not self.search_hits:
            self.find_timer.start()

    def close_find(self, clear_query=False):
        self.find_timer.stop()
        self.find_panel.hide()
        if clear_query:
            self.search.clear()
        self.clear_search()
        self.scroll.setFocus()

    def search_changed(self):
        self.clear_search()
        if self.find_panel.isVisible() and self.search.text().strip():
            self.find_timer.start()

    def clear_search(self):
        if hasattr(self, "find_timer"):
            self.find_timer.stop()
        self.search_hits = []
        self.search_index = -1
        if hasattr(self, "find_panel"):
            self.find_panel.count.clear()
        if hasattr(self, "canvas"):
            self.canvas.search_rects = []
            self.canvas.update()

    def find_next(self, direction=1):
        self.find_timer.stop()
        query = self.search.text().strip()
        if not self.model.doc or not query:
            return
        if not self.search_hits:
            self.search_hits = [(i, rect) for i, page in enumerate(self.model.doc) for rect in page.search_for(query)]
        if not self.search_hits:
            self.find_panel.count.setText("0/0")
            return
        self.search_index = ((0 if direction > 0 else len(self.search_hits) - 1) if self.search_index < 0
                             else (self.search_index + direction) % len(self.search_hits))
        index, rect = self.search_hits[self.search_index]
        self.go_page(index)
        self.canvas.search_rects = [r for i, r in self.search_hits if i == index]
        self.canvas.update()
        displayed = rect * self.canvas.rotation
        document = self.active_document
        def reveal_match():
            if self.active_document is document and self.current_page == index:
                self.scroll.ensureVisible(int(displayed.x0 * self.canvas.scale + 24),
                    int(displayed.y0 * self.canvas.scale + 24), 60, 60)
        QTimer.singleShot(0, reveal_match)
        self.find_panel.count.setText(f"{self.search_index + 1}/{len(self.search_hits)}")

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and any(url.toLocalFile().lower().endswith(".pdf") for url in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(".pdf"):
                self.open_file(path)
                event.acceptProposedAction()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Sol PDF")
    app.setOrganizationName("Sol PDF")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    app.setWindowIcon(sol_icon())
    window = MainWindow()
    window.show()
    if os.environ.get("SOL_PDF_SMOKE_OUTPUT"):
        def smoke():
            folder = Path(os.environ["SOL_PDF_SMOKE_OUTPUT"])
            folder.mkdir(parents=True, exist_ok=True)
            try:
                window.new_file()
                assert window.mode == "view"
                window.set_mode("add")
                window.text_clicked((72, 90))
                window.inline_editor.setPlainText("Original title")
                window.update_text_preview()
                assert window.inline_view.isVisible() and not window.model.doc[0].get_text()
                window.apply_text()
                window.set_mode("edit")
                window.text_clicked(window.model.spans(0)[0])
                window.editor.setPlainText("New title")
                window.apply_text()
                assert "Original title" not in window.model.doc[0].get_text()
                assert "New title" in window.model.doc[0].get_text()
                window.model.blank(0)
                window.model.rotate([0])
                window.model.reorder([1, 0])
                window.refresh()
                window.model.save(folder / "smoke.pdf")
                with fitz.open(folder / "smoke.pdf") as check:
                    assert len(check) == 2
                    assert "New title" in check[1].get_text()
                    assert check[1].rotation == 90
                first_model = window.model
                window.new_file()
                second_model = window.model
                window.set_mode("add")
                window.text_clicked((72, 90))
                window.editor.setPlainText("Second document")
                window.apply_text()
                assert window.document_tabs.count() == 2
                window.activate_document(0)
                assert window.model is first_model and "New title" in window.model.doc[1].get_text()
                second_model.saved_revision = second_model.revision
                window.close_document_tab(1)
                assert window.document_tabs.count() == 1 and window.model is first_model
                window.update_actions()
                window.grab().save(str(folder / "smoke.png"))
                (folder / "result.json").write_text(json.dumps({"success": True,
                    "checks": ["startup", "render", "add text", "replace text", "blank page",
                               "rotation", "reorder", "save", "reopen", "document tabs", "on-page text preview", "default view"]}))
                app.exit(0)
            except Exception as error:
                (folder / "result.json").write_text(json.dumps({"success": False, "error": str(error)}))
                app.exit(1)
        QTimer.singleShot(0, smoke)
        return app.exec()
    for argument in sys.argv[1:]:
        if Path(argument).is_file():
            QTimer.singleShot(0, lambda path=argument: window.open_file(path))
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
