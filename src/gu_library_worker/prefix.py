from __future__ import annotations
import re
from dataclasses import dataclass
from .config import UNCLASSIFIED

_PREFIX_RE = re.compile(r"^\[(?P<subject>[^\]]+)\]\s*(?P<rest>.+)$")

@dataclass(frozen=True)
class Parsed:
    subject: str
    clean_name: str
    source: str  # "share" | "watch"

def parse_prefix(filename: str) -> Parsed:
    m = _PREFIX_RE.match(filename)
    if m:
        return Parsed(
            subject=m.group("subject").strip(),
            clean_name=m.group("rest").strip(),
            source="share",
        )
    return Parsed(subject=UNCLASSIFIED, clean_name=filename, source="watch")
