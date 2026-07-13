from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

# image inputs: each becomes a one-page PDF (page aspect = image aspect)
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
ACCEPTED_EXTENSIONS = {".pdf", ".doc", ".docx", ".ppt", ".pptx"} | IMAGE_EXTENSIONS
TEMP_SUFFIXES = {".tmp", ".crdownload"}
# names containing this token are Syncthing in-progress temp files
SYNCTHING_TOKEN = ".syncthing."
UNCLASSIFIED = "Chưa phân loại"

# stability check: read size twice this many seconds apart
STABILITY_INTERVAL_SECONDS = 3.0

# map original extension -> sourceFormat enum (schema: pdf|docx|pptx). Images map
# to "pdf" — the kho artifact is a PDF and the schema has no image value; the
# "originated from an image / no text" signal is the IMAGE_PAGE_MARKER unit.
SOURCE_FORMAT = {
    ".pdf": "pdf",
    ".doc": "docx",
    ".docx": "docx",
    ".ppt": "pptx",
    ".pptx": "pptx",
    **{ext: "pdf" for ext in IMAGE_EXTENSIONS},
}

@dataclass(frozen=True)
class Paths:
    kho_root: Path

    @property
    def inbox(self) -> Path:
        return self.kho_root / "_inbox"

    @property
    def archive_dir(self) -> Path:
        # Local archive for originals we replaced (e.g. heavy scans). A SIBLING of
        # the kho, so it is OUTSIDE the Syncthing folder (never synced / in-kho).
        return self.kho_root.with_name(self.kho_root.name + "_archive")

    def subject_dir(self, subject: str) -> Path:
        # `subject` may be a "/"-joined nested path (e.g. "Môn/Bài giảng"); split
        # it into real folders. A plain single-level subject is unchanged.
        parts = [p for p in subject.split("/") if p]
        return self.kho_root.joinpath(*parts) if parts else self.kho_root
