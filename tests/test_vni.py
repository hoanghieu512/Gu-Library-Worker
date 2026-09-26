import pytest

from gu_library_worker.vni import (
    convert_text,
    decode_vni,
    looks_unicode,
    looks_vni,
    normalize_text,
)


# Real strings lifted from the Prod decks, with the reading they must produce.
REAL_SAMPLES = [
    ("CHÖÔNG XV", "CHƯƠNG XV"),
    ("MIEÃN, GIAÛM TRAÙCH NHIEÄM HÌNH SÖÏ", "MIỄN, GIẢM TRÁCH NHIỆM HÌNH SỰ"),
    ("Khaùi nieäm", "Khái niệm"),
    ("nhieäm vuï cuûa luaät hình söï", "nhiệm vụ của luật hình sự"),
    ("Ñoái töôïng ñieàu chænh", "Đối tượng điều chỉnh"),
    ("Ñònh nghóa", "Định nghĩa"),
    ("nguyeân taéc cô baûn", "nguyên tắc cơ bản"),
    ("Baûn chaát giai caáp", "Bản chất giai cấp"),
    ("ñaëc thuø", "đặc thù"),
    ("bình ñaúng veà", "bình đẳng về"),
    ("coù theå ñöôïc", "có thể được"),
    ("ngöôøi", "người"),
    ("maâu thuaãn", "mâu thuẫn"),
    ("Thôøi gian thöû thaùch töø 1 naêm", "Thời gian thử thách từ 1 năm"),
    ("HP CHÆ ÑÖÔÏC AÙP DUÏNG", "HP CHỈ ĐƯỢC ÁP DỤNG"),
    ("Khoa hoïc luaät hình söï", "Khoa học luật hình sự"),
    ("Lyù giaûi", "Lý giải"),
    ("toäi phaïm", "tội phạm"),
]


@pytest.mark.parametrize("vni,expected", REAL_SAMPLES)
def test_decodes_real_deck_text(vni, expected):
    assert decode_vni(vni) == expected


@pytest.mark.parametrize("vni,expected", REAL_SAMPLES)
def test_convert_text_handles_every_sample_carrying_proof(vni, expected):
    from gu_library_worker.vni import has_vni_evidence
    if not has_vni_evidence(vni):
        pytest.skip("no VNI sequence: covered by the limitation test below")
    assert convert_text(vni) == expected


def test_a_vni_phrase_with_no_vni_sequence_is_left_alone():
    """The accepted cost of the `Toà án` rule. `maâu thuaãn` is genuinely VNI,
    but `â` and `ã` are shared letters, so on its own the phrase proves nothing.
    In a real document it sits inside a block that does carry proof, and the
    whole block decodes together."""
    assert convert_text("maâu thuaãn") == "maâu thuaãn"
    assert decode_vni("maâu thuaãn") == "mâu thuẫn"
    assert convert_text("maâu thuaãn, nhieäm vuï") == "mâu thuẫn, nhiệm vụ"


def test_standalone_letters_alone_are_not_enough():
    """`CHÖÔNG XV` is unmistakably VNI to a human, but `Ö` and `Ô` are standalone
    letters, not modifiers — no vowel-plus-modifier sequence, so no proof. It
    decodes only with surrounding text that carries some."""
    assert convert_text("CHÖÔNG XV") == "CHÖÔNG XV"
    assert decode_vni("CHÖÔNG XV") == "CHƯƠNG XV"
    assert convert_text("CHÖÔNG XV: MIEÃN, GIAÛM") == "CHƯƠNG XV: MIỄN, GIẢM"


# --- the safety property: never touch text that is already Unicode -----------

ALREADY_UNICODE = [
    "CÁC TRƯỜNG HỢP LOẠI TRỪ TRÁCH NHIỆM HÌNH SỰ",
    "Cơ sở lý luận về các tình tiết loại trừ",
    "Những quy định chung của Bộ luật hình sự",
    "một người tôi cô đơn ở tổ chức",   # ô/ơ/ò/ó — the ambiguous letters
    "Điều 5 khoản 2 điểm a",
]


@pytest.mark.parametrize("text", ALREADY_UNICODE)
def test_unicode_text_is_returned_unchanged(text):
    assert convert_text(text) == text


def test_plain_ascii_is_untouched():
    assert convert_text("Bai 15 - Mien, giam TNHS (hoan chinh)") == \
        "Bai 15 - Mien, giam TNHS (hoan chinh)"


def test_a_word_with_no_vni_evidence_is_left_alone():
    """`tù` is a real Unicode word; the trailing tone follows a consonant, so
    there is no vowel for it to combine with and nothing may change."""
    assert decode_vni("tù") == "tù"


def test_ambiguous_letters_survive_without_proof():
    """`ô` means `ơ` in VNI and `ô` in Unicode — proof, not the letter, decides.
    Neither spelling carries an exclusive character, so neither is touched."""
    assert convert_text("tôi") == "tôi"
    assert convert_text("toâi") == "toâi"
    # give the same word a block that proves VNI and it resolves
    assert convert_text("toâi vaø baïn") == "tôi và bạn"


# --- mixed-encoding scoping --------------------------------------------------

def test_mixed_block_narrows_to_lines():
    mixed = "nguyeân taéc cuûa luaät\nNhững quy định chung"
    assert convert_text(mixed) == "nguyên tắc của luật\nNhững quy định chung"


