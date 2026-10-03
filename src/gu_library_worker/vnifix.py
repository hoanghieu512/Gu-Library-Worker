# src/gu_library_worker/vnifix.py
"""Normalize sidecar text that search cannot match, in a kho already built.

Search reads `units[].text`, and two things make text unmatchable while leaving
it looking perfectly fine: legacy VNI-Times encoding (`MIEÃN, GIAÛM` — invisible
to anyone typing `miễn giảm`) and tone marks left as separate combining
characters (`i` + ́ instead of `í`, which no query will ever equal). The
structure can be flawless and the document still unfindable.

This is the retrofit for documents already in the kho; `pipeline` applies the
same `vni.normalize_text` to everything arriving from now on, so the two stay in
step and a re-run after an intake finds nothing to do.

Only `text` changes. `page`, `label`, `bbox`, `path` and the document metadata
are carried across untouched, so the page anchors the app jumps to cannot move.
A conversion that would drop or split a word, empty a unit, or produce an
invalid sidecar is refused and the document left exactly as it was.

Units marked `"ocr": true` are never touched: recognised text is Unicode by
construction, and stray Latin-1 letters in OCR noise (`haï`, `LEøÄ`) would
otherwise be "decoded" as VNI into different noise. The OCR stage owns those
units (`ocr.clean_text`).
"""
from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from .logsetup import kho_logging
from .reslide import _document_sidecars, _write_atomic
from .schema import validate_sidecar
from .vni import has_vni_evidence, looks_vni, normalize_text

log = logging.getLogger("gu_library_worker")

# Kept apart from reslide's `_sidecar_backup/`, which holds the pre-slide
# sidecars — those must survive this pass untouched.
BACKUP_DIRNAME = "_sidecar_backup_vni"


def _is_ocr(unit: dict) -> bool:
    return unit.get("ocr") is True


@dataclass
class VniFixReport:
    targets: int = 0          # sidecars whose text normalizing would change
    rewritten: int = 0        # converted to Unicode
    skipped_unsafe: int = 0   # a target whose conversion failed a safety check
    units_changed: int = 0
    units_still_vni: int = 0  # units where a VNI character survived: text the
                              # PDF extractor had already torn apart, or a
                              # foreign word that happens to share the letter


def needs_text_fix(data: dict) -> bool:
    """True when normalizing would actually change this document's text.

    The gate is the outcome, not a guess: a document is a target exactly when
    `vni.normalize_text` has something to do to it — decode VNI, compose a
    separated tone mark, or both. VNI decoding is deliberately narrow on its own
    (see `vni.has_vni_evidence`), so this never widens what gets rewritten, it
    only stops a document that needs *only* NFC from being overlooked.
    """
    return any(normalize_text(u.get("text") or "") != (u.get("text") or "")
               for u in (data.get("units") or []) if not _is_ocr(u))


def needs_vni_fix(data: dict) -> bool:
    """True when any unit holds a sequence only VNI encoding produces."""
    return any(has_vni_evidence(u.get("text") or "")
               for u in (data.get("units") or []) if not _is_ocr(u))


def convert_sidecar(data: dict) -> tuple[dict, int] | None:
    """Return (converted copy, units changed), or None if it isn't safe.

    The invariants checked are the ones a transliteration must never break:
    the same units in the same order on the same pages, no unit emptied, and
    the same number of words in each — conversion rewrites letters inside
    words, it never joins or splits them.
    """
    units = data.get("units") or []
    if not units:
        return None

    new_units: list[dict] = []
    changed = 0
    for u in units:
        if _is_ocr(u):
            new_units.append(dict(u))                # OCR text is not ours to re-encode
            continue
        old_text = u.get("text") or ""
        new_text = normalize_text(old_text)
        if not new_text.strip():
            return None                              # never empty a unit
        if len(new_text.split()) != len(old_text.split()):
            return None                              # words must not move
        if new_text != old_text:
            changed += 1
        new_unit = dict(u)
        new_unit["text"] = new_text
        new_units.append(new_unit)

    out = dict(data)
    out["units"] = new_units
    if [u["page"] for u in new_units] != [u.get("page") for u in units]:
        return None                                  # anchors must not move
    if validate_sidecar(out):
        return None
    return out, changed


def vnifix_kho(kho_root, *, apply: bool = False) -> VniFixReport:
    """Re-encode every VNI-carrying sidecar in one kho.

    With `apply=False` (the default) nothing is written. With `apply=True` the
    current sidecar is copied into `<kho>_archive/_sidecar_backup_vni/` first.
    """
    kho_root = Path(kho_root)
    backup_root = kho_root.with_name(kho_root.name + "_archive") / BACKUP_DIRNAME
    report = VniFixReport()

    for path in _document_sidecars(kho_root):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            log.warning("unreadable sidecar, skipping: %s: %s", path, exc)
            continue
        if not isinstance(data, dict) or not needs_text_fix(data):
            continue

        report.targets += 1
        rel = path.relative_to(kho_root)
        converted = convert_sidecar(data)
        if converted is None:
            report.skipped_unsafe += 1
            log.warning("normalize unsafe, sidecar left as-is: %s", rel)
            continue

        new, changed = converted
        # Text the PDF extractor had already scrambled (a character separated
        # from its own vowel by a line break) can't be decoded by anything;
        # count it so the residue is visible rather than silently shipped.
        residue = sum(1 for u in new["units"] if not _is_ocr(u) and looks_vni(u["text"]))
        report.rewritten += 1
        report.units_changed += changed
        report.units_still_vni += residue
        log.info("normalize %s: %d/%d units rewritten%s",
                 rel, changed, len(new["units"]),
                 f", {residue} still hold broken fragments" if residue else "")
        if not apply:
            continue
        backup = backup_root / rel
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, backup)
        _write_atomic(path, new)

    return report


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="gu-library-worker vnifix",
        description="Normalize sidecar text so search can match it: decode "
                    "legacy VNI-Times encoding and compose separated tone "
                    "marks (NFC). Reports only unless --apply is given.")
    p.add_argument("--kho", action="append", required=True, metavar="KHO_ROOT",
                   help="Path to a kho root folder. Repeat --kho for multiple "
                        "kho; they are processed sequentially in one process.")
    p.add_argument("--apply", action="store_true",
                   help="Write the converted sidecars. Without it, nothing is "
                        "modified and the run is a report.")
    p.add_argument("--log-level", default="INFO")
    return p


def run(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    for kho_path in args.kho:
        kho_root = Path(kho_path)
        label = kho_root.parent.name or kho_root.name or str(kho_root)
        if not kho_root.is_dir():
            log.error("kho not found, skipping: %s", kho_root)
            continue
        with kho_logging(kho_root, label):
            log.info("text normalize %s: kho=%s",
                     "APPLY" if args.apply else "DRY-RUN",
                     kho_root)
            try:
                report = vnifix_kho(kho_root, apply=args.apply)
            except Exception as exc:
                log.exception("kho failed, skipping: %s: %s", kho_root, exc)
                continue
            log.info("done: targets=%d rewritten=%d skipped_unsafe=%d "
                     "units_changed=%d units_still_vni=%d%s",
                     report.targets, report.rewritten, report.skipped_unsafe,
                     report.units_changed, report.units_still_vni,
                     "" if args.apply else " (dry run, nothing written)")
    return 0


if __name__ == "__main__":
    sys.exit(run())
