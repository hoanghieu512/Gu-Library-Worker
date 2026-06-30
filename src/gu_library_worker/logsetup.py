# src/gu_library_worker/logsetup.py
"""Persistent, rotating log file for the worker.

A Scheduled Task running in the background swallows stdout, so failures/skips are
invisible. This attaches a rotating file handler at ``<kho>/_worker.log`` (in
ADDITION to stdout) capturing every pass's ScanReport and per-file skip/failure
reasons (with tracebacks). The file is observability only — the worker never
reads it back, so statelessness is preserved. The leading underscore makes the
app/test filters ignore it (same rule as ``_mon.json``).
"""
from __future__ import annotations
import logging
from contextlib import contextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_NAME = "_worker.log"
_LOGGER_NAME = "gu_library_worker"
_FMT = "%(asctime)s %(levelname)s %(message)s"

def attach_log_file(kho_root, *, max_bytes: int = 1_000_000,
                    backup_count: int = 3,
                    level: int = logging.INFO) -> RotatingFileHandler | None:
    """Attach a rotating handler writing to ``<kho>/_worker.log``.

    Returns the handler, or None if the kho dir is missing/unwritable. Idempotent:
    calling it again for the same path returns the existing handler instead of
    stacking duplicates. Rotation caps total size (``max_bytes`` per file,
    ``backup_count`` backups) so a worker polling 24/7 can't grow unbounded.
    """
    kho_root = Path(kho_root)
    if not kho_root.is_dir():
        return None
    log_path = kho_root / LOG_NAME
    logger = logging.getLogger(_LOGGER_NAME)
    # ensure INFO records reach our handler even if no basicConfig ran, without
    # raising the level above a more-verbose setting the user chose (e.g. DEBUG)
    if logger.getEffectiveLevel() > level:
        logger.setLevel(level)
    for handler in logger.handlers:
        if getattr(handler, "_gulib_logfile", None) == str(log_path):
            return handler  # already attached
    try:
        handler = RotatingFileHandler(log_path, maxBytes=max_bytes,
                                      backupCount=backup_count, encoding="utf-8")
    except OSError:
        return None  # never let logging setup break a scan
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(_FMT))
    handler._gulib_logfile = str(log_path)  # type: ignore[attr-defined]
    logger.addHandler(handler)
    return handler

@contextmanager
def kho_logging(kho_root, label: str, *, max_bytes: int = 1_000_000,
                backup_count: int = 3, level: int = logging.INFO):
    """Attach a per-kho ``<kho>/_worker.log`` for the duration of one kho's scan.

    The kho `label` is baked into every line (``... [label] message``) and the
    handler is detached on exit, so each kho's log holds ONLY its own lines —
    Prod and test stay cleanly separated even though one process serves both.
    Yields the handler (or None if the dir is missing/unwritable; the caller
    still logs the skip to stdout). Rotation caps size as in attach_log_file.
    """
    logger = logging.getLogger(_LOGGER_NAME)
    if logger.getEffectiveLevel() > level:
        logger.setLevel(level)
    handler = None
    root = Path(kho_root)
    if root.is_dir():
        try:
            handler = RotatingFileHandler(root / LOG_NAME, maxBytes=max_bytes,
                                          backupCount=backup_count, encoding="utf-8")
            handler.setLevel(level)
            handler.setFormatter(logging.Formatter(
                f"%(asctime)s %(levelname)s [{label}] %(message)s"))
            logger.addHandler(handler)
        except OSError:
            handler = None  # never let logging setup break a scan
    try:
        yield handler
    finally:
        if handler is not None:
            logger.removeHandler(handler)
            handler.close()