def test_mixed_single_line_narrows_to_words():
    """Both real mixed lines in Prod look like this — VNI words abutting Unicode
    ones because the PDF reader merged two font runs. Words carrying proof are
    decoded; `Phaàn` and `naêm` have none of their own and are left, which is
    the price of never mangling a `Toà`."""
    assert convert_text("phaïm vaø hình phaït Phaàn thứ nhất") == \
        "phạm và hình phạt Phaàn thứ nhất"
    assert convert_text("naêm vaø gấp 2 lần mức phạt tù") == \
        "naêm và gấp 2 lần mức phạt tù"


def test_conversion_leaves_no_vni_behind_when_it_acts():
    from gu_library_worker.vni import has_vni_evidence
    for vni, _ in REAL_SAMPLES:
        if has_vni_evidence(vni):
            assert not looks_vni(convert_text(vni))


# --- detection ---------------------------------------------------------------

def test_looks_vni_only_on_vni_exclusive_characters():
    assert looks_vni("nhieäm vuï") is True
    assert looks_vni("nhiệm vụ") is False
    assert looks_vni("tôi có nhà") is False   # ô/ó are shared, not proof


def test_looks_unicode_only_on_unicode_exclusive_characters():
    assert looks_unicode("nhiệm vụ") is True
    assert looks_unicode("nhieäm vuï") is False
    assert looks_unicode("tôi có nhà") is False


# --- normalize ---------------------------------------------------------------

def test_normalize_composes_separated_combining_marks():
    assert normalize_text("ích") == "ích"


def test_normalize_converts_then_composes():
    assert normalize_text("Khaùi nieäm") == "Khái niệm"


def test_empty_text_is_safe():
    assert convert_text("") == ""
    assert normalize_text("") == ""


# --- the false positives real Prod data caught ------------------------------
# `oà` / `oá` is a VNI pair (o + circumflex-tone) AND an everyday Unicode
# sequence — the tone landing on the second vowel of `oa`. Reading it as
# evidence turned `Toà án` into `Tồ án` across four real documents.

NATURAL_UNICODE_PAIRS = [
    "Toà án nhân dân Tối cao",
    "hoàn thiện pháp luật",
    "Gs. Ts. Nguyễn Ngọc Hoà",
    "TS. Hoàng Anh Tuyên",
    "hoá đơn",
    "khoá học",
    "goá bụa",
    "hoè, loè loẹt",
    "thuý, tuý luý",
]


@pytest.mark.parametrize("text", NATURAL_UNICODE_PAIRS)
def test_natural_vowel_clusters_are_never_treated_as_vni(text):
    assert convert_text(text) == text
    assert normalize_text(text) == text


def test_a_vowel_plus_tone_is_not_evidence_on_its_own():
    from gu_library_worker.vni import has_vni_evidence
    assert has_vni_evidence("Toà án") is False
    assert has_vni_evidence("nhieäm vuï") is True


def test_a_vni_block_still_decodes_its_shared_letter_words():
    """Proven VNI by one exclusive character, the whole block decodes — that is
    what makes `cô` -> `cơ` and `toâi` -> `tôi` right rather than reckless."""
    assert convert_text("cô sôû lyù luaän") == "cơ sở lý luận"


def test_a_word_without_proof_survives_a_mixed_line_unchanged():
    """`Phaàn` really is VNI, but alone it carries no exclusive character, so it
    is left rather than risk mangling a `Toà`-shaped Unicode word."""
    out = convert_text("phaïm vaø hình Phaàn thứ nhất")
    assert out.startswith("phạm và hình ")
    assert out.endswith(" thứ nhất")


# --- the other false positives real Prod data caught -------------------------
# `ö ä ü ñ` are exclusive to VNI only *within Vietnamese*. This kho cites German
# and Spanish sources, and a character-only rule turned `öffentliches` into
# `ưffentliches` and `Acuña` into `Acuđa`.

FOREIGN_TEXT = [
    "Zeitschrift für ausländisches öffentliches Recht und Völkerrecht",
    "11. Jairo Acuña-Alfaro, Cố vấn Chính sách về cải cách hành chính",
    "Søren Kierkegaard, København",
    "El Niño, mañana, señor",
    "Bäume, schön, Müller, Größe",
]


@pytest.mark.parametrize("text", FOREIGN_TEXT)
def test_foreign_diacritics_are_never_read_as_vni(text):
    assert convert_text(text) == text
    assert normalize_text(text) == text


def test_a_foreign_letter_alone_is_not_evidence():
    from gu_library_worker.vni import has_vni_evidence
    assert has_vni_evidence("öffentliches") is False
    assert has_vni_evidence("Acuña") is False
    assert has_vni_evidence("cuûa") is True      # same letters, after a vowel


def test_an_exclusive_letter_counts_once_a_line_has_proved_itself():
    """`ñaõ` carries `ñ` but no vowel-plus-modifier pair. On its own that is not
    enough; inside a line that already proved VNI, it is."""
    from gu_library_worker.vni import has_vni_evidence
    assert has_vni_evidence("ñaõ") is False
    assert convert_text("ñaõ") == "ñaõ"
    assert convert_text("A ñaõ thöïc hieän") == "A đã thực hiện"
