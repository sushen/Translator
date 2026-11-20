"""Portable paragraph-aligned projects, independent of legacy jobs and caches."""
import copy
import hashlib
import html
import json
import os
import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

FORMAT = 'trilingual-book-v1'


def normalized(text):
    return re.sub(r'\s+', ' ', text).strip()


def unwrap(text):
    def replace(m):
        left, right = m.groups()
        return left + ('-' if right.isupper() or left.lower() in {'non', 'anti', 'quasi'} else '') + right
    return normalized(re.sub(r'(\w+)-\s*\n(\w)', replace, text))


def new_project(english='', french=''):
    return dict(format=FORMAT, id=uuid.uuid4().hex, title='Trilingual reading project',
                english_pdf=str(english), french_pdf=str(french), units=[], french_pages=[],
                english_pages=[], batches=[], archived_units=[], source_hashes={})


def load_project(path):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if data.get('format') != FORMAT:
        if data.get('schema_version') != 1 or not isinstance(data.get('units'), list) or not data.get('english_pdf'):
            raise ValueError('Choose a Trilingual Book project or an existing trilingual pilot JSON file.')
        imported = new_project(data['english_pdf'], data.get('french_pdf', ''))
        imported.update({k: copy.deepcopy(data[k]) for k in ('units', 'french_pages', 'source_hashes', 'notes') if k in data})
        imported['imported_from'] = str(Path(path).resolve())
        imported['title'] = 'Difference and Repetition · Introduction pilot'
        data = imported
    if not isinstance(data.get('units'), list) or not isinstance(data.get('french_pages'), list):
        raise ValueError('Invalid trilingual project structure.')
    data.setdefault('title','Trilingual reading project')
    data.setdefault('english_pdf','');data.setdefault('french_pdf','')
    for page in data['french_pages']:
        if not isinstance(page.get('physical_page'),int) or not isinstance(page.get('text'),str):
            raise ValueError('Invalid prepared French page.')
    ids = set()
    for u in data['units']:
        if not isinstance(u.get('id'), str) or u['id'] in ids or not isinstance(u.get('english'), str):
            raise ValueError('Invalid or duplicate reading unit.')
        ids.add(u['id'])
        if not isinstance(u.get('bangla', ''), str) or not isinstance(u.get('french', []), list):
            raise ValueError('Invalid reading text.')
        for p in u.get('french', []):
            if not isinstance(p.get('page'), int) or not isinstance(p.get('text'), str):
                raise ValueError('Invalid French reference.')
        u.setdefault('history', [])
        u.setdefault('alignment_status', 'unmatched')
        u.setdefault('bangla', '')
        u.setdefault('french', [])
        u.setdefault('english_pages', [])
    return data


def save_project(data, path):
    path = Path(path)
    if path.suffix.lower() != '.json':
        raise ValueError('Save the editable project as a .json file.')
    if any(path.resolve() == Path(data.get(k, '')).resolve() for k in ('english_pdf', 'french_pdf')):
        raise ValueError('Project cannot replace a source PDF.')
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def revise(unit, changes, reason='Manual edit'):
    changes = {k: v for k, v in changes.items() if unit.get(k) != v}
    if not changes:
        return False
    snapshot = {k: copy.deepcopy(v) for k, v in unit.items() if k != 'history'}
    unit.setdefault('history', []).append(dict(at=datetime.now(timezone.utc).isoformat(), reason=reason, unit=snapshot))
    unit.update(copy.deepcopy(changes))
    if {'english', 'french', 'bangla'} & changes.keys():
        unit.pop('proposal', None)
    if {'english', 'french'} & changes.keys():
        unit['alignment_status'] = 'needs_review'
        unit.pop('proposal', None)
    return True


