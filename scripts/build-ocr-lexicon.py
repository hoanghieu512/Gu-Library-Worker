"""Rebuild src/gu_library_worker/data/ocr_lexicon.txt (the OCR garbage gate's word list).

The OCR stage keeps the "image page" placeholder for a page whose recognised
text has too many tokens outside this list (see `ocr.page_verdict`). The list
is a FIXED file shipped with the worker, so a re-run gives the same verdicts;
rebuild it only on purpose (it changes which pages pass the gate).

Source: the text units of existing sidecars (placeholders and OCR units are
skipped). A token is a run of letters, lowercased, NFC. Kept when it is 1-7
letters long (a Vietnamese syllable is at most 7), appears >= 3 times in total
and in >= 2 different documents — which drops one-off names, e-mail fragments
and run-together words. Read-only on the kho.

usage: python scripts/build-ocr-lexicon.py KHO_ROOT [KHO_ROOT ...]
"""
from __future__ import annotations
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

MARKER = "[trang ảnh scan"
TOKEN_RE = re.compile(r"[^\W\d_]+")
MAX_LEN, MIN_COUNT, MIN_DOCS = 7, 3, 2
OUT = Path(__file__).resolve().parents[1] / "src" / "gu_library_worker" / "data" / "ocr_lexicon.txt"

def sidecars(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        rel = Path(dirpath).relative_to(root)
        if rel.parts and rel.parts[0][:1] in ("_", "."):
            dirnames[:] = []
            continue
        for name in filenames:
            if name.endswith(".json") and not name.startswith("_"):
                yield Path(dirpath) / name

def main(roots: list[str]) -> None:
    count: dict[str, int] = {}
    docs: dict[str, int] = {}
    for root in roots:
        for path in sidecars(Path(root)):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(data, dict):
                continue
            seen: set[str] = set()
            for unit in data.get("units") or []:
                text = unit.get("text", "")
                if unit.get("ocr") or text.startswith(MARKER):
                    continue
                for tok in TOKEN_RE.findall(unicodedata.normalize("NFC", text)):
                    tok = tok.lower()
                    if len(tok) <= MAX_LEN:
                        count[tok] = count.get(tok, 0) + 1
                        seen.add(tok)
            for tok in seen:
                docs[tok] = docs.get(tok, 0) + 1
    words = sorted(t for t, c in count.items() if c >= MIN_COUNT and docs.get(t, 0) >= MIN_DOCS)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(words) + "\n", encoding="utf-8", newline="\n")
    print(f"{len(words)} tokens -> {OUT}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1:])
