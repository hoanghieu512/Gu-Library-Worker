from __future__ import annotations
import os
import time
from pathlib import Path
from typing import Callable
from .config import ACCEPTED_EXTENSIONS, TEMP_SUFFIXES, SYNCTHING_TOKEN, STABILITY_INTERVAL_SECONDS

def is_candidate_name(name: str) -> bool:
    """Pure filename gate. No filesystem access."""
    if name.startswith("."):
        return False
    lower = name.lower()
    if SYNCTHING_TOKEN in lower:
        return False
    for suffix in TEMP_SUFFIXES:
        if lower.endswith(suffix):
            return False
    return Path(lower).suffix in ACCEPTED_EXTENSIONS

def normalize_tmp_name(name: str) -> str | None:
    """Clean a Samsung/SAF artifact name, else return None.

    Android SAF sometimes writes a real on-disk file as ``<name>.<ext>.tmp`` while
    reporting the clean name to the app — so the worker (which sees the true
    filesystem via Syncthing) is the only place to fix it. If `name` is a valid
    document extension buried under one or more trailing ``.tmp`` layers
    (``X.pdf.tmp``, even ``X.pdf.tmp.tmp``), return the cleaned name (``X.pdf``).

    Returns None when it is NOT this artifact: Syncthing in-progress files
    (``.syncthing.*.tmp``), hidden/system files, or a ``.tmp`` whose preceding
    extension is not a document type (``random.tmp``, ``notes.txt.tmp``) — those
    are left untouched (the caller skips them as before).
    """
    if name.startswith(".") or SYNCTHING_TOKEN in name.lower():
        return None
    base = name
    stripped = False
    while base.lower().endswith(".tmp"):
        base = base[:-len(".tmp")]   # peel one .tmp layer (handles multi-layer)
        stripped = True
    if not stripped:
        return None
    if Path(base).suffix.lower() in ACCEPTED_EXTENSIONS:
        return base
    return None

def wait_until_stable(
    path: Path,
    *,
    interval: float = STABILITY_INTERVAL_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
    _stat_size: Callable[[Path], int] = lambda p: os.path.getsize(p),
) -> bool:
    """True if the file size is identical across two reads `interval` apart."""
    try:
        first = _stat_size(path)
        sleep(interval)
        second = _stat_size(path)
    except OSError:
        return False
    return first == second
