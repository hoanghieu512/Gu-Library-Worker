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
