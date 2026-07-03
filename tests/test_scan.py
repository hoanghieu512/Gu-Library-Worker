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

def test_nondoc_tmp_is_skipped_and_left(tmp_path):
    # A .tmp NOT preceded by a document extension is not the SAF artifact -> left.
    paths, inbox = _kho(tmp_path)
    (inbox / "random.tmp").write_bytes(b"x")
    report = scan_once(paths, convert_fn=_convert, sleep=lambda s: None)
    assert (inbox / "random.tmp").exists()  # left for manual cleanup
    assert report.processed == 0

def test_app_tmp_pdf_normalized_and_filed(make_pdf, tmp_path):
    paths, inbox = _kho(tmp_path)
    f = make_pdf("src.pdf", ["Điều 1. Nội dung"])
    f.rename(inbox / "[Tố tụng Hình sự] a.pdf.tmp")
    report = scan_once(paths, convert_fn=_convert, sleep=lambda s: None)
    assert report.processed == 1
    subject = tmp_path / "Tố tụng Hình sự"
    assert (subject / "a.pdf").exists() and (subject / "a.json").exists()
    assert not any(p.name.endswith(".tmp") for p in inbox.iterdir())  # tmp consumed
    assert not (inbox / "[Tố tụng Hình sự] a.pdf").exists()           # not left in inbox

def test_app_tmp_docx_pptx_ppt_normalized(make_docx, make_pptx, tmp_path):
    paths, inbox = _kho(tmp_path)
    make_docx("d.docx", ["Điều 1. Phạm vi", "Nội dung."]).rename(
        inbox / "[Chưa phân loại] b.docx.tmp")
    make_pptx("p.pptx", ["Slide A"]).rename(
        inbox / "[Chưa phân loại] d.pptx.tmp")
    # legacy .ppt: native libs can't read OLE -> converted then read from PDF
    (inbox / "[Chưa phân loại] c.ppt.tmp").write_bytes(b"legacy ole bytes")
    report = scan_once(paths, convert_fn=_convert, sleep=lambda s: None)
    assert report.processed == 3
    area = tmp_path / "Chưa phân loại"
    for stem in ("b", "c", "d"):
        assert (area / f"{stem}.pdf").exists() and (area / f"{stem}.json").exists()
    assert not any(p.name.endswith(".tmp") for p in inbox.iterdir())

def test_syncthing_and_nondoc_tmp_left_alone(tmp_path):
    paths, inbox = _kho(tmp_path)
    (inbox / ".syncthing.x.pdf.tmp").write_bytes(b"x")
    (inbox / "notes.txt.tmp").write_bytes(b"x")
    report = scan_once(paths, convert_fn=_convert, sleep=lambda s: None)
    assert report.processed == 0
    assert (inbox / ".syncthing.x.pdf.tmp").exists()
    assert (inbox / "notes.txt.tmp").exists()

def test_tmp_strip_dedups_against_existing_inbox_file(make_pdf, tmp_path):
    paths, inbox = _kho(tmp_path)
    make_pdf("real.pdf", ["Điều 1. Một"]).rename(inbox / "[Môn] X.pdf")      # real, clean
    make_pdf("t.pdf", ["Điều 1. Hai"]).rename(inbox / "[Môn] X.pdf.tmp")     # collides on strip
    report = scan_once(paths, convert_fn=_convert, sleep=lambda s: None)
    assert report.processed == 2
    subject = tmp_path / "Môn"
    assert sorted(p.name for p in subject.glob("*.pdf")) == ["X (1).pdf", "X.pdf"]  # no clobber

def test_double_tmp_normalized(make_pdf, tmp_path):
    paths, inbox = _kho(tmp_path)
    make_pdf("src.pdf", ["Điều 1. Nội dung"]).rename(inbox / "[Môn] x.pdf.tmp.tmp")
    report = scan_once(paths, convert_fn=_convert, sleep=lambda s: None)
    assert report.processed == 1
    assert (tmp_path / "Môn" / "x.pdf").exists()
    assert not any(p.name.endswith(".tmp") for p in inbox.iterdir())

