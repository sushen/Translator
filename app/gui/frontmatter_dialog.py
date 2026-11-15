"""Cover and title-page layers with a preview from the actual PDF renderer."""
import base64
from copy import deepcopy
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QImage, QPixmap, QFont, QFontDatabase
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QVBoxLayout, QFormLayout,
    QLineEdit, QSpinBox, QCheckBox, QPushButton, QLabel, QFileDialog,
    QColorDialog, QDialogButtonBox, QScrollArea, QWidget, QComboBox)
import pymupdf
from app.document.studio_frontmatter import default_frontmatter, render_frontmatter


class FrontmatterDialog(QDialog):
    def __init__(self, page, parent=None):
        super().__init__(parent)
        from app.fonts.font_manager import FontManager
        font = FontManager.get_instance().get_font_path("Noto Sans Bengali")
        families = QFontDatabase.applicationFontFamilies(QFontDatabase.addApplicationFont(str(font)))
        if families:
            self.setFont(QFont(families[0], 10))
        self.setWindowTitle("Cover & title page designer")
        available = self.screen().availableGeometry()
        self.resize(min(1120, available.width() - 40), min(760, available.height() - 60))
        self.page = page
        self.design = deepcopy(page.get("frontmatter") or default_frontmatter())
        self.design.setdefault("editor", "শাহ আলম প্রধান")
        self.design.setdefault("publisher", "ম্যাসস্টকস")
        if self.design["publisher"] == "মেশস্টকস":
            self.design["publisher"] = "ম্যাসস্টকস"
        for key, value in (("layout", "classic"), ("translator_size", 32), ("author_size", 18), ("support_y", 78)):
            self.design.setdefault(key, value)
        root = QVBoxLayout(self)
        content = QHBoxLayout()
        root.addLayout(content, 1)
        controls = QWidget()
        form = QFormLayout(controls)
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        focus = QPushButton("অনুবাদককে প্রাধান্য দিন · Translator-first layout")
        focus.clicked.connect(self.translator_focus)
        form.addRow(focus)
        self.kind = QComboBox()
        self.kind.addItems(["cover", "title page"])
        self.kind.setCurrentText(self.design["kind"])
        form.addRow("Page role", self.kind)
        self.fields = {}
        for key, label in (("title", "Book title"), ("author", "Author"),
                           ("translator", "Bangla translator"), ("english_translator", "English translator"),
                           ("editor", "সম্পাদক"), ("publisher", "প্রকাশনা")):
            field = QLineEdit(self.design[key])
            self.fields[key] = field
            form.addRow(label, field)
        self.english = QCheckBox("Show separate English translator credit")
        self.english.setChecked(self.design["show_english"])
        form.addRow(self.english)
        self.spins = {}
        for key, label, low, high in (("title_y", "Title position (%)", 12, 80),
            ("author_y", "Author position (%)", 12, 85), ("translator_y", "Translator position (%)", 12, 85),
            ("support_y", "Other credits position (%)", 12, 85),
            ("title_size", "Title font size", 12, 60), ("translator_size", "Translator name size", 16, 48),
            ("author_size", "Author font size", 10, 36), ("credit_size", "Other credits size", 10, 24)):
            spin = QSpinBox()
            spin.setRange(low, high)
            spin.setValue(self.design[key])
            self.spins[key] = spin
            form.addRow(label, spin)
        for key in ("translator_size", "author_size", "support_y"):
            self.spins[key].setEnabled(self.design["layout"] == "translator_focus")
        self.panel = QCheckBox("Light panel behind text for readability")
        self.panel.setChecked(self.design["panel"])
        form.addRow(self.panel)
        opacity = QSpinBox()
        opacity.setRange(0, 100)
        opacity.setSuffix(" %")
        opacity.setValue(self.design.get("panel_opacity", 92))
        opacity.setToolTip("0% is fully transparent; 100% is solid white. Text stays fully opaque.")
        opacity.setEnabled(self.panel.isChecked())
        self.panel.toggled.connect(opacity.setEnabled)
        self.spins["panel_opacity"] = opacity
        form.addRow("Text panel opacity", opacity)
        for title, callback in (("Choose background picture…", self.background),
                                ("Remove background picture", self.remove_background),
                                ("Choose text color…", self.color)):
            button = QPushButton(title)
            button.clicked.connect(callback)
            form.addRow(button)
        note = QLabel("Applying replaces this page's design. The previous page remains in history. A flattened cover's existing lettering cannot be edited as separate text; choose a clean background instead.")
        note.setWordWrap(True)
        form.addRow(note)
        self.error = QLabel()
        self.error.setWordWrap(True)
        form.addRow(self.error)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Apply | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Apply).clicked.connect(self.apply)
        self.buttons.rejected.connect(self.reject)
        root.addWidget(self.buttons)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(controls)
        content.addWidget(scroll, 1)
        self.preview = QLabel()
        self.preview.setMinimumWidth(350)
        self.preview.setScaledContents(False)
        preview_scroll = QScrollArea()
        preview_scroll.setWidget(self.preview)
        preview_scroll.setAlignment(Qt.AlignCenter)
        content.addWidget(preview_scroll, 1)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.refresh)
        for field in self.fields.values():
            field.textChanged.connect(self.schedule)
        for spin in self.spins.values():
            spin.valueChanged.connect(self.schedule)
        self.english.toggled.connect(self.schedule)
        self.panel.toggled.connect(self.schedule)
        self.kind.currentTextChanged.connect(self.schedule)
        self.refresh()

    def translator_focus(self):
        self.design["layout"] = "translator_focus"
        for key in ("translator_size", "author_size", "support_y"):
            self.spins[key].setEnabled(True)
        for key, value in (("title_y", 18), ("author_y", 37), ("translator_y", 51),
                           ("support_y", 78), ("title_size", 40), ("translator_size", 32),
                           ("author_size", 18), ("credit_size", 12)):
            self.spins[key].setValue(value)
        self.refresh()

    def schedule(self):
        self.timer.start(200)

    def collect(self):
        self.design.update({key: field.text() for key, field in self.fields.items()})
        self.design.update({key: spin.value() for key, spin in self.spins.items()})
        self.design.update(kind=self.kind.currentText(), show_english=self.english.isChecked(), panel=self.panel.isChecked())

    def refresh(self):
        self.collect()
        try:
            with pymupdf.open() as pdf:
                render_frontmatter(pdf, {**self.page, "frontmatter": self.design})
                factor = min(.85, max(180, (self.width() - 60) / 2) / pdf[0].rect.width,
                             max(200, self.height() - 100) / pdf[0].rect.height)
                pix = pdf[0].get_pixmap(matrix=pymupdf.Matrix(factor, factor), alpha=False)
                image = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888).copy()
                self.preview.setPixmap(QPixmap.fromImage(image))
                self.preview.adjustSize()
            self.error.clear()
            self.buttons.button(QDialogButtonBox.Apply).setEnabled(True)
            return True
        except Exception as exc:
            self.error.setText(str(exc))
            self.buttons.button(QDialogButtonBox.Apply).setEnabled(False)
            return False

    def background(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose clean cover background", "", "Images (*.png *.jpg *.jpeg)")
        if path:
            from pathlib import Path
            self.design["background"] = base64.b64encode(Path(path).read_bytes()).decode("ascii")
            self.refresh()

    def remove_background(self):
        self.design["background"] = ""
        self.refresh()

    def color(self):
        color = QColorDialog.getColor(parent=self)
        if color.isValid():
            self.design["color"] = color.name()
            self.refresh()

    def apply(self):
        if self.refresh():
            self.accept()
