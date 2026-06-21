# src/gu_library_worker/writer.py
from __future__ import annotations
import json
import shutil
from pathlib import Path

def write_pair(canonical_pdf: Path, sidecar: dict,
               pdf_dst: Path, json_dst: Path, original: Path) -> None:
    """Place the PDF+JSON pair, then delete the original.

    Outputs are written and confirmed before the original is removed, so a
    failure never loses data (the original stays, app keeps showing ⏳)."""
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
        raise RuntimeError("pair not fully written; original preserved")
    original.unlink(missing_ok=True)
