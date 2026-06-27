# src/gu_library_worker/__main__.py
from __future__ import annotations
import argparse
import logging
import sys
from pathlib import Path

from .config import Paths
from .convert import to_pdf
from .logsetup import attach_log_file
from .scan import scan_once

def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="gu-library-worker",
                                description="Scan kho/_inbox once and file outputs.")
    p.add_argument("--kho", required=True, help="Path to the kho root folder")
    p.add_argument("--soffice", default=None,
                   help="LibreOffice soffice path (auto-detected if omitted; "
                        "or set the GULIB_SOFFICE env var)")
    p.add_argument("--log-level", default="INFO")
    return p

def run(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    paths = Paths(kho_root=Path(args.kho))
    log = logging.getLogger("gu_library_worker")
    attach_log_file(paths.kho_root)  # persistent <kho>/_worker.log for the Scheduled Task
    log.info("scan starting: kho=%s", paths.kho_root)
    convert_fn = lambda src, outdir, **kw: to_pdf(src, outdir, soffice=args.soffice)
    report = scan_once(paths, convert_fn=convert_fn)
    log.info("done: processed=%d skipped=%d failed=%d",
             report.processed, report.skipped, report.failed)
    return 0

if __name__ == "__main__":
    sys.exit(run())
