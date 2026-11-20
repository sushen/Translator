"""Isolated, resumable French/English/Bangla reading pilot; no job/cache writes.

prepare performs local extraction/OCR only. translate makes authorized gateway
requests for pending units. render writes a new flowing HTML/PDF draft.
"""
import argparse
import hashlib
import html
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pymupdf


def normalized(text):
    return re.sub(r"\s+", " ", text).strip()


def joined(text):
    def unwrap(match):
        prefix, following = match.group(1), match.group(2)
        keep = prefix.casefold() in {'non', 'anti', 'quasi'} or following.isupper()
        return prefix + ('-' if keep else '') + following
    return normalized(re.sub(r"(\w+)-\s*\n(\w)", unwrap, text))


def save(path, data):
    temporary = path.with_suffix('.writing')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def prepare(args):
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    state = out / 'pilot.json'
    if state.exists():
        raise ValueError('Preparation refuses to replace an existing pilot; resume it instead.')
    units = []
    inventory = []
    with pymupdf.open(args.english) as doc:
        active = False
        for number in range(1, 39):
            page = doc[number - 1]
            inventory.append({'physical_page': number, 'extracted_characters': len(page.get_text().strip())})
            if not 28 <= number <= 37:
                continue
            for block in page.get_text('blocks'):
                if block[6] != 0:
                    continue
                raw = block[4].strip()
                if 'Introduction: Repetition and Difference' in raw:
                    active = True
                    continue
                if not active or not raw:
                    continue
                text = joined(raw)
                # Repair extractor-created one-word blocks and page continuations.
                merge = bool(units) and (len(units[-1]['english']) < 35 or text[0].islower()
                    or not re.search(r'[.!?…][\'"’”)]*\d*$', units[-1]['english']))
                fragment = {'page': number, 'bbox': list(block[:4]), 'raw': raw}
                if merge:
                    previous = units[-1]
                    sep = '' if re.search(r'\w-$', previous['english']) and text[0].islower() else ' '
                    if not sep:
                        previous['english'] = previous['english'][:-1]
                    previous['english'] += sep + text
                    previous['english_fragments'].append(fragment)
                    if number not in previous['english_pages']:
                        previous['english_pages'].append(number)
                else:
                    units.append({'id': f'en{number}-u{len(units)+1:03}', 'english': text,
                                  'english_pages': [number], 'english_fragments': [fragment],
                                  'status': 'pending', 'french': [], 'bangla': ''})
    if not units or units[0]['english_pages'] != [28]:
        raise ValueError('Expected Introduction opening not found on physical page 28; inspect source before proceeding.')
    french = []
    with pymupdf.open(args.french) as doc:
        for number in range(11, 21):
            stem = out / f'fr{number:03}'
            image = stem.with_suffix('.png')
            doc[number-1].get_pixmap(matrix=pymupdf.Matrix(3, 3)).save(image)
            subprocess.run([str(args.tesseract), str(image), str(stem), '--tessdata-dir',
                            str(args.tessdata), '-l', 'fra', '--psm', '3'], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            ocr = stem.with_suffix('.txt').read_text(encoding='utf-8').strip()
            french.append({'physical_page': number, 'printed_page': number-4, 'text': ocr,
                           'raw_extraction': doc[number-1].get_text(), 'method': 'Tesseract fra 300% raster'})
            print(f'OCR French physical page {number}', flush=True)
    data = {'schema_version': 1, 'scope': 'Introduction, English physical pages 28–37 only',
            'english_pdf': str(args.english), 'french_pdf': str(args.french),
            'source_hashes': {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in (args.english, args.french)},
            'english_inventory': inventory, 'french_pages': french, 'units': units,
            'reviewed': False, 'translation_complete': False,
            'notes': ['English physical-page references are authoritative; no inferred printed English folios.',
                      'English extraction blocks are heuristically joined; paragraph segmentation needs editorial review.',
                      'French OCR is retained verbatim. No French passage is generated from the English.',
                      'Draft machine translation and alignment; not independently certified.']}
    save(state, data)
    print(f'Prepared {len(units)} English paragraph candidates', flush=True)


def translate(args):
    from dotenv import load_dotenv
    load_dotenv(args.config, override=True)
    from app.translation.openai_translator import OpenAITranslator
    translator = OpenAITranslator()
    if not translator.client:
        raise ValueError('Configured gateway credentials unavailable; no request made.')
    path = args.output / 'pilot.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    data['model'] = translator.model
    system = '''You are a scholarly French/English/Bangla philosophy translation editor.
Align the supplied English paragraph candidates to their actual French source in
the provided French OCR pages. English is the sequence and translation reference.
Return JSON {"items":[{"id":"...","french":[{"page":11,"text":"EXACT verbatim OCR substring"}],
"bangla":"complete natural literary Bangla translation of this English unit",
"alignment_status":"matched or uncertain or no_counterpart","alignment_note":"brief specific explanation"}]}.
Return each English id exactly once. Preserve all English meaning, examples,
quotations and references in Bangla; never summarize. Use consistent terms:
difference পার্থক্য, repetition পুনরাবৃত্তি, generality সাধারণতা,
singularity অনন্যতা, general সাধারণ, universal সার্বজনীন, law বিধি,
representation উপস্থাপন, concept ধারণা. Adapt grammatical inflections naturally.
French text MUST be copied from supplied OCR, including OCR errors; do not repair,
translate back, or invent it. Select only corresponding passages, splitting at
page boundaries where necessary. French paragraph boundaries may differ from
English: multiple French passages can match one English unit. If a candidate
begins/ends mid-paragraph, align the corresponding fragment only. Omit page
headers/folios from selected passages. Explain substantive discrepancies;
use uncertain or no_counterpart when evidence is insufficient. Do not manufacture
a match. All these pages belong to the Introduction, not the prefaces.'''
    try:
        while pending := [u for u in data['units'] if u['status'] == 'pending']:
            batch = pending[:5]
            payload = {'english': [{'id': u['id'], 'pages': u['english_pages'], 'text': u['english']} for u in batch],
                       'french_ocr': [{'page': p['physical_page'], 'text': p['text']} for p in data['french_pages']]}
            print(f'Requesting {len(batch)} aligned translations; {len(pending)} pending', flush=True)
            response_path = args.output / f"response_{batch[0]['id']}.json"
            response = None
            if response_path.exists():
                raw = response_path.read_text(encoding='utf-8')
            else:
                response = translator.client.with_options(timeout=300, max_retries=0).chat.completions.create(
                    model=translator.model, messages=[{'role': 'system', 'content': system},
                    {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}],
                    response_format={'type': 'json_object'}, temperature=0.2, max_tokens=18000)
                raw = response.choices[0].message.content
                # Retain response before validation to avoid losing a paid result.
                with response_path.open('x', encoding='utf-8') as handle:
                    handle.write(raw)
            result = json.loads(raw)['items']
            if len(result) != len(batch) or {i['id'] for i in result} != {u['id'] for u in batch}:
                raise ValueError('Response IDs/count differ; saved raw response for recovery.')
            for unit in batch:
                item = next(i for i in result if i['id'] == unit['id'])
                bn = item['bangla'].strip()
                if not re.search(r'[\u0980-\u09ff]', bn):
                    raise ValueError('Missing Bangla result; response retained.')
                evidence = []
                for passage in item['french']:
                    page = next(p for p in data['french_pages'] if p['physical_page'] == passage['page'])
                    exact = normalized(passage['text']) in normalized(page['text'])
                    evidence.append(exact)
                unit.update(bangla=bn, french=item['french'], status='translated',
                            alignment_status=item['alignment_status'], alignment_note=item['alignment_note'],
                            french_verbatim_checks=evidence)
                if not all(evidence):
                    unit['alignment_status'] = 'uncertain'
                    unit['alignment_note'] += ' Automated check: selected French differs from OCR; review required.'
            data.setdefault('usage', []).append(response.usage.model_dump() if response and response.usage else {})
            data['translation_complete'] = all(u['status'] == 'translated' for u in data['units'])
            save(path, data)
            print(f"Saved {sum(u['status']=='translated' for u in data['units'])}/{len(data['units'])}", flush=True)
    finally:
        translator.client.close()


def render(args):
    data = json.loads((args.output/'pilot.json').read_text(encoding='utf-8'))
    body = ['<h1>পার্থক্য ও পুনরাবৃত্তি</h1><h2>Gilles Deleuze · Introduction</h2>',
            '<p class="meta">French → English → Bangla · English physical PDF pages 28–37 · Machine draft, editorial review pending. French OCR may contain errors.</p>']
    for unit in data['units']:
        label = ', '.join(map(str, unit['english_pages']))
        body.append(f'<div class="reference">English PDF page(s) {label} · {html.escape(unit["id"])}</div>')
        for passage in unit['french']:
            body.append(f'<div class="language">Français · PDF {passage["page"]} / printed {passage["page"]-4}</div><p lang="fr">{html.escape(joined(passage["text"]))}</p>')
        if not unit['french']:
            body.append('<p class="meta">French counterpart not established.</p>')
        body.append(f'<div class="language">English · Paul Patton</div><p lang="en">{html.escape(unit["english"])}</p>')
        body.append(f'<div class="language">বাংলা</div><p class="bangla" lang="bn">{html.escape(unit["bangla"] or "অনুবাদ অপেক্ষমাণ")}</p>')
        if unit.get('alignment_status') != 'matched':
            body.append(f'<p class="meta">Alignment review: {html.escape(unit.get("alignment_note", "pending"))}</p>')
    reading_markup = ''.join(body)
    body = ['<h2>Alignment notes</h2><p class="meta">These machine-generated notes record edition differences and paragraph boundaries for editorial review. They are not an independent fidelity assessment.</p>']
    for unit in data['units']:
        body.append(f'<p class="meta">{html.escape(unit["id"])}: {html.escape(unit.get("alignment_note", "pending"))}</p>')
    css = '''@font-face{font-family:Bangla;src:url(NotoSerifBengali-Regular.ttf)}
body{font-family:serif;font-size:12pt;line-height:1.5;color:#20242a}
h1{font-family:Bangla;font-size:24pt}h2{font-size:16pt}
h1,h2,.reference,.language{page-break-after:avoid}
p{margin:6pt 0 14pt}.bangla{font-family:Bangla;font-size:13pt;line-height:1.65}
.reference{font-family:sans-serif;font-size:10pt;color:#334f72;margin-top:24pt;border-top:1px solid #aab8c8;padding-top:10pt}
.language{font-family:Bangla;font-size:10pt;color:#596273;margin-top:10pt}
.meta{font-family:Bangla;font-size:9pt;color:#666}'''
    notes_markup = ''.join(body)
    markup = reading_markup + notes_markup
    fonts = ROOT/'assets/fonts'
    # HTML embeds the local font so the reading file can be moved independently.
    import base64
    embedded = base64.b64encode((fonts/'NotoSerifBengali-Regular.ttf').read_bytes()).decode()
    html_css = css.replace('url(NotoSerifBengali-Regular.ttf)', f'url(data:font/ttf;base64,{embedded})')
    for name in ('pilot.html', 'pilot.pdf'):
        if (args.output/name).exists():
            raise ValueError(f'Render refuses to replace {name}; choose a new output location or archive it first.')
    (args.output/'pilot.html').write_text(f'<!doctype html><html><head><meta charset="utf-8"><title>Deleuze trilingual pilot</title><style>{html_css}body{{max-width:760px;margin:40px auto;padding:0 24px}}</style></head><body>{markup}</body></html>', encoding='utf-8')
    from app.pdf.page_flow import append_source_page
    with pymupdf.open() as doc:
        for section in (reading_markup, notes_markup):
            append_source_page(doc, section, 612, 792, pymupdf.Rect(52,48,560,744), css, pymupdf.Archive(str(fonts)))
        for number, page in enumerate(doc):
            page.insert_text((52, 770), f'Difference and Repetition | Trilingual pilot | {number+1} / {len(doc)}', fontsize=8, color=(.4,.4,.4))
        doc.save(str(args.output/'pilot.pdf'))
    with pymupdf.open(args.output/'pilot.pdf') as doc:
        for number in [0, 1, len(doc)-1]:
            doc[number].get_pixmap(matrix=pymupdf.Matrix(1.3,1.3)).save(str(args.output/f'preview_{number+1}.png'))
        print(f'Rendered {len(doc)} flowing output pages', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'translate', 'render'])
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--english', type=Path)
    parser.add_argument('--french', type=Path)
    parser.add_argument('--config', type=Path, default=ROOT/'.env')
    parser.add_argument('--tesseract', type=Path, default=Path(r'C:\Program Files\Tesseract-OCR\tesseract.exe'))
    parser.add_argument('--tessdata', type=Path, default=ROOT/'tmp/trilingual_inspection')
    arguments = parser.parse_args()
    globals()[arguments.action](arguments)
