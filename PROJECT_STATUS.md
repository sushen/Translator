# Project status and development handoff

Last updated: 2026-11-15 (Asia/Dhaka)

## Purpose

A Python/PySide6 desktop workbench for translating English PDFs into Bangla,
reviewing translations, and preparing books with covers and published PDFs.
The original README documents installation and the PDF translation workflow.

## Current snapshot

- Published GitHub source release `v-0.0.2` packages the current Studio/PDF improvements
  as source, with setup and limitations in `RELEASE_NOTES.md`. Local books,
  models, outputs and scratch files are ignored; the previously tracked cache
  and generated output samples are removed from Git's index, retained on disk.

- Studio can now open an existing translated PDF directly or reopen a saved
  project without an active translation job. Imported PDFs are embedded into the
  portable project; untouched pages are copied without reflow. Editing extracted
  text replaces that page's layout, so text extraction and image loss need review.
- Cover/title-page designer stores background and text as separate editable
  layers (title, author, Bangla translator, optional English translator, color,
  font sizes and vertical positions). Live preview uses actual PDF rendering;
  history retains prior designs/imported pages. Original imported-page restore
  is available. Imported Bangla needs manually attached source for AI refinement.

- Source-page-aware PDF flow is now the default: preserves source dimensions,
  derives text margins/gaps from extracted boxes, retains readable font sizes,
  and adds continuation pages without merging the following source page. Source
  page bookmarks/footers and an in-memory output mapping identify correspondence.
  Studio export uses the same pagination engine and preview selects continuations.
  Complex columns/tables and exact facsimile layout remain unsupported.

- Layout refinement: compact controls, slower padding growth during zoom,
  scrollable translation settings and book dashboard, wider default main window,
  and labeled Studio panels with more room for Bangla. Studio project actions
  now use a toolbar with overflow instead of a fixed row of large buttons.

- New separate **Translation Studio → Open translated-page editor** menu copies
  current translated source pages into an independent workspace. Supports manual
  rich-text editing, inline embedded images, saved JSON projects, page revision
  restore, actual PDF preview, and new-file-only PDF export.
- Cloud page refinement reuses OpenAI/gateway or Groq settings, proposes a full
  rewrite with reasons/ambiguities, and requires acceptance. Uses selected plus
  adjacent pages, not whole-book retrieval. Image-bearing pages require manual
  proposal merging. Studio edits do not update existing translation jobs.

Source inspection confirms the following modules exist. This is an inventory,
not a claim that every feature passes tests or works end to end.

| Area | Main source | Present in code |
| --- | --- | --- |
| Desktop UI | `main.py`, `app/gui/` | Main window, preview, book widget, report dialog |
| PDF processing | `app/pdf/`, `app/ocr/` | Analysis, extraction, paragraph/layout parsing, PDF building, OCR |
| Translation | `app/translation/` | OpenAI, Groq, Google, local NLLB, cache, validation, recheck |
| Background processing | `app/processing/` | Worker and SQLite job persistence/resume state |
| Human review | `app/document/paragraph_model.py`, `app/translation/ai_recheck.py` | Paragraph model and recheck engine; provider support or heuristic fallback |
| Books | `app/book/` | Book model and SQLite book manager |
| Covers and publishing | `app/cover/`, `app/publishing/` | Cover generator and cover/content PDF assembly with validation |
| Page selection | `app/utils/page_selection.py` | Page selection utility with dedicated tests |

The README does not fully describe the newer book/review/publishing workflow or
Groq provider. Synchronizing user documentation is a potential follow-up.

## Validation baseline

- Completed a comparison of physical PDF page 6 using identical extracted source
  blocks for local and cloud translation. Each provider returned four translated
  blocks. Final reading exports are Bangla only, as requested by the user.
- Local: installed NLLB 600M, experimental CPU dynamic int8 linear layers in the
  pilot script. Model preparation and inference took about 19 minutes together.
  The normal GUI local path has not been switched to this experimental mode.
- Cloud: authenticated third-party gateway, requested model `gpt-6.1-sol` from
  its advertised model list. The completed pilot took about 86 seconds after
  client setup, including fallback requests. Upstream model identity is not
  independently verified. Cloud requests for this comparison were explicitly
  authorized; further paid runs are not needed to regenerate exports.
