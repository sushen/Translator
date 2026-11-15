"""Page-oriented rich-text editing with explicit AI proposal acceptance."""
import base64
from pathlib import Path

import pymupdf
from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtGui import QImage, QPixmap, QTextImageFormat
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QComboBox, QTextEdit, QPlainTextEdit, QLabel, QFileDialog,
    QMessageBox, QSplitter, QInputDialog, QScrollArea, QToolBar)

from app.document.studio_project import (from_document, save_project, load_project,
                                        record_page, render_project)
from app.translation.refinement import propose
from app.gui.zoom import install_zoom, editor_html
from app.gui.styles.theme import STYLE_SHEET


class RefinementWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, config, payload, parent=None):
        super().__init__(parent)
        self.config, self.payload = config, payload

    def run(self):
        try:
            from openai import OpenAI
            from app.translation.http_client import verified_http_client
            with OpenAI(api_key=self.config["key"], base_url=self.config["url"] or None,
                        http_client=verified_http_client(), max_retries=0) as client:
                self.completed.emit(propose(client, self.config["model"], **self.payload))
        except Exception:
            # Provider exceptions can contain request content or credential details.
            self.failed.emit("AI refinement failed. Check cloud settings and connection; your page is unchanged.")


class StudioWindow(QMainWindow):
    def __init__(self, document, config_factory, parent=None, project=None):
        super().__init__(parent)
        self.setWindowTitle("Translation Studio — Page Editor")
        self.resize(1250, 850)
        self.setStyleSheet(STYLE_SHEET)
        self.project = project if project is not None else from_document(document)
        self.config_factory = config_factory
        self.index, self.project_path, self.worker = 0, None, None
        self.dirty = False
        self.proposal_page = None
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)
        bar = QToolBar("Page and project", self)
        bar.setMovable(False)
        self.addToolBar(bar)
        self.pages = QComboBox()
        self.pages.setMinimumContentsLength(14)
        bar.addWidget(self.pages)
        for title, callback in [("Open translated PDF", self.open_pdf), ("Open project", self.open_project), ("Save project", self.save),
                                ("Export new PDF", self.export), ("Preview PDF", self.preview),
                                ("Add picture", self.picture), ("Restore revision", self.restore)]:
            bar.addAction(title, callback)
        design_menu = self.menuBar().addMenu("Page")
        design_menu.addAction("Design cover / title page…", self.design_frontmatter)
        design_menu.addAction("Attach source text for this page…", self.attach_source)
        design_menu.addAction("Restore original imported PDF page", self.restore_imported)
        bar.addAction("Cover / title page", self.design_frontmatter)
        hint = QLabel("Edit the Bangla page, review an AI proposal, then save or export. Longer translations continue onto extra pages at readable size; each source page starts separately.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #64748b;")
        layout.addWidget(hint)
        split = QSplitter()
        split.setChildrenCollapsible(False)
        split.setHandleWidth(7)
        layout.addWidget(split, 1)
        self.source = QPlainTextEdit()
        self.source.setReadOnly(True)
        self.source.setPlaceholderText("Original source")
        self.editor = QTextEdit()
        self.editor.setAcceptRichText(False)
        self.editor.setPlaceholderText("Editable Bangla translation — type extra text here")
        self.proposal = QPlainTextEdit()
        self.proposal.setReadOnly(True)
        for title, widget in (("Original source", self.source), ("Bangla editor", self.editor),
                              ("AI proposal", self.proposal)):
            panel = QWidget()
            column = QVBoxLayout(panel)
            column.setContentsMargins(0, 0, 0, 0)
            heading = QLabel(title)
            heading.setWordWrap(True)
            heading.setObjectName("panelHeading")
            column.addWidget(heading)
            column.addWidget(widget, 1)
            split.addWidget(panel)
        split.setSizes([300, 530, 350])
        for index, weight in enumerate((3, 5, 3)):
            split.setStretchFactor(index, weight)
        self.instructions = QPlainTextEdit()
        self.instructions.setPlaceholderText("Optional editorial instructions for AI")
        self.instructions.setMaximumHeight(95)
        layout.addWidget(self.instructions)
        formatting = QHBoxLayout()
        layout.addLayout(formatting)
        bold = QPushButton("Bold")
        bold.clicked.connect(lambda: self.editor.setFontWeight(400 if self.editor.fontWeight() > 400 else 700))
        formatting.addWidget(bold)
        size = QComboBox()
        size.addItems(["10", "11", "12", "14", "16", "18", "24"])
        size.setCurrentText("11")
        size.currentTextChanged.connect(lambda value: self.editor.setFontPointSize(float(value)))
        formatting.addWidget(size)
        formatting.addStretch()
        actions = QHBoxLayout()
        layout.addLayout(actions)
        self.improve = QPushButton("Improve with AI")
        self.improve.setToolTip("Uses the configured cloud API and may incur charges")
        self.improve.clicked.connect(self.refine)
        actions.addWidget(self.improve)
        self.accept = QPushButton("Accept proposed text")
        self.accept.setEnabled(False)
        self.accept.clicked.connect(self.accept_proposal)
        actions.addWidget(self.accept)
        reject = QPushButton("Reject proposal")
        reject.clicked.connect(self.clear_proposal)
        actions.addWidget(reject)
        actions.addStretch()
        credit = QLabel("Cloud AI uses API credit")
        credit.setStyleSheet("color: #64748b;")
        actions.addWidget(credit)
        self.editor.textChanged.connect(self.changed)
        self.pages.currentIndexChanged.connect(self.select_page)
        self.refresh_pages()
        self.addToolBarBreak()
        install_zoom(self)

    def changed(self):
        self.dirty = True
        self.accept.setEnabled(False)

    def refresh_pages(self):
        self.pages.blockSignals(True)
        self.pages.clear()
        self.pages.addItems([f"Source page {p['number']}" for p in self.project["pages"]])
        self.pages.blockSignals(False)
        self.index = 0
        self.show_page()

    def capture(self):
        page = self.project["pages"][self.index]
        markup = editor_html(self.editor)
        if markup != getattr(self, "loaded_markup", markup) and not page.get("frontmatter"):
            # Preserve original PDF pages until the user actually edits the text.
            if "pdf_index" in page and not page.get("edited"):
                from datetime import datetime
                page["history"].append({"at": datetime.now().isoformat(), "html": page["html"], "edited": False})
            record_page(page, markup)
            page["edited"] = True
            self.loaded_markup = markup

    def show_page(self):
        page = self.project["pages"][self.index]
        self.source.setPlainText(page["source"])
        self.editor.blockSignals(True)
        self.editor.setHtml(page["html"])
        self.editor.setReadOnly(bool(page.get("frontmatter")))
        self.editor.blockSignals(False)
        self.loaded_markup = editor_html(self.editor)
        self.improve.setEnabled(not bool(page.get("frontmatter")))
        if page.get("frontmatter"):
            self.statusBar().showMessage("Designed page: use Cover / title page to edit its layers; Preview PDF shows the result.")
        elif "pdf_index" in page and not page.get("edited"):
            self.statusBar().showMessage("Original PDF page preserved. Extracted text is only an editing draft; Preview PDF shows the original. Editing text replaces its layout and may lose images.")
        self.clear_proposal()

    def open_pdf(self):
        if not self.discard_ok():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open translated PDF", "output", "PDF (*.pdf)")
        if path:
            try:
                from app.document.studio_frontmatter import import_pdf
                self.project = import_pdf(path)
                self.project_path, self.dirty = None, True
                self.refresh_pages()
            except Exception as exc:
                QMessageBox.warning(self, "PDF import failed", str(exc))

    def design_frontmatter(self):
        self.capture()
        from app.gui.frontmatter_dialog import FrontmatterDialog
        from app.document.studio_frontmatter import replace_frontmatter
        dialog = FrontmatterDialog(self.project["pages"][self.index], self)
        if dialog.exec():
            replace_frontmatter(self.project["pages"][self.index], dialog.design)
            self.dirty = True
            self.show_page()

    def attach_source(self):
        text, ok = QInputDialog.getMultiLineText(self, "Attach source text", "Corresponding original/reference passage (manual alignment):", self.source.toPlainText())
        if ok:
            self.project["pages"][self.index]["source"] = text
            self.source.setPlainText(text)
            self.dirty = True

    def restore_imported(self):
        page = self.project["pages"][self.index]
        if "pdf_index" not in page:
            return
        self.capture()
        from app.document.studio_frontmatter import replace_frontmatter
        replace_frontmatter(page, {})
        page.pop("frontmatter", None)
        page["edited"] = False
        page["html"] = page.get("imported_html", page["html"])
        self.dirty = True
        self.show_page()

    def select_page(self, index):
        if index < 0:
            return
        self.capture()
        self.index = index
        self.show_page()

    def clear_proposal(self):
        self.proposal.clear()
        self.accept.setEnabled(False)
        self.proposal_page = None

    def save(self):
        self.capture()
        path = self.project_path
        if not path:
            path, _ = QFileDialog.getSaveFileName(self, "Save studio project", "translation.studio.json", "Studio project (*.json)")
        if not path:
            return False
        try:
            if Path(path).resolve() == Path(self.project["source_path"]).resolve():
                raise ValueError("Choose a separate project file.")
            save_project(self.project, path)
            self.project_path, self.dirty = path, False
            self.statusBar().showMessage("Studio project saved")
            return True
        except Exception as exc:
            QMessageBox.warning(self, "Save failed", str(exc))
            return False

    def discard_ok(self):
        if not self.dirty:
            return True
        answer = QMessageBox.question(self, "Unsaved studio edits", "Save changes before continuing?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        return self.save() if answer == QMessageBox.Save else answer == QMessageBox.Discard

    def open_project(self):
        if not self.discard_ok():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open studio project", "", "Studio project (*.json)")
        if path:
            try:
                self.project = load_project(path)
                self.project_path, self.dirty = path, False
                self.refresh_pages()
            except Exception as exc:
                QMessageBox.warning(self, "Open failed", str(exc))

    def picture(self):
        path, _ = QFileDialog.getOpenFileName(self, "Add picture", "", "Images (*.png *.jpg *.jpeg)")
        if not path:
            return
        image = QImage(path)
        if image.isNull():
            QMessageBox.warning(self, "Image", "Cannot read this image.")
            return
        data = base64.b64encode(Path(path).read_bytes()).decode("ascii")
        fmt = QTextImageFormat()
        fmt.setName("data:image/png;base64," + data)
        width = min(300, image.width())
        fmt.setWidth(width)
        fmt.setHeight(width * image.height() / image.width())
        self.editor.textCursor().insertImage(fmt)

    def refine(self):
        if self.worker and self.worker.isRunning():
            return
        if not self.source.toPlainText().strip():
            QMessageBox.information(self, "Source text needed", "Imported Bangla PDFs have no aligned original. Use Page → Attach source text before requesting AI refinement.")
            return
        try:
            config = self.config_factory()
        except ValueError as exc:
            QMessageBox.warning(self, "Cloud setup", str(exc))
            return
        self.capture()
        self.request_index = self.index
        self.request_html = editor_html(self.editor)
        context = [{"source": p["source"], "translation_html": p["html"]}
                   for p in self.project["pages"][max(0, self.index - 1):self.index + 2]]
        payload = dict(source=self.source.toPlainText(), current=self.editor.toPlainText(),
                       context=context, instructions=self.instructions.toPlainText())
        self.worker = RefinementWorker(config, payload, self)
        self.worker.completed.connect(self.received)
        self.worker.failed.connect(lambda message: QMessageBox.warning(self, "AI refinement", message))
        self.worker.finished.connect(lambda: self.improve.setEnabled(True))
        self.improve.setEnabled(False)
        self.statusBar().showMessage("Requesting a revision using this page and adjacent page context…")
        self.worker.start()

    def received(self, result):
        if self.index != self.request_index or editor_html(self.editor) != self.request_html:
            self.statusBar().showMessage("Page changed during request; outdated proposal discarded.")
            return
        self.result = result
        self.proposal_page = self.index
        self.proposal.setPlainText(result["translation"] + "\n\nReasons:\n" + result["reasons"] +
                                   "\n\nAmbiguities:\n" + result["ambiguities"])
        self.accept.setEnabled(True)
        self.statusBar().showMessage("Proposal ready; existing page unchanged until accepted")

    def accept_proposal(self):
        if self.proposal_page != self.index:
            return
        # Preserve inline pictures and surrounding design. Replace text fragments
        # only when no images are present; otherwise require explicit manual merge.
        if "<img " in self.editor.toHtml():
            QMessageBox.information(self, "Keep page design", "This page contains pictures. Copy the proposed text into the desired position manually to preserve your design.")
            return
        self.capture()
        self.editor.setPlainText(self.result["translation"])
        self.capture()
        self.clear_proposal()

    def restore(self):
        self.capture()
        history = self.project["pages"][self.index]["history"]
        if not history:
            return
        labels = [f"{i + 1}: {item['at']}" for i, item in enumerate(history)]
        label, ok = QInputDialog.getItem(self, "Restore revision", "Version", labels, editable=False)
        if ok:
            from copy import deepcopy
            selected = deepcopy(history[labels.index(label)])
            from app.document.studio_frontmatter import replace_frontmatter
            page = self.project["pages"][self.index]
            replace_frontmatter(page, selected.get("frontmatter") or {})
            page["html"] = selected["html"]
            page["edited"] = selected.get("edited", True)
            if not selected.get("frontmatter"):
                page.pop("frontmatter", None)
            self.dirty = True
            self.show_page()

    def pdf_bytes(self):
        self.capture()
        return render_project(self.project)

    def preview(self):
        try:
            self.capture()
            data, mapping = render_project(self.project, return_mapping=True)
            window = QMainWindow(self)
            window.setWindowTitle("PDF page preview")
            label = QLabel()
            navigation = QToolBar("Output pages", window)
            window.addToolBar(navigation)
            selector = QComboBox()
            for source, indices in zip(self.project["pages"], mapping):
                for continuation, index in enumerate(indices):
                    title = f"Source page {source['number']}"
                    if continuation:
                        title += f" · continuation {continuation + 1}"
                    selector.addItem(title, index)
            def display(index):
                with pymupdf.open(stream=data, filetype="pdf") as pdf:
                    pix = pdf[selector.itemData(index)].get_pixmap(matrix=pymupdf.Matrix(1.1, 1.1), alpha=False)
                    image = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888).copy()
                label.setPixmap(QPixmap.fromImage(image))
                label.adjustSize()
            navigation.addWidget(selector)
            selector.currentIndexChanged.connect(display)
            selector.setCurrentIndex(mapping[self.index][0])
            display(selector.currentIndex())
            scroll = QScrollArea()
            scroll.setWidget(label)
            window.setCentralWidget(scroll)
            window.resize(750, 850)
            window.show()
        except Exception as exc:
            QMessageBox.warning(self, "Preview failed", str(exc))

    def export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export new PDF", "studio_edited.pdf", "PDF (*.pdf)")
        if path:
            try:
                # Never replace an existing output or original PDF.
                data = self.pdf_bytes()
                with open(path, "xb") as stream:
                    stream.write(data)
                self.statusBar().showMessage("New PDF exported; save the studio project to retain edit history")
            except Exception as exc:
                QMessageBox.warning(self, "Export failed", str(exc))

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self, "AI request running", "Wait for the current AI request to finish before closing.")
            event.ignore()
        elif self.discard_ok():
            event.accept()
        else:
            event.ignore()
