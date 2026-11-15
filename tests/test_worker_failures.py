import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from app.document.document_model import DocumentModel
from app.document.page_model import PageModel
from app.document.paragraph_model import ParagraphModel
from app.processing.worker import TranslationWorker


class TestWorkerFailures(unittest.TestCase):
    def test_failed_and_missing_results_do_not_report_success(self):
        for results in (["[Translation Failed: বাংলা]"], []):
            with self.subTest(results=results), TemporaryDirectory() as directory:
                source = Path(directory) / "source.pdf"
                source.write_bytes(b"fake PDF for mocked extraction")
                paragraph = ParagraphModel("p1", "A philosophical sentence.")
                document = DocumentModel(source, source.name, 1, 1,
                                         pages=[PageModel(1, 612, 792, paragraphs=[paragraph])])
                with patch("app.processing.worker.PDFAnalyzer"), \
                     patch("app.processing.worker.TextExtractor") as extractor, \
                     patch("app.processing.worker.PageParser"), \
                     patch("app.processing.worker.OpenAITranslator") as translator, \
                     patch("app.processing.worker.TranslationCache") as cache, \
                     patch("app.processing.worker.JobManager") as jobs, \
                     patch("app.processing.worker.PDFBuilder") as builder:
                    extractor.return_value.extract_document.return_value = document
                    translator.return_value.translate_batch.return_value = results
                    cache.return_value.get.return_value = None
                    jobs.return_value.load_job.return_value = None
                    builder.return_value.build_pdf.return_value = Path(directory) / "out.pdf"
                    worker = TranslationWorker(source, use_ocr=False)
                    reports, failures = [], []
                    worker.job_finished.connect(lambda path, text: reports.append(text))
                    worker.job_failed.connect(failures.append)
                    worker.run()
                    self.assertEqual(failures, [])
                    self.assertEqual(jobs.return_value.save_job.call_args.args[0].status, "COMPLETED_WITH_ERRORS")
                    self.assertEqual(jobs.return_value.save_job.call_args.args[0].failed_blocks, 1)
                    self.assertIn("Review required", reports[0])
                    self.assertNotIn("successfully", reports[0])
                    cache.return_value.put.assert_not_called()


if __name__ == "__main__":
    unittest.main()
