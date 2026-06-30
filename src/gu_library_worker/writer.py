# src/gu_library_worker/writer.py
from __future__ import annotations
import json
import shutil
import time
from pathlib import Path

def _unlink_with_retry(path: Path, *, tries: int = 25, delay: float = 0.2,
                       sleep=time.sleep) -> bool:
    """Delete `path`, retrying briefly on a transient lock. Returns True if the
    file is gone (or never existed), False if still locked after all tries.

    On Windows a just-closed mmap (PyMuPDF) or an antivirus/Syncthing scan can
    hold the file open for a moment, so an immediate unlink may raise WinError 32.
    """
    for attempt in range(tries):
        try:
            path.unlink()
            return True
        except FileNotFoundError:
            return True
        except OSError:
            if attempt == tries - 1:
                return False
            sleep(delay)
    return False

def write_pair(canonical_pdf: Path, sidecar: dict,
               pdf_dst: Path, json_dst: Path, original: Path) -> None:
    """Place the PDF+JSON pair, then delete the original.

    Outputs are written and confirmed before the original is removed, so a
    failure never loses data (the original stays, app keeps showing ⏳). If the
    original can't be removed even after retries, the just-written pair is rolled
    back so the next pass reprocesses cleanly instead of leaving a duplicate."""
    pdf_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(canonical_pdf, pdf_dst)
    try:
        json_dst.write_text(
            json.dumps(sidecar, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pdf_dst.unlink(missing_ok=True)  # roll back partial pair
        raise
    if not (pdf_dst.exists() and json_dst.exists()):
        pdf_dst.unlink(missing_ok=True)  # clean up orphan, leave no half-pair
        raise RuntimeError("pair not fully written; original preserved")
    if not _unlink_with_retry(original):
        # original still locked: undo the pair so we don't duplicate next pass
        pdf_dst.unlink(missing_ok=True)
        json_dst.unlink(missing_ok=True)
        raise RuntimeError(f"could not remove original (locked); rolled back pair: {original}")
