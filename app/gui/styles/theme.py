"""
Professional stylesheet for English -> Bangla PDF Translator GUI
"""
STYLE_SHEET = """
QMainWindow {
    background-color: #f5f6f8;
}

QGroupBox {
    font-weight: bold;
    border: 1px solid #dcdfe6;
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 10px;
    background-color: #ffffff;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 5px;
    color: #2c3e50;
}

QPushButton {
    background-color: #2b579a;
    color: white;
    border: none;
    padding: 6px 12px;
    border-radius: 4px;
    font-weight: bold;
    min-width: 0px;
}

QPushButton:hover {
    background-color: #1e3d6b;
}

QPushButton:disabled {
    background-color: #c0c4cc;
}

QPushButton#cancel_button {
    background-color: #d9534f;
}

QPushButton#cancel_button:hover {
    background-color: #c9302c;
}

QProgressBar {
    border: 1px solid #dcdfe6;
    border-radius: 4px;
    text-align: center;
    background-color: #eef1f6;
    height: 22px;
}

QProgressBar::chunk {
    background-color: #27ae60;
    width: 10px;
}

QTableWidget {
    background-color: #ffffff;
    border: 1px solid #dcdfe6;
    gridline-color: #eef1f6;
}

QHeaderView::section {
    background-color: #f0f2f5;
    padding: 6px;
    font-weight: bold;
    border: 1px solid #dcdfe6;
}
"""

# Shared control sizing keeps enlarged text proportional without oversized buttons.
STYLE_SHEET += """
QWidget { color: #253247; }
QToolBar { background: #ffffff; border-bottom: 1px solid #dde3eb; spacing: 4px; padding: 4px; }
QToolButton { padding: 5px 9px; border-radius: 4px; }
QToolButton:hover { background: #e8eff9; }
QLineEdit, QComboBox, QSpinBox {
    background: #ffffff; border: 1px solid #ccd5e2;
    border-radius: 4px; padding: 4px 7px; min-height: 20px;
}
QTextEdit, QPlainTextEdit {
    background: #ffffff; border: 1px solid #d4dce7;
    border-radius: 5px; padding: 8px; selection-background-color: #c9dcfa;
}
QTabWidget::pane { border: 1px solid #dde3eb; background: #f5f6f8; }
QTabBar::tab { padding: 8px 16px; background: #e9edf3; margin-right: 3px; }
QTabBar::tab:selected { background: #ffffff; color: #234f8f; }
QSplitter::handle { background: #e6ebf2; }
QScrollArea { border: none; background: transparent; }
QLabel#panelHeading { color: #234f8f; font-weight: bold; padding: 3px 0px; }
QPushButton { color: #ffffff; }
QPushButton:disabled { color: #677489; background-color: #e0e5ed; }
"""
