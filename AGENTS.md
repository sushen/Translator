# Project continuity

Read `README.md` and `PROJECT_STATUS.md` before making changes. The README
describes setup and the original product; the status file records current
development context. Confirm behavior in source rather than treating either
document as proof that a feature works.

## Working rules

- This is a Python/PySide6 English-to-Bangla PDF and book translation workbench.
- Preserve original input PDFs and existing user work, including review edits,
  translation caches, job state, book databases, downloaded models, and outputs.
- Never record API keys, credentials, or private document text in documentation.
- Follow existing module boundaries and use mock providers for verification when
  practical. Do not trigger paid translation or large model downloads just to test.
- Run checks appropriate to the change and report actual results. Distinguish
  source inspection, automated tests, and manual GUI/end-to-end verification.

## Keep the handoff current

After meaningful development work, update `PROJECT_STATUS.md` with what changed,
validation performed, unresolved issues, and the next concrete step. Add a dated
entry to its development log. Keep the current snapshot concise; do not invent
completed work, test results, priorities, or user decisions.

Before resuming, inspect the working tree so existing changes are preserved.
Read the current snapshot and latest log entry, then verify relevant code.
