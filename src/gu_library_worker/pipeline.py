# src/gu_library_worker/pipeline.py
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Callable

from .config import SOURCE_FORMAT, IMAGE_EXTENSIONS
from .images import image_to_single_page_pdf
from .prefix import parse_prefix
from .schema import Document, to_sidecar
from .readers.base import Extraction
from .readers.docx_reader import read_docx
from .readers.pptx_reader import read_pptx
from .readers.pdf_reader import read_pdf
from .pages import anchor_pages, page_count
from .convert import to_pdf as default_convert
from .normalize import is_heavy_scan, normalize_pdf

VN_TZ = timezone(timedelta(hours=7))

@dataclass
class Prepared:
    canonical_pdf: Path
    sidecar: dict
    subject: str
    clean_name: str
    normalized: bool = False  # True when the kho copy is a re-rastered version
                              # of `src` (the original must be archived, not deleted)
    archive_original: bool = False  # True when scan must keep `src` in <kho>_archive
                                    # instead of deleting it (heavy re-raster, or a
                                    # legacy .doc/.ppt whose OOXML structure degraded
                                    # through LibreOffice and is worth re-extracting)

def _now_iso() -> str:
    return datetime.now(VN_TZ).isoformat(timespec="seconds")

def _read(src: Path, ext: str) -> Extraction:
    if ext == ".docx":
        return read_docx(src)
    if ext == ".pptx":
        return read_pptx(src)
    if ext == ".pdf":
        return read_pdf(src)
    # legacy .doc/.ppt: native libs can't read -> handled via PDF after convert
    raise ValueError(f"native read unsupported for {ext}")

def process_one_file(
    src: Path,
    *,
    tmp_workdir: Path,
    convert_fn: Callable[..., Path] = default_convert,
) -> Prepared:
    tmp_workdir.mkdir(parents=True, exist_ok=True)
    parsed = parse_prefix(src.name)
    ext = src.suffix.lower()
    source_format = SOURCE_FORMAT[ext]

    normalized = False
    legacy_ole = ext in (".doc", ".ppt")  # OLE original -> converted via LibreOffice;
                                          # structure degrades, so preserve the source
    if ext == ".pdf":
        canonical_pdf = src
        extraction = read_pdf(src)
        # Zero-text (scanned/image) PDF whose page rasters are too heavy for a
        # phone viewer -> republish a lighter 150dpi JPEG version into the kho.
        # Text PDFs and already-light scans are never re-rastered.
        if extraction.image_pdf and is_heavy_scan(src):
            normalized_pdf = tmp_workdir / (src.stem + "_normalized.pdf")
            normalize_pdf(src, normalized_pdf)
            canonical_pdf = normalized_pdf
            extraction = read_pdf(canonical_pdf)   # sidecar matches the kho copy
            normalized = True
    elif ext in IMAGE_EXTENSIONS:
        # One image -> one-page PDF (page aspect = image aspect), then the same
        # zero-text + heavy-scan path as a scanned PDF. The source image is a
        # consumed input (Gú keeps the phone copy), so `normalized` stays False:
        # the original is deleted, NOT archived like a re-rastered scan.
        built = tmp_workdir / (src.stem + "_img.pdf")
        image_to_single_page_pdf(src, built)
        canonical_pdf = built
        extraction = read_pdf(built)               # zero-text -> image_pdf sidecar
        if extraction.image_pdf and is_heavy_scan(built):
            light = tmp_workdir / (src.stem + "_img_light.pdf")
            normalize_pdf(built, light)
            canonical_pdf = light
            extraction = read_pdf(light)
    elif ext in (".docx", ".pptx"):
        canonical_pdf = convert_fn(src, tmp_workdir)
        extraction = _read(src, ext)
        if ext == ".docx":
            anchor_pages(extraction.units, canonical_pdf)  # pptx already anchored
    else:  # .doc / .ppt legacy -> convert then extract from the PDF
        canonical_pdf = convert_fn(src, tmp_workdir)
        extraction = read_pdf(canonical_pdf)

    doc = Document(
        title=Path(parsed.clean_name).stem,
        source=parsed.source,
        sourceFormat=source_format,
        kind=extraction.kind,
        units=extraction.units,
        addedAt=_now_iso(),
        pageCount=page_count(canonical_pdf),
    )
    return Prepared(
        canonical_pdf=canonical_pdf,
        sidecar=to_sidecar(doc),
        subject=parsed.subject,
        clean_name=parsed.clean_name,
        normalized=normalized,
        archive_original=normalized or legacy_ole,
    )