- Fourteen local translation, gateway configuration, worker failure, and startup tests
  passed in the project virtual environment. One DOCX export test passed in the
  bundled document runtime. Both Word packages retain all translated blocks and
  exclude the English source. Source-block identity across providers was checked.
- Both final PDFs are one page and were visually inspected. Bengali fonts are
  embedded. PDF text extraction does not preserve all original Bangla codepoints;
  appearance alone must not be presented as proof of correct copying/search.
- Word visual rendering could not run: neither Word nor LibreOffice is installed.
  DOCX files are editable drafts with verified text/package structure, not a
  verified Word layout. Noto Bengali fonts must be available to the reader.
- An earlier broader 32-test run had 28 passes and four Windows temporary SQLite
  file cleanup errors in book-model and job-state tests. These remain unresolved.
- A real Qt GUI event test now passes 15 checks for physical page 6: browse,
  analysis, selection, configured gateway translation, progress/control state,
  result preview, human-edit save/restore, selected-page scope, and preservation
  of the source and older output. The initial fresh four-block translation
  succeeded with no cache hits; reruns reused saved results without API calls.
- Native Windows automation could read accessibility data, but screenshots timed
  out and mouse geometry/input was unavailable. Validation therefore used real
  Qt controls/events and widget snapshots with isolated test storage, not a
  complete manual desktop interaction test. Only the file picker and storage
  locations were substituted; the gateway, worker, dialogs, and PDF builder ran.
- OCR, a whole-book run, cancellation during a live network call, and the full
  publishing workflow remain untested. Passing one outline page is not proof of
  full-book translation quality.
- README test command: `python -m unittest discover tests`.
- README launch command: `python main.py`; dependencies: `requirements.txt`.

## Changes implemented

- Local translation splits overlong inputs without discarding source characters;
  generation-limit results and provider failure markers are rejected.
- Worker completion distinguishes runs with errors, checks batch result counts,
  and retries invalid restored/cached translations rather than accepting them.
- Gateway support: configurable API base URL, editable GUI model name, endpoint
  isolation in cache/job keys, and native Windows certificate trust with TLS
  verification enabled. A local ignored `.env` holds user-managed credentials;
  never print or copy its values into reports.
- Cloud prompt/output handling now agrees on JSON object structure, accepts plain
  individual translations, and unwraps accidental single-string JSON arrays.
- `app/document/docx_builder.py` exports Unicode Bangla and preserves human edits.
- Pilot tools under `tools/` perform extraction, isolated translation, and export.
  Their exports do not write to the user's translation cache or book/job state.
- Fixed a reproduced GUI preview bug: completed selected-page translations now
  populate review from the worker's result document rather than the source-only
  analysis document. The original source page count remains available.
- Human-edit saves use the current result document, job, and output file, keeping
  selected-page scope and avoiding overwriting an older output with a fixed name.
- Providers and local model discovery load lazily so cloud GUI startup does not
  import Torch. The bundled Bengali font is registered with Qt for GUI rendering.

## Comparison artifacts

- `output/page6_local/local_translation_serif.pdf`
- `output/page6_local/local_translation_review.docx`
- `output/page6_cloud/cloud_translation_serif.pdf`
- `output/page6_cloud/cloud_translation_review.docx`
- Each directory contains `pilot.json` with source/translation alignment and
  provenance. These contain document text and should remain local.
- `tmp/gui_e2e/report.json` records the passing automated GUI workflow, while
  `report_before_fix.json` records the reproduced preview failure. Widget images
  and the fresh translated units are saved beside them. The report identifies
  the GUI-generated PDF; these local test artifacts may include private text.

## Working tree context

At the initial inspection, `cache/translation_cache.db` was already modified and
`models/` was untracked. Their contents were not inspected or changed by this
task. Recheck Git status each session; do not discard these user/runtime assets.

## Next steps

The requested comparison exports are complete. The user also described a future
improvement workflow that takes English source plus the current corrected Bangla
and proposes a better version. The new separate Studio now implements cloud
revision proposals; the older review GUI still constructs `AIRecheckEngine()`
without a provider and performs heuristic checks.
Do not describe its PASS result as verified translation fidelity.

The GUI can use the configured gateway for translation after restarting. Word
export and the comparison runner are not wired to GUI buttons. Useful next work
is integrating Studio revisions with existing job records and expanding export
choices. Studio already offers explicit acceptance and independent history. Resolve PDF
Unicode extraction and verify Word layout before claiming production readiness.
The page-six GUI path now passes automated checks after the fixes above. Continue
with reviewed batches and a terminology policy rather than calling the whole
application or a full-book translation perfect on the basis of this sample.

