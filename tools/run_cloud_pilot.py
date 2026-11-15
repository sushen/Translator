"""Translate the exact extracted pilot units through the configured gateway."""
import copy
import json
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config.settings import settings
from app.document.paragraph_model import ParagraphModel
from app.translation.openai_translator import OpenAITranslator
from app.translation.translation_validator import TranslationValidator

source = Path(sys.argv[1])
out = Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
report = copy.deepcopy(json.loads(source.read_text(encoding="utf-8")))
report.update(provider="cloud", model=settings.openai_model, reviewed=False,
              provenance="Fresh cloud gateway translation of the same extracted source blocks as the local pilot")
report.pop("load_error", None)
for unit in report["units"]:
    unit.update(translation="", status="pending", error="")
if not settings.openai_api_key or any(mark in settings.openai_api_key for mark in ("*", "REPLACE", "&#", "\\")):
    raise SystemExit("Cloud key is empty or still masked. No request made.")
print(f"Translating {len(report['units'])} source blocks through the configured gateway", flush=True)
translator = OpenAITranslator()
start = time.monotonic()
try:
    paragraphs = [ParagraphModel(id=u["id"], text=u["source"], is_heading=u["is_heading"]) for u in report["units"]]
    results = translator.translate_batch(paragraphs)
    if len(results) != len(paragraphs):
        raise RuntimeError("Incomplete cloud batch")
    for unit, text in zip(report["units"], results):
        valid, reason = TranslationValidator.validate(unit["source"], text)
        unit.update(translation=text if valid else "", status="translated" if valid else "failed", error="" if valid else reason)
finally:
    report["elapsed_seconds"] = round(time.monotonic() - start, 1)
    report["successful"] = sum(u["status"] == "translated" for u in report["units"])
    report["failed"] = sum(u["status"] != "translated" for u in report["units"])
    (out / "pilot.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if translator.client:
        translator.client.close()
print(f"Cloud pilot: {report['successful']}/{len(report['units'])} translated", flush=True)
