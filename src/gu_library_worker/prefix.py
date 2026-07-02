from __future__ import annotations
import logging
import re
from dataclasses import dataclass
from .config import UNCLASSIFIED

log = logging.getLogger("gu_library_worker")

# One or more leading [..] groups, then the rest (the real filename).
_LEADING_RE = re.compile(r"^((?:\[[^\]]*\]\s*)+)(.+)$")
_BRACKET_RE = re.compile(r"\[([^\]]*)\]")

# `subject` carries the nested path as "/"-joined segments (a single segment for
# the common one-bracket case). Paths.subject_dir splits it back into folders.
_SEP = "/"

@dataclass(frozen=True)
class Parsed:
    subject: str
    clean_name: str
    source: str  # "share" | "watch"

def _valid_segment(s: str) -> bool:
    # Block path traversal / separators / empty / the app's reserved `_` prefix.
    return bool(s) and s not in (".", "..") and "/" not in s and "\\" not in s \
        and not s.startswith("_")

def parse_prefix(filename: str) -> Parsed:
    """Parse the destination prefix.

    - No leading bracket  -> unclassified, source 'watch' (manual drop).
    - `[Môn] x`           -> subject 'Môn' (unchanged one-level behavior).
    - `[Môn][Bài giảng] x`-> subject 'Môn/Bài giảng' (nested, any depth).
    Abnormal input is routed safely to the unclassified area and logged, never
    escaping the kho: a bad segment (`..`, `/`, `\\`, empty, leading `_`), or a
    nested path under `Chưa phân loại` (which stays flat).
    """
    m = _LEADING_RE.match(filename)
    if not m:
        return Parsed(subject=UNCLASSIFIED, clean_name=filename, source="watch")

    prefix_blob, rest = m.group(1), m.group(2).strip()
    segments = [s.strip() for s in _BRACKET_RE.findall(prefix_blob)]

    bad = [s for s in segments if not _valid_segment(s)]
    if bad:
        log.warning("unsafe subject prefix in %r (bad segment(s) %r) -> %s",
                    filename, bad, UNCLASSIFIED)
        return Parsed(subject=UNCLASSIFIED, clean_name=rest, source="share")

    if segments[0] == UNCLASSIFIED and len(segments) > 1:
        log.warning("nested prefix under '%s' in %r ignored -> flat unclassified",
                    UNCLASSIFIED, filename)
        return Parsed(subject=UNCLASSIFIED, clean_name=rest, source="share")

    return Parsed(subject=_SEP.join(segments), clean_name=rest, source="share")