## Development log

### 2026-11-15 — Publish GitHub source release v-0.0.2

- Prepared the accumulated application changes for the requested GitHub release;
  added release notes and excluded local books/models/outputs/scratch directories.
  Removed the runtime database and generated output samples from version control
  without deleting local files. Original PDFs, models and saved work are retained.
- Validation: 17 isolated tests passed across offscreen Studio/frontmatter/
  pagination, gateway configuration, lazy provider loading and worker failures;
  all 88 Python files compile; `git diff --cached --check` and credential-pattern
  scan passed (the README's documented fake key is excluded from that scan).
  PySide6 and MuPDF imports passed. Full unittest discovery was interrupted after
  prolonged dependency loading without test results. A timed diagnostic found
  OpenAI SDK import file reads; no paid calls or model downloads were requested.
  The project environment lacks `python-docx`, so DOCX tests were not verified
  in this release session. Existing broader-suite limitations remain above.
- Published the source release from commit `9d2ffb4` on branch `v-0.0.2`:
  https://github.com/sushen/Translator/releases/tag/v-0.0.2
- No manual GUI/end-to-end verification or standalone executable build was done.
  Next step: validate a clean install and broader test suite in a fully
  provisioned environment.

### 2026-11-10 — Prioritize the Bangla translator in cover design

- Added a translator-first layout with a separate large Bangla translator name,
  smaller author block, and subdued English/editor/publication credits at bottom.
  Added independent translator/author sizes and supporting-credit position.
- New designs use this layout. Existing projects retain the classic layout until
  the user selects the clearly labeled preset; identity fields, background and
  opacity are preserved. Apply/Cancel now remain outside the controls scroller,
  and preview fits available dialog width as well as height.
- Validation: all ten frontmatter/Studio tests passed; `git diff --check` passed.
  Visually reviewed the rendered Bangla hierarchy and the width-fitted dialog
  screenshot at a small offscreen screen size. No existing projects/PDFs
  replaced or paid requests made. Next step: restart, open the existing cover,
  select the translator-first preset, review, then Apply and Save.

### 2026-11-10 — Use publication label

- Changed the designer field and rendered credit label to the user's requested
  Bangla wording for publication. Stored publisher values remain unchanged.
- Validation: `git diff --check` and source search; no runtime tests needed for
  this label-only change. Restart to see the label in the designer/new exports.

### 2026-11-10 — Correct publisher transliteration

- Corrected the publisher default per user spelling. Opening a design carrying
  the previous exact misspelling also corrects the editable field; Apply/Save
  persists it. Other publisher values and existing project files are preserved.
- Validation: source search and `git diff --check`; no model/API calls.

### 2026-11-10 — Add Bangla editor and publisher credits

- Added editable Bangla-labeled editor/publisher fields to the cover/title-page
  designer, prefilled as requested. Nonempty values render below translator
  credits and persist with the existing design data; empty fields omit that line.
- Existing saved projects are not rewritten. Opening an older design prepopulates
  the new fields; Apply and Save persist them. Credits share the existing font
  size and vertical-position control, with overflow validation unchanged.
- Validation: three frontmatter tests and `git diff --check` passed. Visually
  inspected a synthetic Bangla render with all four credit lines enabled;
  editor/publisher text fits without overlap. No paid API calls were made.
  Next step: restart, review the fields on the current cover, then Apply/Save.

### 2026-11-10 — Select OpenAI by default

- Changed only the provider selection in the local ignored environment config
  to OpenAI, preserving other settings and credentials. The source fallback was
  already OpenAI; no GUI override was needed. Verified a fresh Settings instance
  resolves the provider to OpenAI. No API requests or model downloads performed.
- Restart the application for the startup provider selection to change.

### 2026-11-10 — Add text-panel opacity control

- Added 0–100% panel opacity to the cover/title-page designer, live preview,
  saved layer data and PDF rendering. New designs default to the requested 5%.
  Existing saved designs without this field retain 92% until explicitly changed;
  text itself remains fully opaque. No existing projects were overwritten.
- Validation: three frontmatter tests passed and `git diff --check` passed.
  Next step: restart, open the current cover, set Text panel opacity to 5%,
  Apply, and save the Studio project.

### 2026-11-10 — Add direct PDF editing and cover/title-page layers

- Added main-menu and Studio PDF import plus direct saved-project opening.
  Existing PDF bytes travel with the Studio project. Untouched pages are copied,
  while explicitly edited pages use the rich-text/continuation renderer.
- Added cover/title-page dialog with separate editable title/author/translator
  credits, optional English translator credit, embedded background, text color,
  fonts, vertical placement, readability panel, and actual-renderer live preview.
  Overlapping/non-fitting text is rejected instead of silently shrinking.
- Added prior-design snapshots, revision restore, and original imported-page
  restore. AI requires a manually attached original/reference passage for imported
  Bangla PDFs rather than treating Bangla extraction as English source.
- Eleven targeted Studio/frontmatter/pagination tests passed. Tests cover source
  preservation, unchanged-body render equivalence, editable metadata persistence,
  actual-text-edit detection, original-page restoration and overlap rejection.
  The final expanded run passed all 16 targeted checks including worker failures,
  gateway configuration, and provider loading; `git diff --check` also passed.
- Opened the user's supplied PDF locally: a draft project retains all 59 pages;
  replacing its first two pages leaves the checked third-page render unchanged.
  Visually reviewed both new frontmatter pages and the designer's offscreen Qt
  screenshot. Fixed missing dialog font registration found during visual review.
- Prepared an editable draft under `output/studio/`; original PDF is unchanged.
  No paid calls/downloads or manual desktop verification. Next step: open the
  draft in Studio, choose the desired clean cover background, review names/layout,
  save, and export to a new PDF. Plain imported-PDF text edits rebuild page layout;
  complex layout editing and reliable recovery of malformed PDF Unicode remain
  limitations. No claim of a perfect publishing tool is made.

### 2026-11-10 — Add readable source-page continuation layout

- Confirmed the old exporter discarded extracted text positions, used A4 in
  continuous reflow, and estimated paragraph boxes. Rendered source/output page
  six showed compressed Bangla layout; no linguistic accuracy conclusion drawn.
- Added a Story-based flow engine: no font shrinking, source-size output pages,
  source-derived text margins/spacing, paragraphs split across continuation pages,
  and a fresh start for the next source page. Blank source pages remain separate.
- Enabled this mode by default and relabeled the GUI checkbox; unchecked mode
  retains legacy continuous reflow. Added source-page bookmarks, continuation
  footers, and `PDFBuilder.last_page_map` for output correspondence.
- Studio now paginates longer edited text instead of shrinking to fit one page;
  preview navigation lists every output page with its source/continuation label.
- Synthetic tests verify complete repeated-text retention, readable font sizes,
  original dimensions, blank-page separation, source ordering, and Studio mapping.
  Twelve targeted checks passed across pagination, Studio, worker failures,
  gateway, and provider loading; after adding Studio overflow coverage, all eight
  final pagination/Studio tests passed again. `git diff --check` passed.
  Visually inspected synthetic Bangla first/continuation/next-source page renders
  under `tmp/pdfs/page_flow_check/`. No paid calls or existing PDF replacements.
- Limitations: exact facsimile positions, columns/tables, scanned-page OCR, and
  full-book output are not verified. Original source-page numbering in footers is
  physical PDF numbering. Next step: regenerate a reviewed cached book subset to
  a new filename and inspect its page mapping and typography on the desktop.

### 2026-11-10 — Add configurable book locations

- Added File → Book locations and a matching button in Translation Job input.
  Defaults discover a single English/reference PDF under `Book` and a single
  original PDF under the existing original-edition subfolder without renaming it.
- Folder and optional PDF paths are editable/browsable and remembered with Qt
  user settings. Startup selects the default reference PDF without analysis,
  translation, or paid requests. Browse opens in the configured book folder.
- Saving new defaults preserves the current open work. Original-edition path is
  stored as a reference only; multilingual passage alignment and sending that
  edition to refinement are not yet implemented. No book content was read.
- Validation: six Studio/provider-loading tests passed; offscreen startup
  confirmed three path fields, existing default PDFs, and default selection.
  `git diff --check` passed. No manual desktop verification. Next step: connect original-edition
  viewing/alignment when that workflow is requested.

### 2026-11-10 — Balance desktop layout and zoom proportions

- Reduced global button padding and removed forced minimum widths. Added
  consistent field styling, clearer button contrast, and compact toolbar/tab
  chrome. Zoom scales text fully while spacing grows more gently.
- Wrapped translation settings and book details in scroll areas, enabled long
  form-row wrapping, gave model settings more width, and made library columns
  size to their headings/content. Increased main window's initial size.
- Studio has labeled, aligned panels with a wider Bangla editor, project actions
  in an overflow toolbar, a shorter AI action, and wrapped explanatory text.
- Corrected text-view zoom isolation from control fonts. Ten targeted tests pass
  (five Studio plus gateway, provider-loading, and worker-failure tests), including
  preservation of export HTML during display zoom. `git diff --check` passes. Visually inspected
  offscreen renders using synthetic text/empty book storage at 125% and 175%;
  these are not manual desktop/end-to-end verification. No paid calls/downloads.
- Render artifacts and the isolated inspection helper are in
  `tmp/ui_layout_review/` and `tmp/review_ui_layout.py`. Next step: restart the
  app and check comfort on the user's monitor with their preferred zoom.

### 2026-11-10 — Add interface zoom controls

- Added a Display zoom toolbar and View menu in the main window and Studio,
  percentage selection from 75–200%, keyboard shortcuts, and remembered settings
  with a larger initial default of 125%.
- Studio serialization removes display magnification so exported typography is
  preserved. Zoom changes do not mark the Studio page edited.
- Five Studio tests pass, including zoom/export HTML invariance. Verification
  uses offscreen Qt; no manual desktop check or paid API call was performed.
- Restart the running application to load the new controls. Next step: check
  comfortable zoom on the user's monitor and review layout at higher settings.

### 2026-11-10 — Add Windows GUI launcher

- Added `Start GUI.bat` for double-click startup using the project virtual
  environment and project working directory; startup errors remain visible.
- Documented the launcher in README. No translation or model download required.

### 2026-11-10 — Add a separate translated-page studio

- Added the requested menu, page editor, embedded image insertion, simple text
  formatting, standalone project persistence/history, and PDF preview/export.
- Added background cloud refinement using existing settings; proposals remain
  separate until accepted and stale responses are discarded. No paid requests
  or model downloads were made for verification.
- Nine targeted automated tests passed: four new studio tests plus gateway,
  provider-loading, and worker-failure coverage. Verified the new menu through
  an offscreen MainWindow startup. `git diff --check` passed before final docs.
- Automated tests cover project roundtrip, source-model isolation, image export,
  history presence, response validation, and stale proposal rejection. No manual
  desktop verification or live cloud refinement was performed.
- Limits: inline layout only; export fits each source page (can shrink text);
  pictures require manual merging of AI proposals; existing jobs remain separate.
  Next step: manually review a saved book page and its exported PDF, then test an
  explicitly authorized cloud revision before expanding to whole-book context.

### 2026-11-10 — Verify the GUI translation and editing workflow

- Ran a fresh authorized gateway translation through real GUI controls and the
  background worker with isolated storage; all four selected blocks translated.
- Reproduced and fixed incorrect preview data, selected-page edit handling, and
  the older-output overwrite risk. Registered the bundled GUI font and deferred
  unused local-provider dependencies at startup.
- The expanded cached rerun passed 15 GUI checks including edit persistence,
  restoration, original-source preservation, and prior-output preservation.
- All 15 targeted automated tests passed after these fixes (14 project-runtime
  checks plus one bundled-runtime DOCX check); `git diff --check` passed.
- Native desktop capture/input limitations and untested full-book/quality areas
  are recorded above. No full-book translation was started.

### 2026-11-10 — Finish page six local and cloud comparison

- Completed the authorized local/cloud pilot and exported four Bangla-only files.
- Added gateway configuration, native verified TLS, robust translation result
  handling, and Word export support; verified with 14 targeted tests.
- Reviewed both PDF renders and checked Word text retention and source alignment.
- Recorded remaining PDF Unicode extraction, Word rendering, SQLite cleanup,
  GUI export integration, and model-powered revision limitations above.

### 2026-11-09 — Establish project continuity

- Added `AGENTS.md` to guide future sessions and require status updates after
  meaningful work.
- Added this current-state snapshot, module map, verification limits, and handoff.
- No application behavior changed; no automated tests run.

For future entries, record: change and reason; affected areas; checks and results;
remaining issues; user decisions; next concrete action.
