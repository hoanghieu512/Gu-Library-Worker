# src/gu_library_worker/naming.py
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path

@dataclass
class Reservations:
    """Names claimed earlier in the SAME scan pass (not yet on disk)."""
    taken: set[tuple[str, str]] = field(default_factory=set)  # (subject_path, stem)

def _is_free(subject: Path, stem: str, res: Reservations) -> bool:
    if (str(subject), stem) in res.taken:
        return False
    if (subject / f"{stem}.pdf").exists():
        return False
    if (subject / f"{stem}.json").exists():
        return False
    return True

def resolve_target_stems(subject: Path, clean_name: str,
                         res: Reservations) -> tuple[Path, Path]:
    """Return (pdf_path, json_path) for `clean_name`, suffixing ` (n)` on
    collision with disk or same-scan reservations. Reserves the chosen stem."""
    base = Path(clean_name).stem
    stem = base
    n = 0
    while not _is_free(subject, stem, res):
        n += 1
        stem = f"{base} ({n})"
    res.taken.add((str(subject), stem))
    return subject / f"{stem}.pdf", subject / f"{stem}.json"
