# gu-library-worker

Mini-PC worker for Gú's Library: polls `kho/_inbox/`, converts originals to PDF,
extracts a schema-v1 sidecar JSON, and files the pair into the subject folder.

See `Docs/superpowers/plans/2026-06-21-gu-library-m7-worker.md` and
`Docs/gu-library-sidecar-schema.md`.

## Running on the mini PC

One pass manually (LibreOffice is auto-detected — no `--soffice` needed):

    .venv\Scripts\python -m gu_library_worker --kho "D:\path\to\kho"

LibreOffice resolution order: `GULIB_SOFFICE` env var → standard install dirs
(`C:\Program Files\LibreOffice\program\soffice.exe` and the `(x86)` variant) →
`PATH`. If it's installed somewhere non-standard, point the worker at it:

    set GULIB_SOFFICE=D:\Apps\LibreOffice\program\soffice.exe

(or pass `--soffice "<path>"`). If LibreOffice can't be found, the worker fails
with a clear message telling you to install it or set `GULIB_SOFFICE`.

Register the Scheduled Task (every 3 minutes, restarts after reboot):

    powershell -ExecutionPolicy Bypass -File scripts\register-task.ps1 -KhoRoot "D:\path\to\kho"

The worker is stateless: each run scans `_inbox/` once and exits. Files it can't
handle (wrong extension, still being written, broken) are left in place on
purpose — the app shows ⏳ as the signal to clean up by hand.
