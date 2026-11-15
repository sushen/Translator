# English → Bangla PDF Translator

For the current development snapshot, verification status, and handoff history,
see [PROJECT_STATUS.md](PROJECT_STATUS.md). Contributor and agent continuity
guidance is in [AGENTS.md](AGENTS.md).

A production-quality Python PySide6 desktop application for translating English PDF documents into beautifully formatted Unicode Bangla (Bengali) PDFs with complete document structure preservation, accurate Bengali typography/script shaping, translation caching, interrupted job resume support, OCR fallback, and side-by-side preview.

---

## Table of Contents
1. [Key Features](#key-features)
2. [Architecture Overview](#architecture-overview)
3. [Prerequisites & Installation](#prerequisites--installation)
4. [Environment Configuration & API Key Setup](#environment-configuration--api-key-setup)
5. [Google Cloud Translation Setup](#google-cloud-translation-setup)
6. [How to Launch & Use the Application](#how-to-launch--use-the-application)
7. [Side-by-Side Preview](#side-by-side-preview)
8. [Translation Cache & Job Resume System](#translation-cache--job-resume-system)
9. [Bengali Font Handling & Script Shaping](#bengali-font-handling--script-shaping)
10. [OCR Fallback for Scanned Pages](#ocr-fallback-for-scanned-pages)
11. [Running Automated Tests](#running-automated-tests)
12. [Troubleshooting & FAQs](#troubleshooting--faqs)

---

## Key Features

- **Multiple Translation Providers**: Supports OpenAI (`gpt-4o`, `gpt-4o-mini`), **Local AI Translator** (Meta NLLB-200 local model - 100% free, offline, no API key), official Google Cloud Translation API (`en` → `bn`), and offline `mock-translator`.
- **Document Analysis & Detection**: Automatically counts pages, measures text density, and detects scanned/image vs. selectable text pages.
- **Structure Preservation**: Preserves paragraph flow, story headings, page numbers, margins, images, and visual hierarchy.
- **Natural Bengali Typography**: Uses embedded `Noto Sans Bengali` / `Noto Serif Bengali` fonts with MuPDF HTML shaping engine to ensure flawless rendering of Bengali complex scripts, conjuncts (যুক্তাক্ষর), and vowel signs (কার).
- **Persistent Translation Cache**: Uses SQLite database with SHA-256 keys to avoid re-translating identical text chunks across sessions and save API costs (with provider isolation).
- **Interrupted Job Resume**: Automatically saves translation state chunk-by-chunk; if interrupted, restarting resumes from the exact paused location.
- **Side-by-Side Paragraph Inspection**: Built-in tab for side-by-side verification of original English paragraphs alongside Bangla translations.
- **OCR Support**: Integrates `pytesseract` and `pdf2image` for automatic fallback on scanned PDF pages.
- **Safety First**: Never modifies or overwrites the original input PDF.

---

## Architecture Overview

```
app/
├── main.py                     # GUI Application Entry Point
├── config/
│   └── settings.py             # Settings & Environment Configuration
├── gui/
│   ├── main_window.py          # PySide6 Main Application Window
│   ├── widgets/
│   │   └── preview_widget.py   # Side-by-Side Preview Widget
│   ├── dialogs/
│   │   └── report_dialog.py    # Translation Summary Job Report Dialog
│   └── styles/
│       └── theme.py            # GUI Styling Theme
├── pdf/
│   ├── analyzer.py             # PDF Page Density & Scanned Page Detection
│   ├── text_extractor.py       # PyMuPDF Block, Line & Font Extractor
│   ├── page_parser.py          # Paragraph Reconstruction & Page Number Filter
│   ├── layout_analyzer.py      # Story Heading & Layout Structure Classifier
│   └── pdf_builder.py          # PyMuPDF Unicode Bangla PDF Generator
├── ocr/
│   └── ocr_engine.py           # Tesseract OCR Integration Wrapper
├── translation/
│   ├── translator.py           # Abstract Base Translator Interface
│   ├── openai_translator.py    # Official OpenAI SDK & Mock Translators
│   ├── google_translator.py    # Official Google Cloud Translation API Provider
│   ├── local_translator.py     # Local AI NLLB-200 Multilingual Model Translator
│   ├── model_manager.py        # Model Download, Device Placement & RAM/VRAM Lifecycle Manager
│   ├── translation_cache.py    # SQLite SHA-256 Translation Cache
│   ├── translation_validator.py# Bengali Unicode & Integrity Validator
│   └── prompts.py              # Literary Bangla Translation Prompts
├── document/
│   ├── document_model.py       # High-level Document Model
│   ├── page_model.py           # Page Model & Bounding Boxes
│   ├── block_model.py          # Extraction Block Model
│   └── paragraph_model.py      # Reconstructed Paragraph Unit Model
├── fonts/
│   └── font_manager.py         # Bengali Font Discovery & Validation
├── processing/
│   ├── pipeline.py             # Job State & Resume Persistence Manager
│   └── worker.py               # Background PySide6 QThread Worker
└── utils/
    ├── logging.py              # Centralized Application Logging
    └── paths.py                # Platform Path Resolution Utilities

assets/
└── fonts/
    ├── NotoSansBengali-Regular.ttf
    └── NotoSerifBengali-Regular.ttf
```

---

## Prerequisites & Installation

### Requirements
- **Python Version**: Python 3.10 or higher (Tested on Python 3.12).
- **Tesseract OCR (Optional for scanned PDFs)**: Installed system binary for `tesseract`.

### Setup Steps
1. Clone or extract the repository.
2. Create and activate a virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install required Python packages:
   ```bash
   pip install -r requirements.txt
   ```

---

## Environment Configuration & API Key Setup

For an OpenAI-compatible third-party gateway, set `OPENAI_BASE_URL` to its API
address (typically ending in `/v1`), `OPENAI_MODEL` to a model available through
that gateway, and `OPENAI_API_KEY` to its key. The OpenAI settings panel also
accepts a custom API base URL and editable model name. Gateway credentials and
model access must be verified separately. Keep `.env` local; it is ignored by Git.

Create a `.env` file in the project root directory (or copy from `.env.example`):
```bash
cp .env.example .env
```
Edit `.env` to set your OpenAI API key and model or Google credentials:
```env
TRANSLATION_PROVIDER=openai
OPENAI_API_KEY=sk-your-actual-api-key-here
OPENAI_MODEL=gpt-4o-mini

# Google Cloud Translation Settings (Optional if using Google Provider)
GOOGLE_PROJECT_ID=your-google-project-id
GOOGLE_CREDENTIALS_PATH=/path/to/your/service_account_credentials.json
```
*Note: You can also enter or override credentials directly within the GUI setting fields.*

---

## Local AI Translator Setup & Model Management

The **Local AI Translator** option allows you to translate English PDFs into Bangla **completely locally** on your computer without any cloud service, API key, credit card, or web scraping.

### Features:
- **Model**: Meta NLLB-200 (`facebook/nllb-200-distilled-600M`).
- **No API Key or Internet Required**: Runs 100% offline once downloaded.
- **Hardware Acceleration**: Automatically selects CUDA GPU if available and supported, otherwise seamlessly uses CPU.
- **Model Storage**: Saved in the `models/` directory inside the application folder using `pathlib`.
- **First-Run Download**: The model (~2.4 GB) is downloaded only when requested via the GUI `[ Download Model ]` button or when starting a job with the provider selected for the first time.

### Device Selection Options:
- `auto`: Uses CUDA if an NVIDIA GPU is available, otherwise CPU.
- `cpu`: Forces translation on CPU.
- `cuda`: Forces translation on CUDA GPU (falls back to CPU if unavailable or out-of-memory).

---

## Google Cloud Translation Setup

To use Google Cloud Translation as a real translation provider in the application:

1. **Create or select a Google Cloud Project** in the [Google Cloud Console](https://console.cloud.google.com/).
2. **Enable the Cloud Translation API** for your project:
   - Go to APIs & Services > Enabled APIs & Services.
   - Click **+ ENABLE APIS AND SERVICES** and search for **Cloud Translation API**.
   - Click **Enable**.
3. **Configure Authentication**:
   - Create a Service Account under **IAM & Admin > Service Accounts**.
   - Grant appropriate roles (e.g., `Cloud Translation API User`).
   - Create and download a JSON Service Account Key file to your computer.
4. **Provide Credentials to Application**:
   - In the GUI under **LANGUAGE & MODEL SETTINGS**, select `Google Cloud Translation` in **Translation Provider**.
   - Enter your **Google Project ID** (or leave empty if included in the service account JSON).
   - Click **Browse...** next to **Google Credentials** to select your downloaded Service Account JSON key file.
   - Alternatively, set `GOOGLE_CREDENTIALS_PATH` and `GOOGLE_PROJECT_ID` in your `.env` file or environment variables.
5. **Test the Connection**:
   - Click **[ Test Google Connection ]** in the GUI to verify that credentials are valid and the Cloud Translation API is accessible.
6. **Run a Small Test Translation First**:
   - Use **Test Mode (Pages)** setting (e.g., `1` or `3` pages) to test integration before running full translations.

---

## How to Launch & Use the Application

Choose **File → Book locations…** (or **Book locations…** in Translation Job)
to set the default book folder, English/reference PDF, and original-edition PDF.
The app initially discovers a single PDF in `Book` and its existing original
subfolder. Defaults are remembered; startup selects the reference PDF without
automatically analyzing or translating it. Changing defaults keeps current work
open. The original-edition path is saved for reference; automatic multilingual
alignment and original-edition refinement are not implemented yet.

On Windows, double-click **Start GUI.bat** in the project folder. It uses the
project's `venv` and keeps startup errors visible if launching fails.

Use the **Display zoom** toolbar or **View** menu to zoom from 75% to 200%.
Shortcuts: **Ctrl++** (or **Ctrl+=**) to enlarge, **Ctrl+-** to reduce, and
**Ctrl+0** to reset. The chosen percentage is remembered; the initial default is
125%. Display zoom does not change Studio PDF text sizes.

1. **Launch the GUI**:
   ```bash
   python3 main.py
   ```
2. **Select Input PDF**: Click **Browse...** to select an English PDF document.
3. **Analyze PDF**: Click **Analyze PDF**. The app scans pages, extracts layout blocks, reconstructs broken lines into paragraphs, and displays file metadata.
4. **Choose Settings**:
   - Select **Translation Provider** (`OpenAI`, `Google Cloud Translation`, or `Mock Translator`).
   - Configure model/credentials for the chosen provider.
   - Select font (`Noto Sans Bengali` or `Noto Serif Bengali`).
   - Test Mode (optional: enter `1`, `3`, or `5` pages to test a subset first).
   - Checkboxes for headings, paragraphs, page numbers, images, and OCR.
5. **Translate PDF**: Click **Translate PDF**. Real-time progress bar, page count, chunk stats, and error counter will update.
6. **Output Location**: Generated PDFs are safely saved in the `output/` folder with `_Bangla.pdf` appended to avoid modifying the original file. Click **Open Output Folder** to view generated files.

---

## Side-by-Side Preview

### Translation Studio page editor

To edit an existing translated PDF directly, choose **Translation Studio → Open
translated PDF in Studio…**. Untouched imported pages retain their original PDF
appearance in exports. The text editor contains extracted text for replacement;
editing it rebuilds that page and can lose its original layout/images. Some PDFs
have imperfect Unicode extraction, so check text carefully. Use **Page → Restore
original imported PDF page** to recover its original appearance. Imported PDFs
need manually attached source text before AI refinement; use **Page → Attach
source text for this page…**. This does not automatically align editions.

Choose **Cover / title page** for the selected page to replace it with a designed
page. Set title, author, Bangla translator, optional separate English translator,
editor (সম্পাদক), publication (প্রকাশনা),
background picture, text color, font sizes, and vertical positions. The
**অনুবাদককে প্রাধান্য দিন · Translator-first layout** preset gives the Bangla
translator a separate large name block, with smaller supporting credits below.
Translator and author font sizes and the supporting-credit position have
independent controls. Existing designs keep their layout until the preset is
selected; names, background, and opacity are retained. Apply/Cancel stay visible
below the scrollable controls. The
**Text panel opacity** control ranges from 0% (transparent) to 100% (solid
white), with 5% for new designs. Existing designs retain their earlier opacity
until changed. The text itself remains opaque. The live
preview uses the actual PDF renderer. The background and text remain separate
editable project layers; lettering already baked into an old cover image cannot
be edited independently. Use a clean background or the default neutral design.
The previous page/design is retained in revision history. Save the project to
retain layers and reopen via **Translation Studio → Open saved Studio project…**.

After translating a book (or opening its Human Review from Books), choose
**Translation Studio → Open translated-page editor**. This separate workspace
copies the current source-page translations without modifying the existing job.
Select a source page, edit Bangla text, apply bold/font size, or insert a picture
at the cursor. **Save project** stores text, embedded pictures, and page revision
history in a local `.json` file; **Open project** restores that studio work.

**Improve page with cloud AI** uses the current OpenAI/gateway or Groq settings
and may incur API charges. It sends the original page, current editable text,
adjacent page context, and optional editorial instructions. The proposed rewrite,
reasons, and ambiguities appear separately. Accept or reject explicitly. Editing
or switching pages during a request invalidates the proposal. Pages with pictures
require manually merging proposed text to preserve the design.

**Preview PDF** shows the actual export rendering. **Export new PDF** includes
current studio edits and pictures and refuses to overwrite an existing file.
Each source page starts separately. Longer content continues onto extra output
pages at readable size; PDF bookmarks and footers identify the source page and
its continuations. Studio preview lets you select every output/continuation page.
This is a flowing rich-text editor with inline images, not a free-position layout
designer. Studio changes stay in the studio project and its exports; they do not
update the original translation job. Whole-book retrieval, multilingual alignment,
and native DOCX import are not part of this editor.

For normal translation export, **Keep source pages; add overflow pages** is on
by default. It keeps source page dimensions, derives text margins and paragraph
spacing from extraction, and flows extra text onto continuation pages without
shrinking fonts. The following source page starts fresh. Uncheck it for the
older continuous-reflow export. Complex columns, tables, and exact facsimile
placement are not guaranteed by this reading-layout mode.

Switch to the **Side-by-Side Preview** tab in the GUI at any point during or after analysis/translation. Select any extracted paragraph block from the table to view the original English source text side-by-side with its Bangla translation.

---

## Translation Cache & Job Resume System

- **Caching**: Every translated paragraph is cached locally in `cache/translation_cache.db` indexed by a SHA-256 hash of `(source_text, source_lang, target_lang, model_name)`. Re-running translation on identical text instantly returns cached translations without making external API calls. Cache keys strictly distinguish between OpenAI (`gpt-4o-mini`), Google (`google-cloud-translate`), and Mock providers.
- **Job Resume**: The system records active job progress in SQLite (`job_state` table). If a job is interrupted or cancelled, re-running the application on the same file loads the previous progress map and resumes directly from the remaining untranslated blocks.

---

## Bengali Font Handling & Script Shaping

Bengali script requires complex shaping (joining consonants and placing vowel diacritics / কার signs correctly). Standard canvas rendering often misplaces vowels or breaks conjuncts. This application embeds true Unicode `Noto Sans Bengali` / `Noto Serif Bengali` OpenType TTF fonts and utilizes PyMuPDF's HTML box engine for native font shaping, producing accurate Bengali script without broken glyphs.

---

## OCR Fallback for Scanned Pages

For PDF documents containing scanned pages or images with low text density, the application detects scanned pages and routes them to `TesseractOCREngine` (`pytesseract` + `pdf2image`) to extract readable English text before paragraph reconstruction.

---

## Running Automated Tests

The page-six pilot can also be run outside the GUI. It saves translation results
as JSON so exports can be regenerated without another model/API request:

```powershell
python tools/run_local_pilot.py "path/to/book.pdf" --pages 6 --int8 --output output/page6_local
python tools/run_cloud_pilot.py output/page6_local/pilot.json output/page6_cloud
python tools/export_pilot_docx.py output/page6_local/pilot.json
python tools/export_pilot_docx.py output/page6_cloud/pilot.json
python tools/export_pilot_pdf.py output/page6_local/pilot.json serif
python tools/export_pilot_pdf.py output/page6_cloud/pilot.json serif
```

Cloud translation uses the locally configured key, API base URL, and model and
may incur provider charges. The `--int8` option is an experimental CPU memory
optimization for the pilot, not the default GUI local-model path. Both exports
are Bangla only. Word export and model-powered revision are not yet GUI actions.
See `PROJECT_STATUS.md` for verification results and known output limitations.

An opt-in GUI workflow test uses the real Qt controls, translation worker,
configured gateway, and PDF builder on physical page 6:

```powershell
python tools/test_gui_workflow.py
```

It substitutes the native file picker and uses isolated databases under
`tmp/gui_e2e/` to protect existing jobs and book records. Its first run may incur
gateway charges; subsequent runs reuse its saved translations. It checks preview
updates, edit save/restore, page selection, and source/output preservation, and
writes a report and GUI snapshots. It does not certify whole-book accuracy or
replace testing native dialogs and desktop interactions.

Run the unit test suite to verify extraction, paragraph parsing, layout analysis, font loading, Google & OpenAI translation providers, caching, job state saving, and PDF creation:
```bash
python3 -m unittest discover tests
```

---

## Troubleshooting & FAQs

- **Q: Bengali characters appear broken or blank in third-party viewers.**
  - **A**: Ensure `assets/fonts/NotoSansBengali-Regular.ttf` is present. The application embeds the font inside the generated PDF for universal viewing across PDF readers.
- **Q: Translation fails due to Google API authentication errors.**
  - **A**: Verify your Google Project ID and Service Account JSON key path. Click **Test Google Connection** in the GUI to diagnose authentication issues.
- **Q: Translation fails due to OpenAI API key errors.**
  - **A**: Verify your key in `.env` or in the GUI field. You can test full application flow offline without an API key by selecting `Mock Translator` in the Translation Provider dropdown.
- **Q: Application shows GUI display warning on headless Linux server.**
  - **A**: If running on a headless Linux environment without an X server, set `QT_QPA_PLATFORM=offscreen python3 main.py`.