def test_unstable_app_tmp_not_stripped_before_stable(make_pdf, tmp_path, monkeypatch):
    # LƯU Ý 1: stability check runs on the .tmp candidate BEFORE the strip; an
    # unstable (still-writing) file is left as-is, not renamed or processed.
    import gu_library_worker.scan as scan_mod
    paths, inbox = _kho(tmp_path)
    make_pdf("src.pdf", ["Điều 1. Nội dung"]).rename(inbox / "[Môn] x.pdf.tmp")
    seen = {}
    def fake_stable(path, **kw):
        seen["name"] = path.name
        return False
    monkeypatch.setattr(scan_mod, "wait_until_stable", fake_stable)
    report = scan_once(paths, convert_fn=_convert)
    assert report.processed == 0
    assert (inbox / "[Môn] x.pdf.tmp").exists()         # not renamed
    assert not (inbox / "[Môn] x.pdf").exists()         # not stripped
    assert seen["name"] == "[Môn] x.pdf.tmp"            # stability saw the .tmp first

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

def test_resent_duplicate_against_existing_folder_pair(make_pdf, tmp_path):
    # The real mini-PC case: a file processed in a PREVIOUS run already sits in
    # the subject folder; the same file is shared again and lands in _inbox/.
    # The new pair must be suffixed (1) against the on-disk file (not just the
    # same-scan set), the old pair must NOT be overwritten, and the inbox cleared.
    paths, inbox = _kho(tmp_path)
    subject = tmp_path / "Luật Đất đai"
    subject.mkdir()
    (subject / "31-2024-qh15_1.pdf").write_bytes(b"%PDF-1.4 old")
    (subject / "31-2024-qh15_1.json").write_text('{"schemaVersion": 1}', encoding="utf-8")
    old_bytes = (subject / "31-2024-qh15_1.pdf").read_bytes()

    f = make_pdf("re.pdf", ["Điều 1. Nội dung gửi lại"])
    f.rename(inbox / "[Luật Đất đai] 31-2024-qh15_1.pdf")
    report = scan_once(paths, convert_fn=_convert, sleep=lambda s: None)

    assert report.processed == 1
    assert (subject / "31-2024-qh15_1 (1).pdf").exists()
    assert (subject / "31-2024-qh15_1 (1).json").exists()           # pair same suffix
    assert (subject / "31-2024-qh15_1.pdf").read_bytes() == old_bytes  # not overwritten
    assert not (inbox / "[Luật Đất đai] 31-2024-qh15_1.pdf").exists()  # inbox cleared

def test_resent_duplicate_increments_to_next_free(make_pdf, tmp_path):
    paths, inbox = _kho(tmp_path)
    subject = tmp_path / "Môn"
    subject.mkdir()
    for stem in ("X", "X (1)"):
        (subject / f"{stem}.pdf").write_bytes(b"%PDF-1.4")
        (subject / f"{stem}.json").write_text('{"schemaVersion": 1}', encoding="utf-8")
    f = make_pdf("s.pdf", ["Điều 1. Nội dung"])
    f.rename(inbox / "[Môn] X.pdf")
    scan_once(paths, convert_fn=_convert, sleep=lambda s: None)
    assert (subject / "X (2).pdf").exists()
    assert (subject / "X (2).json").exists()

def test_same_scan_two_inbox_files_same_target(make_pdf, tmp_path):
    # Keep the old-good case: two files cleaning to the same target in ONE pass.
    paths, inbox = _kho(tmp_path)
    a = make_pdf("a.pdf", ["Điều 1. Một"])
    a.rename(inbox / "[Môn] doc.pdf")
    b = make_pdf("b.pdf", ["Điều 1. Hai"])
    b.rename(inbox / "[Môn]doc.pdf")     # no space -> same clean name "doc.pdf"
    report = scan_once(paths, convert_fn=_convert, sleep=lambda s: None)
    subject = tmp_path / "Môn"
    assert report.processed == 2
    assert sorted(p.name for p in subject.glob("*.pdf")) == ["doc (1).pdf", "doc.pdf"]
    assert sorted(p.name for p in subject.glob("*.json")) == ["doc (1).json", "doc.json"]

