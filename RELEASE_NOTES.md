# Book Translator v-0.0.2

This source release adds Translation Studio and improves the English-to-Bangla
PDF review and book preparation workflow.

## Changes

- Separate Studio with rich-text editing, embedded pictures, portable projects,
  revision history, PDF preview, and export to a new file.
- Open translated PDFs directly; preserve untouched imported pages and restore
  original pages when needed.
- Cover/title-page designer with editable credits, background, translator-first
  layout, opacity controls, and live preview.
- Source-page-aware PDF flow with readable continuation pages and bookmarks.
- Configurable book locations, remembered interface zoom, compact scrollable
  controls, and a Windows launcher.
- OpenAI-compatible gateway settings and verified Windows TLS; lazy local-model
  loading, stronger translation validation, and safer selected-page review saves.
- Pilot scripts for local/cloud comparisons and editable DOCX exports.

## Install

Use the source ZIP or clone the repository at `v-0.0.2`. Install Python 3.10+
(3.12 recommended), create `venv`, and install `requirements.txt`. Copy
`.env.example` to `.env` and configure your provider locally. Launch with
`python main.py` or `Start GUI.bat` on Windows. See README for full setup.

This release does not include a standalone executable, downloaded AI models,
credentials, books, translation databases, or generated user outputs. Existing
local work must be retained when upgrading. Cloud actions may incur provider
charges; use the mock provider for an offline workflow check.

## Known limitations

Release checks: 17 isolated tests passed across offscreen Studio/cover/pagination,
gateway configuration, lazy provider loading and worker failures;
syntax compilation passed for all 88 Python files, and the staged whitespace
check passed. Full unittest discovery was interrupted during prolonged dependency
loading; a timed diagnostic found OpenAI SDK import file reads. `python-docx`
is absent from the release-check environment, so DOCX tests were not rerun.
No live paid translation, model download, or manual desktop verification was
performed for this release. See PROJECT_STATUS.md for prior validation.

Complex columns/tables and exact source layout are not guaranteed. Editing text
in an imported PDF rebuilds that page and can lose its layout/images. Bangla PDF
copy/search correctness and Word visual layout remain unverified. Studio edits
stay separate from translation jobs; whole-book retrieval and multilingual
alignment are not implemented. OCR, full-book quality, and the complete native
desktop publishing workflow have not been verified for this release.
