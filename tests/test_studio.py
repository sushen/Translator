import base64
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pymupdf
from PySide6.QtWidgets import QApplication
from app.document.document_model import DocumentModel
from app.document.page_model import PageModel
from app.document.paragraph_model import ParagraphModel
from app.document.studio_project import from_document, save_project, load_project, render_project
from app.gui.studio_window import StudioWindow
from app.translation.refinement import propose


class StudioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def document(self):
        return DocumentModel(Path("original.pdf"), "original.pdf", 0, 1, pages=[
            PageModel(6, 595, 842, paragraphs=[ParagraphModel("p1", "Source", translated_text="বাংলা")])])

    def test_edit_save_restore_render_and_source_isolation(self):
        document = self.document()
        window = StudioWindow(document, lambda: {})
        window.editor.setPlainText("সম্পাদিত বাংলা")
        window.capture()
        self.assertEqual(document.pages[0].paragraphs[0].current_translation, "বাংলা")
        self.assertTrue(window.project["pages"][0]["history"])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "project.json"
            save_project(window.project, path)
            project = load_project(path)
            self.assertIn("সম্পাদিত বাংলা", project["pages"][0]["html"])
            with pymupdf.open(stream=render_project(project), filetype="pdf") as pdf:
                self.assertEqual(len(pdf), 1)
                self.assertGreater(len(pdf[0].get_pixmap().samples), 0)
        window.dirty = False
        window.close()

    def test_embedded_image_survives_editor_and_pdf(self):
        from PySide6.QtGui import QImage, QTextImageFormat
        from PySide6.QtCore import QBuffer, QByteArray, QIODevice
        image = QImage(20, 20, QImage.Format_RGB32)
        image.fill(0xff0000)
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.WriteOnly)
        image.save(buffer, "PNG")
        window = StudioWindow(self.document(), lambda: {})
        fmt = QTextImageFormat()
        fmt.setName("data:image/png;base64," + base64.b64encode(bytes(data)).decode())
        fmt.setWidth(30)
        fmt.setHeight(30)
        window.editor.textCursor().insertImage(fmt)
        with pymupdf.open(stream=window.pdf_bytes(), filetype="pdf") as pdf:
            self.assertTrue(pdf[0].get_images())
        window.dirty = False
        window.close()

    def test_proposal_validates_complete_result(self):
        client = Mock()
        client.chat.completions.create.return_value = SimpleNamespace(choices=[SimpleNamespace(
            finish_reason="stop", message=SimpleNamespace(content='{"translation":"বাংলা","reasons":"Clearer","ambiguities":"None"}'))])
        self.assertEqual(propose(client, "mock", "source", "current", [])["translation"], "বাংলা")
        client.chat.completions.create.return_value.choices[0].finish_reason = "length"
        with self.assertRaises(ValueError):
            propose(client, "mock", "source", "current", [])

    def test_stale_proposal_not_applied(self):
        window = StudioWindow(self.document(), lambda: {})
        window.request_index = 0
        window.request_html = window.editor.toHtml()
        window.editor.setPlainText("new edit")
        window.received({"translation": "replacement", "reasons": "", "ambiguities": ""})
        self.assertFalse(window.accept.isEnabled())
        self.assertEqual(window.editor.toPlainText(), "new edit")
        window.dirty = False
        window.close()

    def test_display_zoom_preserves_export_and_edits(self):
        from app.gui.zoom import editor_html
        window = StudioWindow(self.document(), lambda: {})
        original = window.zoom_selector.currentText()
        window.zoom_selector.setCurrentText("100%")
        before = editor_html(window.editor)
        window.zoom_selector.setCurrentText("175%")
        self.assertEqual(editor_html(window.editor), before)
        self.assertFalse(window.dirty)
        self.assertEqual(window.editor.property("displayZoomSteps"), 9)
        window.zoom_selector.setCurrentText(original)
        window.close()

    def test_studio_overflow_mapping(self):
        project = from_document(self.document())
        project["pages"][0]["html"] = "<p>" + "Readable expanded text. " * 900 + "</p>"
        project["pages"].append({"number":7,"width":595,"height":842,"source":"next",
                                 "html":"<p>Next source page</p>","history":[]})
        data, mapping = render_project(project, return_mapping=True)
        self.assertGreater(len(mapping[0]), 1)
        self.assertEqual(mapping[1][0], mapping[0][-1] + 1)
        with pymupdf.open(stream=data, filetype="pdf") as pdf:
            self.assertIn("Next source page", pdf[mapping[1][0]].get_text())
