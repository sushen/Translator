import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import tempfile
import unittest
from pathlib import Path
import pymupdf
from PySide6.QtWidgets import QApplication
from app.document.studio_frontmatter import import_pdf, default_frontmatter, replace_frontmatter
from app.document.studio_project import render_project, save_project, load_project
from app.gui.frontmatter_dialog import FrontmatterDialog
from app.gui.studio_window import StudioWindow


class FrontmatterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def source(self, folder):
        path = Path(folder) / "source.pdf"
        with pymupdf.open() as pdf:
            for text in ("Original cover", "Original title", "Preserve this body page"):
                page = pdf.new_page(width=612, height=792)
                page.insert_text((70, 100), text)
            pdf.save(path)
        return path

    def test_cover_and_credits_roundtrip_preserve_other_pages(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.source(folder)
            original_bytes = path.read_bytes()
            project = import_pdf(path)
            replace_frontmatter(project["pages"][0], default_frontmatter())
            credits = default_frontmatter("title page")
            credits["show_english"] = True
            replace_frontmatter(project["pages"][1], credits)
            saved = Path(folder) / "project.json"
            save_project(project, saved)
            reopened = load_project(saved)
            self.assertEqual(reopened["pages"][1]["frontmatter"]["translator"], "সুশেন বিশ্বাস")
            with pymupdf.open(stream=render_project(reopened), filetype="pdf") as result, pymupdf.open(path) as source:
                self.assertEqual(len(result), 3)
                self.assertEqual(result[2].get_pixmap().digest, source[2].get_pixmap().digest)
                self.assertNotEqual(result[0].get_pixmap().digest, source[0].get_pixmap().digest)
            self.assertEqual(path.read_bytes(), original_bytes)
            self.assertFalse(project["pages"][0]["history"][0]["edited"])

    def test_open_preview_does_not_replace_imported_layout(self):
        with tempfile.TemporaryDirectory() as folder:
            project = import_pdf(self.source(folder))
            window = StudioWindow(None, lambda: {}, project=project)
            window.capture()
            self.assertFalse(project["pages"][0]["edited"])
            window.editor.setPlainText("Edited credits")
            window.capture()
            self.assertTrue(project["pages"][0]["edited"])
            window.restore_imported()
            self.assertFalse(project["pages"][0]["edited"])
            window.dirty = False
            window.close()

    def test_designer_rejects_overlapping_text(self):
        page = {"width":612,"height":792,"html":"","history":[]}
        dialog = FrontmatterDialog(page)
        self.assertTrue(dialog.refresh())
        dialog.spins["author_y"].setValue(dialog.spins["title_y"].value())
        self.assertFalse(dialog.refresh())
        dialog.close()

    def test_translator_preset_preserves_identity_and_panel(self):
        design = default_frontmatter()
        design.pop("layout")
        design.update(translator="শু", panel_opacity=50)
        page = {"width":612,"height":792,"html":"","history":[],"frontmatter":design}
        dialog = FrontmatterDialog(page)
        dialog.translator_focus()
        self.assertEqual(dialog.design["translator"], "শু")
        self.assertEqual(dialog.design["panel_opacity"], 50)
        self.assertGreater(dialog.design["translator_size"], dialog.design["author_size"])
        self.assertGreater(dialog.design["translator_size"], dialog.design["credit_size"])
        self.assertTrue(dialog.refresh())
        dialog.close()
