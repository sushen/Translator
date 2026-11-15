import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from docx import Document
from app.document.docx_builder import DOCXBuilder
from app.document.document_model import DocumentModel
from app.document.page_model import PageModel
from app.document.paragraph_model import ParagraphModel


class TestDOCXBuilder(unittest.TestCase):
    def test_unicode_human_edit_and_failed_paragraph_are_preserved(self):
        reviewed = ParagraphModel("reviewed", "Original", translated_text="আগের অনুবাদ", status="translated")
        reviewed.add_human_edit("মানুষের সম্পাদিত বাংলা যুক্তাক্ষর পরীক্ষা")
        failed = ParagraphModel("failed", "Untranslated source", status="failed")
        model = DocumentModel(Path("source.pdf"), "source.pdf", 0, 1,
                              pages=[PageModel(21, 612, 792, paragraphs=[reviewed, failed])])
        with TemporaryDirectory() as directory:
            path = DOCXBuilder().build_docx(model, Path(directory) / "review.docx")
            doc = Document(path)
            paragraphs = [p.text for p in doc.paragraphs]
            self.assertIn(reviewed.human_translation, paragraphs)
            self.assertNotIn("আগের অনুবাদ", paragraphs)
            self.assertIn("Translation unavailable for this paragraph", paragraphs)
            self.assertIn("Untranslated source", paragraphs)
            self.assertEqual(doc.styles["Normal"].font.name, "Noto Serif Bengali")


if __name__ == "__main__":
    unittest.main()
