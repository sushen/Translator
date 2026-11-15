import tempfile
import unittest
from pathlib import Path
import pymupdf
from app.document.document_model import DocumentModel
from app.document.page_model import PageModel
from app.document.paragraph_model import ParagraphModel
from app.pdf.pdf_builder import PDFBuilder


class PageFlowTests(unittest.TestCase):
    def test_continuation_preserves_order_and_readable_size(self):
        document = DocumentModel(Path("source.pdf"), "source.pdf", 0, 2, pages=[
            PageModel(6, 400, 500, paragraphs=[ParagraphModel("a", "source",
                translated_text="BEGIN " + "Readable translated content. " * 650 + " END", bbox=(40, 50, 360, 440))]),
            PageModel(7, 400, 500, paragraphs=[ParagraphModel("b", "source", translated_text="NEXT SOURCE PAGE")])])
        with tempfile.TemporaryDirectory() as folder:
            builder = PDFBuilder()
            path = builder.build_pdf(document, Path(folder) / "test.pdf")
            with pymupdf.open(path) as pdf:
                first_pages = builder.last_page_map[0]["output_pages"]
                self.assertGreater(len(first_pages), 1)
                next_page = builder.last_page_map[1]["output_pages"][0] - 1
                self.assertEqual(next_page, len(first_pages))
                text = " ".join(pdf[i - 1].get_text() for i in first_pages)
                self.assertIn("BEGIN", text)
                self.assertIn("END", text)
                self.assertEqual(text.count("Readable"), 650)
                self.assertNotIn("NEXT SOURCE PAGE", text)
                self.assertIn("NEXT SOURCE PAGE", pdf[next_page].get_text())
                self.assertEqual(tuple(pdf[0].rect), (0, 0, 400, 500))
                sizes = [s["size"] for b in pdf[0].get_text("dict")["blocks"] if "lines" in b
                         for line in b["lines"] for s in line["spans"] if "Readable" in s["text"]]
                self.assertTrue(sizes)
                self.assertGreaterEqual(min(sizes), 11)

    def test_short_and_blank_pages_remain_separate(self):
        document = DocumentModel(Path("source.pdf"), "source.pdf", 0, 2, pages=[
            PageModel(1, 612, 792, paragraphs=[ParagraphModel("a", "Source", translated_text="Short page")]),
            PageModel(2, 612, 792)])
        with tempfile.TemporaryDirectory() as folder:
            path = PDFBuilder().build_pdf(document, Path(folder) / "test.pdf")
            with pymupdf.open(path) as pdf:
                self.assertEqual(len(pdf), 2)
                self.assertEqual(len(pdf.get_toc()), 2)