def test_nested_prefix_filed_into_subfolder(make_pdf, tmp_path):
    paths, inbox = _kho(tmp_path)
    make_pdf("s.pdf", ["Điều 1. Nội dung"]).rename(
        inbox / "[Luật Đất đai][Bài giảng] x.pdf")
    report = scan_once(paths, convert_fn=_convert, sleep=lambda s: None)
    assert report.processed == 1
    dest = tmp_path / "Luật Đất đai" / "Bài giảng"     # folder auto-created
    assert (dest / "x.pdf").exists() and (dest / "x.json").exists()
    assert not any(p.name.endswith(".pdf") for p in inbox.iterdir())

def test_nested_prefix_three_levels(make_pdf, tmp_path):
    paths, inbox = _kho(tmp_path)
    make_pdf("s.pdf", ["Điều 1. Nội dung"]).rename(
        inbox / "[Môn][Bài giảng][Chương 1] y.pdf")
    scan_once(paths, convert_fn=_convert, sleep=lambda s: None)
    assert (tmp_path / "Môn" / "Bài giảng" / "Chương 1" / "y.pdf").exists()

def test_nested_prefix_existing_folder_ok(make_pdf, tmp_path):
    paths, inbox = _kho(tmp_path)
    (tmp_path / "Môn" / "Bài giảng").mkdir(parents=True)   # app pre-created + synced
    make_pdf("s.pdf", ["Điều 1. Nội dung"]).rename(inbox / "[Môn][Bài giảng] z.pdf")
    report = scan_once(paths, convert_fn=_convert, sleep=lambda s: None)
    assert report.processed == 1 and report.failed == 0
    assert (tmp_path / "Môn" / "Bài giảng" / "z.pdf").exists()

def test_nested_prefix_dup_suffixed_in_subfolder(make_pdf, tmp_path):
    paths, inbox = _kho(tmp_path)
    dest = tmp_path / "Môn" / "Bài giảng"
    dest.mkdir(parents=True)
    (dest / "z.pdf").write_bytes(b"%PDF-1.4 existing")
    make_pdf("s.pdf", ["Điều 1. Mới"]).rename(inbox / "[Môn][Bài giảng] z.pdf")
    scan_once(paths, convert_fn=_convert, sleep=lambda s: None)
    assert (dest / "z.pdf").exists() and (dest / "z (1).pdf").exists()  # no overwrite
    assert (dest / "z (1).json").exists()

def test_unsafe_nested_prefix_goes_to_unclassified_not_stuck(make_pdf, tmp_path):
    paths, inbox = _kho(tmp_path)
    make_pdf("s.pdf", ["Điều 1. Nội dung"]).rename(inbox / "[Môn][..] evil.pdf")
    report = scan_once(paths, convert_fn=_convert, sleep=lambda s: None)
    assert report.processed == 1 and report.failed == 0
    assert (tmp_path / "Chưa phân loại" / "evil.pdf").exists()     # safe area, in kho
    assert not (tmp_path.parent / "evil.pdf").exists()            # never escaped kho
    assert not any(p.name.endswith(".pdf") for p in inbox.iterdir())

def _heavy_scan_inbox(inbox, name, pages=2, img_w=500):
    import fitz
    p = inbox / name
    doc = fitz.open()
    for _ in range(pages):
        page = doc.new_page(width=150, height=200)               # small page, fast
        pm = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, img_w, round(img_w * 200 / 150)))
        pm.set_rect(pm.irect, (235, 235, 235))
        page.insert_image(page.rect, pixmap=pm)
    doc.save(p); doc.close()
    return p

def _max_img_width(pdf):
    import fitz
    with fitz.open(pdf) as d:
        return max(img[2] for page in d for img in page.get_images(full=True))

