# src/gu_library_worker/__main__.py
from __future__ import annotations
import argparse
import logging
import sys
from pathlib import Path

from .config import Paths
from .convert import to_pdf
from .logsetup import kho_logging
from .ocr_stage import DEFAULT_BUDGET_S, SLOW_PAGE_MARGIN_S, run_stage
from .scan import scan_once

def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="gu-library-worker",
                                description="Scan one or more kho/_inbox once and file outputs.")
    p.add_argument("--kho", action="append", required=True, metavar="KHO_ROOT",
                   help="Path to a kho root folder. Repeat --kho for multiple kho; "
                        "they are scanned sequentially in one process.")
    p.add_argument("--soffice", default=None,
                   help="LibreOffice soffice path (auto-detected if omitted; "
                        "or set the GULIB_SOFFICE env var)")
    p.add_argument("--log-level", default="INFO")
    p.add_argument("--ocr-budget", type=float, default=DEFAULT_BUDGET_S, metavar="SECONDS",
                   help="OCR time per pass, shared by all kho (default "
                        f"{DEFAULT_BUDGET_S:.0f}). New pages start only in the first "
                        f"BUDGET-{SLOW_PAGE_MARGIN_S:.0f}s so a slow page started last still "
                        "ends inside the pass. OCR runs only for a kho with "
                        "<kho>_ocrcache/ocr.json set to enabled.")
    p.add_argument("--skip-intake", action="store_true",
                   help="skip the _inbox scan and run only the OCR stage "
                        "(manual backfill runs)")
    return p

def _kho_label(kho_root: Path) -> str:
    # parent folder distinguishes environments (GuLibrary vs GuLibrary-Prod),
    # since the kho folder itself is usually just named "kho".
    return kho_root.parent.name or kho_root.name or str(kho_root)

def run(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    log = logging.getLogger("gu_library_worker")
    convert_fn = lambda src, outdir, **kw: to_pdf(src, outdir, soffice=args.soffice)

    # One process, one task: scan each kho SEQUENTIALLY (never two LibreOffice
    # conversions at once — they share a headless profile and would lock). One
    # kho's failure must not stop the rest, so isolate each.
    for kho_path in [] if args.skip_intake else args.kho:
        kho_root = Path(kho_path)
        label = _kho_label(kho_root)
        if not kho_root.is_dir():
            log.error("kho not found, skipping: %s", kho_root)
            continue
        with kho_logging(kho_root, label):
            log.info("scan starting: kho=%s", kho_root)
            try:
                report = scan_once(Paths(kho_root=kho_root), convert_fn=convert_fn)
            except Exception as exc:  # bad perms / mid-scan error -> skip this kho
                log.exception("kho failed, skipping: %s: %s", kho_root, exc)
                continue
            log.info("done: processed=%d skipped=%d failed=%d",
                     report.processed, report.skipped, report.failed)

    # OCR after intake, so a new file is never kept waiting behind image pages.
    # Opt-in per kho; a kho without ocr.json is untouched and logs nothing.
    run_stage([Path(k) for k in args.kho if Path(k).is_dir()], args.ocr_budget, _kho_label)
    return 0

if __name__ == "__main__":
    sys.exit(run())
