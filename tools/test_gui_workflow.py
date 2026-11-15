"""Exercise the real Qt GUI and real configured gateway on physical PDF page six.

Only the native file picker and storage locations are substituted. Translation,
worker threads, controls, dialogs, preview, and PDF generation are real.
"""
import json
import hashlib
import os
import sys
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt, QTimer, QEventLoop
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
from app.gui.main_window import MainWindow
from app.gui.dialogs.report_dialog import ReportDialog
from app.processing.pipeline import JobManager
from app.translation.translation_cache import TranslationCache
from app.book.book_manager import BookManager


def main():
    output = ROOT / "tmp/gui_e2e"
    output.mkdir(parents=True, exist_ok=True)
    source = next((ROOT / "Book").glob("*.pdf"))
    original_source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    previous_output = ROOT / "output" / f"{source.stem}_Bangla.pdf"
    previous_output_hash = hashlib.sha256(previous_output.read_bytes()).hexdigest() if previous_output.exists() else None
    database = output / "translation_cache.db"
    app = QApplication.instance() or QApplication([])
    report = {"test": "Qt GUI physical page six cloud translation", "checks": {}, "errors": []}
    patches = [
        patch("app.gui.main_window.JobManager", side_effect=lambda: JobManager(database)),
        patch("app.processing.worker.JobManager", side_effect=lambda: JobManager(database)),
        patch("app.processing.worker.TranslationCache", side_effect=lambda: TranslationCache(database)),
        patch("app.gui.widgets.book_widget.BookManager", side_effect=lambda: BookManager(output / "books.db")),
        patch.object(QFileDialog, "getOpenFileName", return_value=(str(source), "PDF Files (*.pdf)")),
    ]
    for item in patches:
        item.start()
    window = MainWindow()
    window.show()
    app.processEvents()
    window.tabs.setCurrentIndex(1)
    window.provider_combo.setCurrentText("OpenAI")
    window.page_mode_combo.setCurrentText("Specific Pages")
    window.page_specific_edit.setText("6")
    window.font_combo.setCurrentText("Noto Serif Bengali")
    window.chk_images.setChecked(False)
    window.chk_ocr.setChecked(False)
    QTest.mouseClick(window.browse_btn, Qt.LeftButton)
    report["checks"]["file_selected_through_browse"] = window.input_pdf_path == source
    QTest.mouseClick(window.analyze_btn, Qt.LeftButton)
    report["checks"]["analysis_completed"] = bool(window.analyzed_doc and window.translate_btn.isEnabled())
    report["checks"]["only_physical_page_six_selected"] = window._get_page_selection().get_selected_pages(window.analyzed_doc.total_pages) == [6]
    window.grab().save(str(output / "configured.png"))
    print("GUI configured and source analyzed; translating only physical page six", flush=True)
    finished = QEventLoop()
    def close_dialogs():
        for widget in app.topLevelWidgets():
            if isinstance(widget, ReportDialog) and widget.isVisible():
                widget.grab().save(str(output / "completion_dialog.png"))
                widget.accept()
            elif isinstance(widget, QMessageBox) and widget.isVisible():
                if widget.icon() in (QMessageBox.Warning, QMessageBox.Critical):
                    report["errors"].append(widget.text())
                widget.accept()
    dialog_timer = QTimer()
    dialog_timer.timeout.connect(close_dialogs)
    dialog_timer.start(250)
    QTest.mouseClick(window.translate_btn, Qt.LeftButton)
    if not hasattr(window, "worker"):
        raise RuntimeError("Translate button did not create a worker")
    report["checks"]["controls_disabled_while_running"] = not window.translate_btn.isEnabled() and window.cancel_btn.isEnabled()
    def success(path, summary):
        report["output_pdf"] = path
        report["summary"] = summary
        finished.quit()
    def failure(message):
        report["errors"].append(message)
        finished.quit()
    window.worker.job_finished.connect(success)
    window.worker.job_failed.connect(failure)
    timeout = QTimer()
    timeout.setSingleShot(True)
    timeout.timeout.connect(lambda: (report["errors"].append("GUI translation exceeded test timeout"), window.worker.cancel(), finished.quit()))
    timeout.start(300000)
    finished.exec()
    timeout.stop()
    window.worker.wait(5000)
    job = JobManager(database).find_job_by_path(str(source))
    report["checks"]["worker_completed_without_failed_blocks"] = bool(job and job.status == "COMPLETED" and job.failed_blocks == 0)
    report["checks"]["controls_reenabled"] = window.translate_btn.isEnabled() and not window.cancel_btn.isEnabled()
    expected = {key: unit for key, unit in (job.units_map if job else {}).items() if unit.get("status") == "translated"}
    visible = {p.id: p.current_translation for p in window.preview_widget.paragraphs}
    report["checks"]["preview_contains_selected_translations"] = bool(expected) and all(visible.get(key) == (unit.get("human_translation") or unit.get("translated_text") or unit.get("ai_translation")) for key, unit in expected.items())
    report["checks"]["preview_limited_to_selected_page"] = set(visible) == set(expected)
    report["translated_blocks"] = len(expected)
    report["preview_blocks"] = len(visible)
    report["source_total_pages"] = window.analyzed_doc.total_pages
    report["checks"]["source_page_count_preserved"] = window.analyzed_doc.total_pages == 528
    window.tabs.setCurrentIndex(2)
    app.processEvents()
    if report["checks"]["preview_contains_selected_translations"]:
        preview = window.preview_widget
        preview.table.selectRow(0)
        paragraph = preview._get_current_paragraph()
        original = paragraph.current_translation
        edited = original + " পরীক্ষামূলক সংশোধন"
        preview.target_text_edit.setPlainText(edited)
        QTest.mouseClick(preview.save_edit_btn, Qt.LeftButton)
        saved = JobManager(database).load_job(window.current_job_id)
        report["checks"]["human_edit_persisted"] = saved.units_map[paragraph.id]["human_translation"] == edited
        report["checks"]["edit_kept_selected_pages"] = set(saved.units_map) == set(expected)
        report["checks"]["edit_kept_current_output_path"] = str(window.current_output_path) == report["output_pdf"]
        # Restore the original wording through the same GUI control before delivery.
        preview.target_text_edit.setPlainText(original)
        QTest.mouseClick(preview.save_edit_btn, Qt.LeftButton)
        restored = JobManager(database).load_job(window.current_job_id)
        report["checks"]["test_edit_restored"] = restored.units_map[paragraph.id]["human_translation"] == original
    report["checks"]["source_pdf_unchanged"] = hashlib.sha256(source.read_bytes()).hexdigest() == original_source_hash
    report["checks"]["previous_output_unchanged"] = previous_output_hash is None or hashlib.sha256(previous_output.read_bytes()).hexdigest() == previous_output_hash
    window.grab().save(str(output / "review.png"))
    dialog_timer.stop()
    report["passed"] = all(report["checks"].values()) and not report["errors"]
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if job:
        (output / "translated_units.json").write_text(json.dumps(job.units_map, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "checks": report["checks"], "translated_blocks": len(expected), "preview_blocks": len(visible)}, indent=2), flush=True)
    window.close()
    for item in reversed(patches):
        item.stop()
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
