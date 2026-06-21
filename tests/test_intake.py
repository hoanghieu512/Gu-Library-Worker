from gu_library_worker.intake import is_candidate_name, wait_until_stable

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
