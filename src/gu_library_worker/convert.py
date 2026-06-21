# src/gu_library_worker/convert.py
from __future__ import annotations
import subprocess
from pathlib import Path

DEFAULT_SOFFICE = "soffice"  # on PATH; override via CLI/env on the mini PC

class ConversionError(RuntimeError):
    pass

def build_command(src: Path, outdir: Path, soffice: str = DEFAULT_SOFFICE) -> list[str]:
    return [
        soffice, "--headless", "--norestore",
        "--convert-to", "pdf",
        "--outdir", str(outdir),
        str(src),
    ]

def to_pdf(src: Path, outdir: Path, soffice: str = DEFAULT_SOFFICE,
           timeout: float = 180.0) -> Path:
    """Convert `src` to a PDF in `outdir`. Returns the output path or raises."""
    cmd = build_command(src, outdir, soffice)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ConversionError(f"LibreOffice failed to run: {exc}") from exc
    if result.returncode != 0:
        raise ConversionError(f"LibreOffice exit {result.returncode}: {result.stderr}")
    out = outdir / (src.stem + ".pdf")
    if not out.exists() or out.stat().st_size == 0:
        raise ConversionError(f"expected PDF not produced: {out}")
    return out
