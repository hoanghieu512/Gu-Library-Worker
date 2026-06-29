from gu_library_worker.intake import is_candidate_name, normalize_tmp_name, wait_until_stable

def test_accepts_supported_extensions():
    assert is_candidate_name("[Môn] a.pdf")
    assert is_candidate_name("b.docx")
    assert is_candidate_name("c.PPTX")  # case-insensitive

def test_rejects_temp_and_unknown():
    assert not is_candidate_name("a.pdf.tmp")
    assert not is_candidate_name("b.crdownload")
    assert not is_candidate_name("notes.txt")
    assert not is_candidate_name("archive.zip")

def test_rejects_syncthing_and_hidden():
    assert not is_candidate_name(".syncthing.a.pdf.tmp")
    assert not is_candidate_name(".hidden.pdf")

def test_normalize_strips_doc_ext_tmp():
    assert normalize_tmp_name("[Tố tụng Hình sự] a.pdf.tmp") == "[Tố tụng Hình sự] a.pdf"
    assert normalize_tmp_name("[Chưa phân loại] b.docx.tmp") == "[Chưa phân loại] b.docx"
    assert normalize_tmp_name("c.ppt.tmp") == "c.ppt"
    assert normalize_tmp_name("d.pptx.tmp") == "d.pptx"
    # dotted stem preserved
    assert normalize_tmp_name("[X] 5.17. Luật.pdf.tmp") == "[X] 5.17. Luật.pdf"

def test_normalize_handles_multiple_tmp_layers():
    assert normalize_tmp_name("[Môn] x.pdf.tmp.tmp") == "[Môn] x.pdf"
    assert normalize_tmp_name("x.pdf.tmp.tmp.tmp") == "x.pdf"

def test_normalize_returns_none_for_non_artifacts():
    assert normalize_tmp_name(".syncthing.a.pdf.tmp") is None   # Syncthing in-progress
    assert normalize_tmp_name("random.tmp") is None             # no doc ext before .tmp
    assert normalize_tmp_name("notes.txt.tmp") is None          # non-document ext
    assert normalize_tmp_name("a.pdf.crdownload") is None       # not a .tmp
    assert normalize_tmp_name("[Môn] a.pdf") is None            # already clean, not a .tmp
    assert normalize_tmp_name(".hidden.pdf.tmp") is None        # hidden/system

def test_stability_true_when_size_holds(tmp_path):
    f = tmp_path / "x.pdf"
    f.write_bytes(b"1234")
    sizes = iter([4, 4])
    assert wait_until_stable(f, sleep=lambda s: None,
                             _stat_size=lambda p: next(sizes)) is True

def test_stability_false_when_size_changes(tmp_path):
    f = tmp_path / "x.pdf"
    f.write_bytes(b"1234")
    sizes = iter([4, 9])
    assert wait_until_stable(f, sleep=lambda s: None,
                             _stat_size=lambda p: next(sizes)) is False
