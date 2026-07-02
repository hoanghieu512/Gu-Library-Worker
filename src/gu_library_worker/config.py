from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

ACCEPTED_EXTENSIONS = {".pdf", ".doc", ".docx", ".ppt", ".pptx"}
TEMP_SUFFIXES = {".tmp", ".crdownload"}
# names containing this token are Syncthing in-progress temp files
SYNCTHING_TOKEN = ".syncthing."
UNCLASSIFIED = "Chưa phân loại"

# stability check: read size twice this many seconds apart
STABILITY_INTERVAL_SECONDS = 3.0

# map original extension -> sourceFormat enum (pdf|docx|pptx)
SOURCE_FORMAT = {
    ".pdf": "pdf",
    ".doc": "docx",
    ".docx": "docx",
    ".ppt": "pptx",
    ".pptx": "pptx",
}

@dataclass(frozen=True)
class Paths:
    kho_root: Path

    @property
    def inbox(self) -> Path:
        return self.kho_root / "_inbox"

    def subject_dir(self, subject: str) -> Path:
        # `subject` may be a "/"-joined nested path (e.g. "Môn/Bài giảng"); split
        # it into real folders. A plain single-level subject is unchanged.
        parts = [p for p in subject.split("/") if p]
        return self.kho_root.joinpath(*parts) if parts else self.kho_root
