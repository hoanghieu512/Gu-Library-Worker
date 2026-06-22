# src/gu_library_worker/convert.py
from __future__ import annotations
import os
import shutil
import subprocess
from pathlib import Path

# Standard Windows install locations — checked directly so the worker does NOT
# depend on PATH (soffice.exe is almost never on PATH, and a Scheduled Task
# running in the background often has no user-level PATH at all).
_WINDOWS_SOFFICE_PATHS = (
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
)
# Last-resort PATH lookup names (Linux/Mac dev, or Windows with PATH set).
_SOFFICE_NAMES = ("soffice", "soffice.exe", "soffice.com")

class ConversionError(RuntimeError):
    pass

def resolve_soffice() -> str:
    """Locate the LibreOffice binary without relying on PATH.

    Priority: GULIB_SOFFICE env var > standard Windows install dirs > PATH.
    Raises ConversionError with an actionable message if none is found
    (instead of letting a bare ``[WinError 2]`` surface later).
    """
    candidates: list[str] = []
    env = os.environ.get("GULIB_SOFFICE")
    if env:
        candidates.append(env)               # explicit override wins
    candidates.extend(_WINDOWS_SOFFICE_PATHS)
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    for name in _SOFFICE_NAMES:              # cross-platform fallback
        found = shutil.which(name)
        if found:
            return found
    raise ConversionError(
        "LibreOffice not found. Install LibreOffice or set GULIB_SOFFICE to the "
        "full path of soffice.exe/soffice.com. "
        f"Tried: GULIB_SOFFICE={env or '(unset)'}, "
        f"{', '.join(_WINDOWS_SOFFICE_PATHS)}, and PATH ({', '.join(_SOFFICE_NAMES)})."
    )

def build_command(src: Path, outdir: Path, soffice: str) -> list[str]:
    return [
        soffice, "--headless", "--norestore",
        "--convert-to", "pdf",
        "--outdir", str(outdir),
        str(src),
    ]

def to_pdf(src: Path, outdir: Path, soffice: str | None = None,
           timeout: float = 180.0) -> Path:
    """Convert `src` to a PDF in `outdir`. Returns the output path or raises.

    When `soffice` is omitted, the binary is resolved via `resolve_soffice()`
    (GULIB_SOFFICE > standard install dirs > PATH).
    """
    exe = soffice if soffice else resolve_soffice()
    cmd = build_command(src, outdir, exe)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ConversionError(f"LibreOffice failed to run ({exe}): {exc}") from exc
    if result.returncode != 0:
        raise ConversionError(f"LibreOffice exit {result.returncode}: {result.stderr}")
    out = outdir / (src.stem + ".pdf")
    if not out.exists() or out.stat().st_size == 0:
        raise ConversionError(f"expected PDF not produced: {out}")
    return out