def fingerprint(unit):
    return hashlib.sha256(json.dumps([unit.get(k) for k in ('english','french','bangla')],
                                    ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def evidence_check(project, passages):
    results = []
    for passage in passages:
        corpus = next((p for p in project['french_pages'] if p['physical_page'] == passage['page']), None)
        results.append(bool(corpus and normalized(passage['text']) and
                            normalized(passage['text']) in normalized(corpus['text'])))
    return bool(results) and all(results)


def apply_proposal(project, unit, kind):
    proposal = unit.get('proposal', {})
    if proposal.get('kind') != kind:
        raise ValueError('No matching proposal to accept.')
    if proposal.get('basis') != fingerprint(unit):
        unit.pop('proposal', None)
        raise ValueError('Text changed after this proposal. Request a fresh proposal.')
    if kind == 'align':
        status = proposal.get('alignment_status', 'uncertain')
        missing_counterpart = status == 'no_counterpart' and not proposal['french']
        if not missing_counterpart and not evidence_check(project, proposal['french']):
            status = 'uncertain'
        revise(unit, {'french': proposal['french']}, 'Accepted alignment proposal')
        unit.update(alignment_status=status, alignment_note=proposal.get('alignment_note', ''))
    else:
        revise(unit, {'bangla': proposal['bangla'], 'status': 'translated'}, 'Accepted translation proposal')
    unit.pop('proposal', None)


def split_unit(project, index, position):
    unit = project['units'][index]
    if not 0 < position < len(unit['english']):
        raise ValueError('Place the English cursor between the two paragraphs to split.')
    original = copy.deepcopy(unit)
    right = copy.deepcopy(unit)
    right.update(id=uuid.uuid4().hex, english=unit['english'][position:].strip(), bangla='', french=[],
                 history=[], status='pending', alignment_status='unmatched',
                 alignment_note='Split unit: redistribute French and Bangla from the preceding unit.')
    revise(unit, {'english': unit['english'][:position].strip()}, 'Split English unit; original retained in history')
    unit['alignment_note'] = 'Split unit: redistribute existing French/Bangla between both units before review.'
    right.pop('proposal', None)
    project.setdefault('archived_units', []).append(original)
    project['units'].insert(index+1, right)


def join_units(project, index):
    if index+1 >= len(project['units']):
        raise ValueError('No following unit to join.')
    left, right = project['units'][index:index+2]
    project.setdefault('archived_units', []).append(copy.deepcopy(right))
    revise(left, {'english': left['english']+'\n\n'+right['english'],
                  'bangla': '\n\n'.join(filter(None, (left['bangla'], right['bangla']))),
                  'french': left['french']+right['french'],
                  'english_pages': sorted(set(left['english_pages']+right['english_pages']))}, 'Joined adjacent units')
    left['english_fragments'] = left.get('english_fragments', [])+right.get('english_fragments', [])
    project['units'].pop(index+1)


def export_project(project, pdf_path, html_only=False):
    """New-file-only pair; readable continuous flow, no per-source page constraint."""
    import base64
    import pymupdf
    from app.fonts.font_manager import FontManager
    from app.pdf.page_flow import append_source_page
    pdf_path = Path(pdf_path)
    if pdf_path.suffix.lower() != ('.html' if html_only else '.pdf'):
        raise ValueError('Choose an .html output filename.' if html_only else 'Choose a .pdf output filename.')
    html_path = pdf_path if html_only else pdf_path.with_suffix('.html')
    if (not html_only and pdf_path.exists()) or html_path.exists():
        raise ValueError('Choose a new export name; existing PDF/HTML files are never overwritten.')
    units = [u for u in project['units'] if not u.get('excluded')]
    if not units:
        raise ValueError('There are no included reading units to export.')
    font = Path(FontManager.get_instance().get_font_path('Noto Serif Bengali'))
    css = f'''@font-face{{font-family:BN;src:url({font.name})}}
body{{font-family:serif;font-size:12pt;line-height:1.5;color:#20242a}}
h1,.bn{{font-family:BN}}h1{{font-size:23pt}}.bn{{font-size:13pt;line-height:1.65}}
.ref{{font-family:sans-serif;font-size:10pt;color:#335577;border-top:1px solid #abbaca;margin-top:24pt;padding-top:10pt}}
.label,.note{{font-family:BN;font-size:9pt;color:#606975}}p{{margin:6pt 0 14pt}}
h1,h2,.ref,.label{{page-break-after:avoid}}'''
    esc = lambda s: html.escape(str(s)).replace('\n', '<br>')
    body = [f'<h1>{esc(project["title"])}</h1><p class="note">French → English → Bangla · Editorial draft · Physical PDF page references</p>']
    notes = ['<h2>Alignment and review notes</h2>']
    for u in units:
        body.append(f'<div class="ref">English PDF {esc(", ".join(map(str,u["english_pages"])))} · {esc(u["id"])}</div>')
        for f in u['french']:
            body.append(f'<div class="label">Français · PDF {f["page"]}</div><p>{esc(unwrap(f["text"]))}</p>')
        if not u['french']:
            body.append('<p class="note">French counterpart not established.</p>')
        body += [f'<div class="label">English</div><p>{esc(u["english"])}</p>',
                 f'<div class="label">বাংলা</div><p class="bn">{esc(u["bangla"] or "অনুবাদ অপেক্ষমাণ")}</p>']
        notes.append(f'<p class="note">{esc(u["id"])} · {esc(u.get("alignment_status","unmatched"))}: {esc(u.get("alignment_note", ""))}</p>')
    body.append('<p class="note">End of aligned reading batch.</p>')
    notes.append('<p class="note">End of alignment notes.</p>')
    sections = (''.join(body), ''.join(notes))
    if not html_only:
        with pymupdf.open() as doc:
            for section in sections:
                append_source_page(doc, section, 612, 792, pymupdf.Rect(52,48,560,744), css, pymupdf.Archive(str(font.parent)))
            text = ' '.join(p.get_text() for p in doc)
            if 'End of aligned reading batch.' not in text or 'End of alignment notes.' not in text:
                raise ValueError('PDF pagination omitted trailing content. Project is safe; export HTML separately or reduce the batch.')
            for n, page in enumerate(doc):
                page.insert_text((52,770),f'Trilingual reading draft | {n+1} / {len(doc)}',fontsize=8)
            pdf = doc.tobytes()
    font_data = base64.b64encode(font.read_bytes()).decode('ascii')
    html_css = css.replace(f'url({font.name})',f'url(data:font/ttf;base64,{font_data})')
    content = f'<!doctype html><html><head><meta charset="utf-8"><title>Trilingual reading</title><style>{html_css}body{{max-width:760px;margin:40px auto;padding:20px}}</style></head><body>{"".join(sections)}</body></html>'
    # Exclusive creation also protects against a file appearing after the initial check.
    if not html_only:
        with pdf_path.open('xb') as f:
            f.write(pdf)
    with html_path.open('x',encoding='utf-8') as f:
        f.write(content)
    return (str(html_path),) if html_only else (str(pdf_path), str(html_path))
