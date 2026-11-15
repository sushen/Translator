"""User-configurable local library defaults; never moves or modifies books."""
from pathlib import Path
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (QDialog, QFormLayout, QLineEdit, QPushButton,
                              QHBoxLayout, QFileDialog, QDialogButtonBox, QMessageBox)
from app.utils.paths import BASE_DIR


def book_locations():
    preferences = QSettings("TranslatorWorkbench", "BookLocations")
    folder = BASE_DIR / "Book"
    original = folder / "Oraginal"
    def unique_pdf(directory):
        files = sorted(directory.glob("*.pdf")) if directory.is_dir() else []
        return str(files[0]) if len(files) == 1 else ""
    return {
        "folder": preferences.value("folder", str(folder), type=str),
        "source": preferences.value("source", unique_pdf(folder), type=str),
        "original": preferences.value("original", unique_pdf(original), type=str),
    }


class BookLocationsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Book Locations")
        self.resize(800, 240)
        layout = QFormLayout(self)
        layout.setRowWrapPolicy(QFormLayout.WrapLongRows)
        self.fields = {}
        values = book_locations()
        for key, label in (("folder", "Book folder"), ("source", "Default English/reference PDF"),
                           ("original", "Original-edition PDF")):
            row = QHBoxLayout()
            field = QLineEdit(values[key])
            field.setMinimumWidth(250)
            self.fields[key] = field
            row.addWidget(field, 1)
            button = QPushButton("Browse…")
            button.clicked.connect(lambda checked=False, item=key: self.browse(item))
            row.addWidget(button)
            layout.addRow(label, row)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def browse(self, key):
        start = self.fields[key].text() or self.fields["folder"].text()
        if key == "folder":
            path = QFileDialog.getExistingDirectory(self, "Choose book folder", start)
        else:
            path, _ = QFileDialog.getOpenFileName(self, "Choose PDF", start, "PDF files (*.pdf)")
        if path:
            self.fields[key].setText(path)

    def save(self):
        values = {key: field.text().strip() for key, field in self.fields.items()}
        if not Path(values["folder"]).is_dir():
            QMessageBox.warning(self, "Book folder", "Choose an existing book folder.")
            return
        for key in ("source", "original"):
            value = values[key]
            if value and (not Path(value).is_file() or Path(value).suffix.lower() != ".pdf"):
                QMessageBox.warning(self, "PDF path", "Choose an existing PDF, or leave the optional path empty.")
                return
        preferences = QSettings("TranslatorWorkbench", "BookLocations")
        for key, value in values.items():
            preferences.setValue(key, value)
        self.accept()