def test_heavy_scan_normalized_and_original_archived(tmp_path):
    paths, inbox = _kho(tmp_path)
    src = _heavy_scan_inbox(inbox, "[Tố tụng Hình sự] scan.pdf")
    src_size, src_w = src.stat().st_size, _max_img_width(src)
    report = scan_once(paths, convert_fn=_convert, sleep=lambda s: None)
    assert report.processed == 1 and report.failed == 0
    subj = tmp_path / "Tố tụng Hình sự"
    kho_pdf = subj / "scan.pdf"
    assert kho_pdf.exists() and (subj / "scan.json").exists()
    assert _max_img_width(kho_pdf) < src_w                       # kho copy is lighter
    # original archived OUT of the kho (sibling _archive, never synced)
    archived = list(paths.archive_dir.glob("*.pdf"))
    assert len(archived) == 1 and archived[0].stat().st_size == src_size   # untouched
    assert paths.kho_root not in paths.archive_dir.parents       # outside the kho
    assert not any(p.name.endswith(".pdf") for p in inbox.iterdir())  # inbox cleared

def test_heavy_scan_normalized_into_nested_subfolder(tmp_path):
    paths, inbox = _kho(tmp_path)
    _heavy_scan_inbox(inbox, "[Môn][Bài giảng] scan.pdf", pages=1)
    scan_once(paths, convert_fn=_convert, sleep=lambda s: None)
    assert (tmp_path / "Môn" / "Bài giảng" / "scan.pdf").exists()
    assert list(paths.archive_dir.glob("*.pdf"))                 # original archived

def test_image_pdf_filed_not_stuck(tmp_path):
    # A scanned/image PDF (0 text) must be filed with a minimal sidecar, not fail
    # the validator and stay stuck in _inbox retrying forever.
    import fitz
    paths, inbox = _kho(tmp_path)
    p = inbox / "[Tố tụng Hình sự] scan.pdf"
    doc = fitz.open(); doc.new_page(); doc.new_page(); doc.save(p); doc.close()
    report = scan_once(paths, convert_fn=_convert, sleep=lambda s: None)
    assert report.processed == 1 and report.failed == 0
    subject = tmp_path / "Tố tụng Hình sự"
    assert (subject / "scan.pdf").exists() and (subject / "scan.json").exists()
    assert not any(x.name.endswith(".pdf") for x in inbox.iterdir())  # not stuck

def test_worker_never_ingests_stversions(make_pdf, tmp_path):
    # Syncthing versioning lives at the share root (sibling of _inbox) and the
    # worker only scans _inbox/ non-recursively, so versioned files are never
    # re-ingested (which would resurrect deleted docs as junk). Guard both: a
    # .stversions at kho root, and a stray .stversions dir inside _inbox.
    paths, inbox = _kho(tmp_path)
    root_ver = tmp_path / ".stversions" / "Môn"
    root_ver.mkdir(parents=True)
    (root_ver / "old~20260621-082220.pdf").write_bytes(b"%PDF-1.4 versioned")
    inbox_ver = inbox / ".stversions"
    inbox_ver.mkdir()
    (inbox_ver / "deleted~20260621-082220.pdf").write_bytes(b"%PDF-1.4 versioned")

    f = make_pdf("x.pdf", ["Điều 1. Nội dung"])
    f.rename(inbox / "[Môn] x.pdf")
    report = scan_once(paths, convert_fn=_convert, sleep=lambda s: None)

    assert report.processed == 1            # only the real inbox file
    assert (tmp_path / "Môn" / "x.pdf").exists()
    # versioned copies are left exactly where they were, never processed
    assert (root_ver / "old~20260621-082220.pdf").exists()
    assert (inbox_ver / "deleted~20260621-082220.pdf").exists()
    assert not (tmp_path / "Môn" / "old.pdf").exists()
    assert not (tmp_path / "Môn" / "deleted.pdf").exists()
