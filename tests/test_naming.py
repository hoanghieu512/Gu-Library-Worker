# tests/test_naming.py
from gu_library_worker.naming import resolve_target_stems, Reservations

def test_basic_pair_names(tmp_path):
    subject = tmp_path / "Môn"
    subject.mkdir()
    res = Reservations()
    pdf, js = resolve_target_stems(subject, "bai-giang.pdf", res)
    assert pdf.name == "bai-giang.pdf"
    assert js.name == "bai-giang.json"

def test_suffix_when_disk_collision(tmp_path):
    subject = tmp_path / "Môn"
    subject.mkdir()
    (subject / "bai-giang.pdf").write_bytes(b"x")
    res = Reservations()
    pdf, js = resolve_target_stems(subject, "bai-giang.pdf", res)
    assert pdf.name == "bai-giang (1).pdf"
    assert js.name == "bai-giang (1).json"

def test_suffix_when_reserved_same_scan(tmp_path):
    subject = tmp_path / "Môn"
    subject.mkdir()
    res = Reservations()
    resolve_target_stems(subject, "x.pdf", res)        # reserves "x"
    pdf, js = resolve_target_stems(subject, "x.pdf", res)
    assert pdf.name == "x (1).pdf"
    assert js.name == "x (1).json"

def test_suffix_increments(tmp_path):
    subject = tmp_path / "Môn"
    subject.mkdir()
    (subject / "x.pdf").write_bytes(b"a")
    (subject / "x (1).pdf").write_bytes(b"b")
    res = Reservations()
    pdf, _ = resolve_target_stems(subject, "x.pdf", res)
    assert pdf.name == "x (2).pdf"
