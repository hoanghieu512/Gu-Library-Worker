from pathlib import Path
from gu_library_worker.config import (
    Paths, ACCEPTED_EXTENSIONS, IMAGE_EXTENSIONS, SOURCE_FORMAT, TEMP_SUFFIXES, UNCLASSIFIED,
)

def test_paths_derive_inbox_from_kho(tmp_path):
    p = Paths(kho_root=tmp_path)
    assert p.inbox == tmp_path / "_inbox"

def test_subject_dir_creates_under_kho(tmp_path):
    p = Paths(kho_root=tmp_path)
    assert p.subject_dir("Luật Công chứng") == tmp_path / "Luật Công chứng"
    assert p.subject_dir(UNCLASSIFIED) == tmp_path / "Chưa phân loại"

def test_subject_dir_nested(tmp_path):
    p = Paths(kho_root=tmp_path)
    assert p.subject_dir("Môn/Bài giảng") == tmp_path / "Môn" / "Bài giảng"
    assert p.subject_dir("A/B/C") == tmp_path / "A" / "B" / "C"

def test_constants_shapes():
    assert {".pdf", ".doc", ".docx", ".ppt", ".pptx"} <= ACCEPTED_EXTENSIONS
    assert IMAGE_EXTENSIONS <= ACCEPTED_EXTENSIONS          # images are accepted too
    assert {".jpg", ".jpeg", ".png"} <= IMAGE_EXTENSIONS
    assert all(SOURCE_FORMAT[ext] == "pdf" for ext in IMAGE_EXTENSIONS)  # image -> pdf doc
    assert ".tmp" in TEMP_SUFFIXES and ".crdownload" in TEMP_SUFFIXES
    assert UNCLASSIFIED == "Chưa phân loại"
