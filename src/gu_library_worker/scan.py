# src/gu_library_worker/scan.py
from __future__ import annotations
import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .config import Paths
from .intake import is_candidate_name, wait_until_stable
from .naming import Reservations, resolve_target_stems
from .pipeline import process_one_file
from .schema import validate_sidecar
from .writer import write_pair
from .convert import to_pdf as default_convert

log = logging.getLogger("gu_library_worker")

@dataclass
class ScanReport:
    processed: int = 0
    skipped: int = 0
    failed: int = 0

def scan_once(paths: Paths, *, convert_fn: Callable[..., Path] = default_convert,
              sleep=None) -> ScanReport:
    report = ScanReport()
    inbox = paths.inbox
    if not inbox.exists():
        return report

    reservations = Reservations()
    stable_kwargs = {} if sleep is None else {"sleep": sleep}

    for entry in sorted(inbox.iterdir()):
        if not entry.is_file():
            continue
        if not is_candidate_name(entry.name):
            log.info("skipped (unsupported/temp name): %s", entry.name)
            report.skipped += 1
            continue
        if not wait_until_stable(entry, **stable_kwargs):
            log.info("not stable yet, leaving: %s", entry.name)
            report.skipped += 1
            continue
        try:
            with tempfile.TemporaryDirectory() as td:
                prepared = process_one_file(entry, tmp_workdir=Path(td),
                                            convert_fn=convert_fn)
                errors = validate_sidecar(prepared.sidecar)
                if errors:
                    raise ValueError(f"sidecar invalid: {errors}")
                subject_dir = paths.subject_dir(prepared.subject)
                pdf_dst, json_dst = resolve_target_stems(
                    subject_dir, prepared.clean_name, reservations)
                write_pair(prepared.canonical_pdf, prepared.sidecar,
                           pdf_dst, json_dst, entry)
            report.processed += 1
            log.info("processed %s -> %s", entry.name, pdf_dst)
        except Exception as exc:  # isolate per-file failure; leave original
            report.failed += 1
            log.exception("failed to process %s: %s", entry.name, exc)
    return report
