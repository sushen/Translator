"""Window zoom controls, with reversible rich-text display magnification."""
import re
from PySide6.QtCore import QSettings
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QToolBar, QComboBox, QTextEdit, QPlainTextEdit


def editor_html(editor):
    """Serialize at original size so display zoom never changes PDF typography."""
    steps = editor.property("displayZoomSteps") or 0
    blocked = editor.blockSignals(True)
    try:
        editor.zoomOut(steps)
        return editor.toHtml()
    finally:
        editor.zoomIn(steps)
        editor.blockSignals(blocked)


def install_zoom(window):
    baseline = window.styleSheet()
    preferences = QSettings("TranslatorWorkbench", "Display")
    toolbar = QToolBar("Display zoom", window)
    toolbar.setMovable(False)
    window.addToolBar(toolbar)
    menu = window.menuBar().addMenu("View")
    selector = QComboBox()
    selector.addItems([f"{value}%" for value in range(75, 201, 25)])
    toolbar.addWidget(selector)
    window.zoom_selector = selector

    def apply():
        percent = int(selector.currentText().rstrip("%"))
        scale = percent / 100
        editors = [editor for editor in window.findChildren(QTextEdit) + window.findChildren(QPlainTextEdit)
                   if editor.window() == window]
        originals = []
        for editor in editors:
            blocked = editor.blockSignals(True)
            editor.zoomOut(editor.property("displayZoomSteps") or 0)
            originals.append((editor, editor.document().defaultFont(), blocked))
        # Text grows fully; chrome grows gently so padding cannot overwhelm content.
        chrome_scale = 1 + (scale - 1) * 0.35
        scaled = re.sub(r"(\d+(?:\.\d+)?)px", lambda m: f"{float(m[1]) * chrome_scale:g}px", baseline)
        controls = ("QLabel, QPushButton, QToolButton, QComboBox, QLineEdit, QSpinBox, "
                    "QMenuBar, QMenu, QTabBar, QGroupBox, QCheckBox, QHeaderView, "
                    "QTableWidget, QProgressBar, QStatusBar")
        window.setStyleSheet(scaled + f"\n{controls} {{ font-size: {10 * scale:g}pt; }}")
        for editor, font, blocked in originals:
            steps = round((scale - 1) * 12)
            editor.document().setDefaultFont(font)
            editor.zoomIn(steps)
            editor.setProperty("displayZoomSteps", steps)
            editor.blockSignals(blocked)
        preferences.setValue("zoomPercent", percent)

    def change(delta):
        selector.setCurrentIndex(max(0, min(selector.count() - 1, selector.currentIndex() + delta)))

    for title, shortcut, callback in [
        ("Zoom in", "Ctrl+=", lambda: change(1)),
        ("Zoom out", "Ctrl+-", lambda: change(-1)),
        ("Reset zoom", "Ctrl+0", lambda: selector.setCurrentText("100%")),
    ]:
        action = menu.addAction(title, callback)
        action.setShortcut(QKeySequence(shortcut))
        toolbar.addAction(action)
    extra = window.addAction("Zoom in (+)", lambda: change(1))
    extra.setShortcut(QKeySequence("Ctrl++"))
    selector.setCurrentText(f"{preferences.value('zoomPercent', 125, type=int)}%")
    selector.currentTextChanged.connect(apply)
    apply()
