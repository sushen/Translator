"""Run a small, isolated local-model pilot without changing user caches or jobs."""
import argparse
import json
import sys
import time
import faulthandler
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--pages", default="21,27,32", help="One-based PDF page numbers")
    parser.add_argument("--output", type=Path, default=Path("output/local_pilot"))
    parser.add_argument("--tiny", action="store_true", help="Translate just the first prose sentence")
    parser.add_argument("--int8", action="store_true", help="Use experimental CPU dynamic int8 linear layers to reduce memory pressure")
    parser.add_argument("--debug-loading", action="store_true")
    args = parser.parse_args()
    if args.debug_loading:
        faulthandler.dump_traceback_later(90, repeat=True)
    args.output.mkdir(parents=True, exist_ok=True)
    pages = [int(p) for p in args.pages.split(",")]
    if args.tiny:
        pages = pages[:1]
    import pymupdf
    import torch
    torch.set_num_threads(2)
    from app.pdf.text_extractor import TextExtractor
    from app.pdf.page_parser import PageParser
    from app.translation.local_translator import LocalTranslator
    from app.translation.translation_validator import TranslationValidator

    with pymupdf.open(args.source) as source, pymupdf.open() as excerpt:
        for p in pages:
            if not 1 <= p <= len(source):
                raise ValueError(f"PDF page out of range: {p}")
            excerpt.insert_pdf(source, from_page=p-1, to_page=p-1)
        excerpt.save(args.output / "source_excerpt.pdf")
    document = TextExtractor(extract_images=False).extract_document(args.output / "source_excerpt.pdf")
    page_parser = PageParser()
    units = []
    for original_page, page in zip(pages, document.pages):
        page_parser.parse_page(page)
        for p in page.paragraphs:
            if p.is_page_number or not p.text.strip():
                continue
            units.append({"id": p.id, "page": original_page, "source": p.text,
                          "is_heading": p.is_heading, "translation": "", "status": "pending"})
    if args.tiny:
        unit = next(u for u in units if len(u["source"]) > 100 and not u["is_heading"])
        unit["source"] = re.split(r'(?<=[.!?])\s+', unit["source"], maxsplit=1)[0]
        units = [unit]
    report = {"source": str(args.source.resolve()), "pages": pages,
              "model": "facebook/nllb-200-distilled-600M", "reviewed": False,
              "comparison": "Local model only; cloud credentials unavailable",
              "units": units}
    def save():
        (args.output / "pilot.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    save()
    translator = LocalTranslator(batch_size=1, max_length=256)
    print(f"Extracted {len(units)} paragraphs from PDF pages {pages}. Loading local model...", flush=True)
    start = time.monotonic()
    try:
        translator._get_model_and_tokenizer()
        if args.int8:
            print("Quantizing CPU linear layers to int8 for lower memory use...", flush=True)
            manager = translator.model_manager
            manager._model = torch.ao.quantization.quantize_dynamic(
                manager._model, {torch.nn.Linear}, dtype=torch.qint8, inplace=True
            )
            report["precision"] = "CPU dynamic int8 linear layers; embeddings unchanged"
            save()
            print("CPU int8 model ready", flush=True)
        for i, unit in enumerate(units, 1):
            print(f"Translating {i}/{len(units)} (source PDF page {unit['page']})", flush=True)
            try:
                text = translator.translate_paragraph(unit["source"], unit["is_heading"])
                valid, reason = TranslationValidator.validate(unit["source"], text)
                unit.update(translation=text if valid else "", status="translated" if valid else "failed", error="" if valid else reason)
            except Exception as exc:
                unit.update(status="failed", error=str(exc))
            save()
    except Exception as exc:
        report["load_error"] = str(exc)
        print(f"MODEL LOAD FAILED: {exc}", flush=True)
    finally:
        report["elapsed_seconds"] = round(time.monotonic() - start, 1)
        report["successful"] = sum(u["status"] == "translated" for u in units)
        report["failed"] = sum(u["status"] == "failed" for u in units)
        save()
        translator.unload()
    print(f"Pilot finished: {report['successful']}/{len(units)} translated. See {args.output / 'pilot.json'}", flush=True)
    faulthandler.cancel_dump_traceback_later()


if __name__ == "__main__":
    main()
