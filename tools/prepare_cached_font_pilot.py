"""Prepare a tiny rendering specimen from an existing successful local translation."""
import json
import re
import sqlite3
from pathlib import Path
import pymupdf

root = Path(__file__).resolve().parents[1]
source = next((root / "book").glob("*.pdf"))
with sqlite3.connect(f"file:{(root / 'cache/translation_cache.db').as_posix()}?mode=ro", uri=True) as connection:
    rows = connection.execute("SELECT source_text,target_text,model_name FROM translation_cache WHERE model_name LIKE 'local-%' ORDER BY length(source_text)").fetchall()
    text, translated, model = next(row for row in rows if any('\u0980' <= c <= '\u09ff' for c in row[1]) and not row[1].startswith('['))
normalize = lambda value: re.sub(r'\s+', ' ', value).strip().lower()
with pymupdf.open(source) as document:
    page_number = next(i+1 for i in range(min(20, len(document))) if normalize(text[:50]) in normalize(document[i].get_text()))
out = root / "output/font_pilot"
out.mkdir(parents=True, exist_ok=True)
data = {"source": str(source), "pages": [page_number], "model": model,
        "reviewed": False, "provenance": "Existing local-model cache entry reused for font and export testing; not a fresh inference or quality benchmark",
        "successful": 1, "failed": 0,
        "units": [{"id": "cached_local_specimen", "page": page_number, "source": text,
                   "translation": translated, "is_heading": False, "status": "translated"}]}
(out / "pilot.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Prepared cached local specimen from source PDF page {page_number}")
