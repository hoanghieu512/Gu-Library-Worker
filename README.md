# gu-library-worker

Atomman worker for Gú's Library: polls `kho/_inbox/`, converts originals to PDF,
extracts a schema-v1 sidecar JSON, and files the pair into the subject folder.

See `Docs/superpowers/plans/2026-06-21-gu-library-m7-worker.md` and
`Docs/gu-library-sidecar-schema.md`.

## Running on the Atomman

One pass manually (LibreOffice is auto-detected — no `--soffice` needed):

    .venv\Scripts\python -m gu_library_worker --kho "D:\path\to\kho"

Watch multiple kho in one process — repeat `--kho`. They are scanned
**sequentially** (one process, never two LibreOffice conversions at once), and
one kho's failure is isolated from the rest:

    .venv\Scripts\python -m gu_library_worker --kho "D:\GuLibrary\kho" --kho "D:\GuLibrary-Prod\kho"

LibreOffice resolution order: `GULIB_SOFFICE` env var → standard install dirs
(`C:\Program Files\LibreOffice\program\soffice.exe` and the `(x86)` variant) →
`PATH`. If it's installed somewhere non-standard, point the worker at it:

    set GULIB_SOFFICE=D:\Apps\LibreOffice\program\soffice.exe

(or pass `--soffice "<path>"`). If LibreOffice can't be found, the worker fails
with a clear message telling you to install it or set `GULIB_SOFFICE`.

Register the Scheduled Task (every 3 minutes, restarts after reboot):

    powershell -ExecutionPolicy Bypass -File scripts\register-task.ps1 -KhoRoot "D:\path\to\kho"

For multiple kho, pass a comma-separated list:

    powershell -ExecutionPolicy Bypass -File scripts\register-task.ps1 -KhoRoot "D:\GuLibrary\kho","D:\GuLibrary-Prod\kho"

The worker is stateless: each run scans `_inbox/` once and exits. Files it can't
handle (wrong extension, still being written, broken) are left in place on
purpose — the app shows ⏳ as the signal to clean up by hand.

## Diagnostics: `_worker.log`

Each pass appends to `<kho>/_worker.log` (in addition to stdout) — the run time,
the `ScanReport` (processed/skipped/failed), and the reason each file was skipped
or failed (with tracebacks). This is how you debug a stuck file when the Scheduled
Task runs in the background and swallows stdout. The file rotates (≈1 MB × 3
backups) so it can't grow unbounded, and its leading underscore keeps the app
from treating it as data.

Each kho gets its OWN `<kho>/_worker.log`, and every line is tagged with the kho
label (its parent folder, e.g. `[GuLibrary-Prod]`) — so Prod and test stay cleanly
separated even though one process serves both.

It lives at the kho root, so Syncthing will replicate it. To keep it local to the
Atomman, add a `.stignore` at the kho root containing:

    _worker.log
    _worker.log.*

## Heavy scan normalization

