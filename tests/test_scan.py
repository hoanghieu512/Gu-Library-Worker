# tests/test_scan.py
import json
from pathlib import Path
from gu_library_worker.config import Paths
from gu_library_worker.scan import scan_once

def _convert(src, outdir, **kw):
    import fitz
    out = outdir / (src.stem + ".pdf")
    doc = fitz.open(); page = doc.new_page()
    page.insert_text((72, 72), "Điều 1. Nội dung", fontsize=12)
    doc.save(out); doc.close()
    return out

def _kho(tmp_path):
    inbox = tmp_path / "_inbox"
    inbox.mkdir()
    return Paths(kho_root=tmp_path), inbox

def test_docx_filed_into_subject_and_original_removed(make_docx, tmp_path):
    paths, inbox = _kho(tmp_path)
    src = make_docx("law.docx", ["Điều 1. Phạm vi", "Nội dung điều một."])
    src.rename(inbox / "[Luật Công chứng] law.docx")
    report = scan_once(paths, convert_fn=_convert, sleep=lambda s: None)
    subject = tmp_path / "Luật Công chứng"
    assert (subject / "law.pdf").exists()
    assert (subject / "law.json").exists()
    assert not (inbox / "[Luật Công chứng] law.docx").exists()
    assert report.processed == 1

def test_tmp_file_is_skipped_and_left(tmp_path):
    paths, inbox = _kho(tmp_path)
    (inbox / "junk.pdf.tmp").write_bytes(b"x")
    report = scan_once(paths, convert_fn=_convert, sleep=lambda s: None)
    assert (inbox / "junk.pdf.tmp").exists()  # left for manual cleanup
    assert report.processed == 0

def test_duplicate_target_gets_suffix(make_pdf, tmp_path):
    paths, inbox = _kho(tmp_path)
    subject = tmp_path / "Môn"
    subject.mkdir()
    (subject / "doc.pdf").write_bytes(b"%PDF-1.4 existing")
    f = make_pdf("src.pdf", ["Điều 1. Nội dung mới"])
    f.rename(inbox / "[Môn] doc.pdf")
    scan_once(paths, convert_fn=_convert, sleep=lambda s: None)
    assert (subject / "doc.pdf").exists()        # original kept
    assert (subject / "doc (1).pdf").exists()     # new pair suffixed
    assert (subject / "doc (1).json").exists()

def test_unclassified_goes_to_its_folder(make_pdf, tmp_path):
    paths, inbox = _kho(tmp_path)
    f = make_pdf("x.pdf", ["Điều 1. Nội dung"])
    f.rename(inbox / "[Chưa phân loại] x.pdf")
    scan_once(paths, convert_fn=_convert, sleep=lambda s: None)
    assert (tmp_path / "Chưa phân loại" / "x.pdf").exists()

def test_one_bad_file_does_not_abort_others(make_pdf, tmp_path):
    paths, inbox = _kho(tmp_path)
    good = make_pdf("g.pdf", ["Điều 1. Tốt"])
    good.rename(inbox / "[Môn] good.pdf")
    (inbox / "[Môn] broken.pdf").write_bytes(b"not a real pdf")
    report = scan_once(paths, convert_fn=_convert, sleep=lambda s: None)
    assert (tmp_path / "Môn" / "good.pdf").exists()
    assert report.processed == 1
    assert report.failed >= 1
    assert (inbox / "[Môn] broken.pdf").exists()  # failed file left in place