A **scanned/image PDF** (no text layer) whose page rasters are too heavy for a
phone viewer (effective resolution > ~200 dpi and/or JPEG2000 encoding) is
republished into the kho as a lighter **150 dpi JPEG** version — same page count
and page size, visually indistinguishable when read, but far cheaper to decode
(so the app doesn't OOM/crash opening it). Grayscale pages become grayscale;
pages with real colour (a stamp) stay RGB. **PDFs with a text layer are never
re-rastered**, and already-light scans pass through untouched.

The untouched original is moved to a local archive next to the kho —
`<kho>_archive/` (a sibling of the kho, so it is NOT inside the Syncthing folder
and never syncs). The archive path is logged.

Timing note: normalization is ~0.8 s/page, so a large scan can make one pass take
a couple of minutes. Since kho are scanned sequentially in one process, this can
delay the other kho's scan by up to that one pass — it self-heals on the next
3-minute run. This is intentional (no parallel LibreOffice); the loop
architecture is unchanged.

## Rebuilding slide structure: `reslide` (manual, one-off)

A legacy `.ppt` can't be read by python-pptx, so the pipeline converts it and
extracts from the PDF — which used to land in the kho as unlabelled `paragraph`
blocks. Since v0.14.0 new `.ppt` files get slide structure straight away; this
tool repairs the ones already in the kho.

    python -m gu_library_worker.reslide --kho "D:\GuLibrary\kho" --kho "D:\GuLibrary-Prod\kho"
    python -m gu_library_worker.reslide --kho "D:\GuLibrary\kho" --apply

It **reports only unless `--apply` is given**. Repair merges the units the
sidecar already has, grouped by `page`, into one `slide` unit per page labelled
`Slide N`. `page` is copied verbatim and **the PDF in the kho is never touched
or re-converted**, so the page anchors the app jumps to stay exactly as accurate
as they were. A sidecar that fails any safety check (a page beyond `pageCount`,
an invalid result) is **left degraded rather than rewritten** — a page jump that
lands correctly beats structure that lands on the wrong page.

The previous sidecar is copied to `<kho>_archive/_sidecar_backup/<relative path>`
before anything is overwritten, and the new one is written atomically so
Syncthing never picks up a half-written file. Re-running is a no-op.

Overwriting a sidecar makes every Android device re-index that file — by design,
but worth doing in batches if you ever have hundreds to repair.

## Text search can't match: normalized on the way in, `vnifix` for the backlog

Two things make sidecar text unmatchable while leaving it looking perfectly
normal on screen:

- **Legacy VNI-Times encoding.** Material written before Unicode stored
  Vietnamese as ASCII letters in a VNI-Times font: the bytes say
  `CHÖÔNG XV — MIEÃN, GIAÛM`, and only the font made them look right. LibreOffice
  substitutes a normal font, so those bytes land in the sidecar and nobody
  searching for `miễn giảm` can ever match them.
- **Decomposed tone marks.** `i` followed by a combining acute instead of `í`.
  Identical on screen, equal to no query anyone will type.

Since v0.16.0 the pipeline fixes both **for every source format** on the way in —
after each reader and after page anchoring — so newly added documents need no
repair. (v0.15.0 hooked it into the `.doc`/`.ppt` branch only, which missed the
PDF, docx and pptx files that turned out to be most of them.) This tool is the
retrofit for what is already in the kho.

    python -m gu_library_worker.vnifix --kho "D:\GuLibrary-Prod\kho"
    python -m gu_library_worker.vnifix --kho "D:\GuLibrary-Prod\kho" --apply

It **reports only unless `--apply` is given**. Only `text` changes — `page`,
`bbox`, `label`, `path` and the document metadata are carried across untouched,
so page anchors cannot move. A conversion that would empty a unit, change a
unit's word count, move a page, or produce an invalid sidecar is refused and the
document left alone. The previous sidecar is copied to
`<kho>_archive/_sidecar_backup_vni/` — deliberately *not* `_sidecar_backup/`,
which holds `reslide`'s pre-slide originals. Re-running is a no-op.

**Deciding what is VNI is the hard part, and two obvious rules are both wrong.**
A vowel followed by a tone mark (`aù`) looks like proof, but Vietnamese Unicode
writes `hoà`, `toà`, `hoá`, `Hoàng` exactly that way — the tone landing on the
second vowel of a cluster — so that rule turns `Toà án` into `Tồ án`. The
characters `ö ä ü ñ` look exclusive to VNI, but they are everyday German, Nordic
and Spanish letters, and a kho holding foreign citations turns `öffentliches`
into `ưffentliches`. Proof is the two together: **a VNI-exclusive modifier
immediately after a vowel**, which nothing else produces. Text that only *might*
be VNI is left as it is, so a few real VNI words with no exclusive character of
their own (`Phaàn`) survive unconverted — the price of never mangling a `Toà`.

## Prod ops: Drive print queue + weekly backup (rclone)

Two Scheduled Tasks, **Prod only**, independent of `GuLibraryWorker`:

- **GuLibraryPrintSync** — every 15 min, mirrors `<kho>/_print/` up to Google Drive
  `GuLibrary/Di-in`. `rclone sync` is a mirror: ticking "Xong" (file leaves
  `_print/`) removes it from Drive next run, so the Drive folder always equals the
  current print queue.
- **GuLibraryBackup** — weekly, makes a dated snapshot `<kho-parent>\backup\YYYY-MM-DD\`
  (a sibling of the kho, **outside the Syncthing tree**), keeps the newest 4, then
  mirrors `backup\` to Drive `GuLibrary/Backup`. `.stversions` is excluded from the
  snapshot.

Each task logs to `<kho-parent>\_print-sync.log` / `_backup.log` (outside the kho).
On a network/Drive error they log and exit; the next scheduled run retries (no
in-place retry loop, no popup). Tasks run **whether logged on or not** (S4U), so
they survive a reboot with no logon and run headless (no window).

### One-time manual setup (Gú, on the Atomman)

1. **Install rclone** (https://rclone.org/downloads/) and put `rclone.exe` on PATH.
2. **Configure the Google Drive remote** (opens a browser once for OAuth):

       rclone config
       # n) new remote  -> name it e.g. "gdrive"  -> storage: "drive"
       # accept defaults, authorize in the browser, confirm

3. **Test by hand before trusting the tasks:**

       rclone lsd gdrive:                                   # lists Drive, proves auth
       rclone sync "D:\GuLibrary-Prod\kho\_print" gdrive:GuLibrary/Di-in
       powershell -File scripts\backup.ps1 -KhoRoot "D:\GuLibrary-Prod\kho" -SkipDrive   # snapshot only

4. **Register both tasks (ADMINISTRATOR PowerShell):**

       powershell -File scripts\register-ops-tasks.ps1 -KhoRoot "D:\GuLibrary-Prod\kho" -RcloneRemote "gdrive"

   Verify: `Get-ScheduledTask GuLibraryPrintSync,GuLibraryBackup`.

Notes: the S4U task loads your profile, so it uses your `%APPDATA%\rclone\rclone.conf`.
If the task can't find the config, pass an explicit path to both the register
script and it forwards it: `-RcloneConfig "C:\path\to\rclone.conf"`. Re-run
`register-task.ps1` too (it now registers `GuLibraryWorker` as S4U for the same
reboot-without-logon behavior).

### Chat alerts (Zalo Bot or Telegram)

Both tasks report to a chat bot via `scripts\notify.ps1`, so a dead sync doesn't sit
unnoticed in a log:

| Task | Message |
|---|---|
| print-sync | `FAILING` after failing continuously for 2 h (`-AlertAfterMinutes`), a reminder every 24 h while still failing, then `RECOVERED` |
| backup | `OK` after every weekly run (a heartbeat: **no Sunday message = go look**), `FAILING` on the first failure, then `RECOVERED` |

Alert state lives next to each log (`_print-sync.state.json`, `_backup.state.json`).
A failed alert is logged as `WARN notify failed` and never changes the task result.

Setup (as the same Windows user the tasks run as; the token never goes in the repo):

1. Create a bot — **Zalo:** in the Zalo app open the OA "Zalo Bot Manager" → create
   bot (name must start with "Bot") → the token arrives by message. **Telegram:**
   `@BotFather` → `/newbot`.
2. `powershell -File scripts\notify-setup.ps1` → creates `%APPDATA%\GuLibrary\notify.json`.
   Put in `"provider": "zalo"` (or `"telegram"`) and the `"token"`.
3. Run `notify-setup.ps1` again and, **while it says "Waiting for a message"**, send
   any message to the bot from your phone (Zalo's `getUpdates` long poll may only
   deliver messages that arrive while it waits): it finds your `chat_id`, saves it,
   and sends a test message. Re-test any time with
   `notify-setup.ps1 -Test`.

No `notify.json` = alerts off, tasks behave as before. Switching Zalo ↔ Telegram is a
config change only (both use the same `/bot<token>/sendMessage` API shape).
