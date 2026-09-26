# src/gu_library_worker/vni.py
"""Transliterate legacy VNI-Times text into Unicode Vietnamese.

Slide decks written before Unicode stored Vietnamese as ASCII letters in a
VNI-Times font: the *bytes* say `CHÖÔNG XV — MIEÃN, GIAÛM`, only the font made
them look like `CHƯƠNG XV — MIỄN, GIẢM`. LibreOffice substitutes a normal font
when converting, so the sidecar ends up holding those raw bytes — readable to
nobody and unsearchable, since typing "miễn giảm" can never match "MIEÃN, GIAÛM".

VNI writes a vowel as a plain ASCII letter followed by a modifier character
(`aù` = á, `eä` = ệ), plus a few standalone letters (`ñ` = đ, `ö` = ư, `ô` = ơ).
Three of those standalone letters — `ò` `ó` `ô` — are also perfectly ordinary
Unicode Vietnamese characters, so a document that mixes both encodings cannot be
decoded character by character: `ô` means `ơ` in a VNI run and `ô` in a Unicode
one. `convert_text` resolves that by scope rather than by guesswork, narrowing
block → line → word until each piece is unambiguously one encoding or the other,
and leaving anything still ambiguous exactly as it was.
"""
from __future__ import annotations

import re
import unicodedata

# Characters VNI produces that Vietnamese Unicode never contains. Their presence
# is positive proof a run of text is VNI-encoded.
VNI_ONLY = set("öÖøØûÛïÏäÄåÅñÑëËüÜæÆ")
# Characters only real Unicode Vietnamese contains — VNI text, being Latin-1,
# can never produce them. Their presence proves a run is already Unicode.
UNICODE_ONLY = {chr(c) for c in range(0x1EA0, 0x1EFA)} | set("ăĂđĐơƠưƯ")

# Standalone VNI letters -> Unicode. `ì í ò ó` already carry their tone; the rest
# are bare vowels that a following modifier may still tone.
_SINGLE = {
    "ñ": "đ", "Ñ": "Đ",
    "ö": "ư", "Ö": "Ư",
    "ô": "ơ", "Ô": "Ơ",
    "æ": "ỉ", "Æ": "Ỉ",
    "ì": "ì", "Ì": "Ì",
    "í": "í", "Í": "Í",
    "ò": "ị", "Ò": "Ị",
    "ó": "ĩ", "Ó": "Ĩ",
}

# Modifier characters, grouped by what they do to the vowel before them.
_PLAIN_TONES = "ùøûõï"      # sắc huyền hỏi ngã nặng
_CIRCUMFLEX = "âáàåãä"      # ˆ then ˆ+sắc ˆ+huyền ˆ+hỏi ˆ+ngã ˆ+nặng
_BREVE = "êéèúüë"           # ˘ then ˘+sắc ˘+huyền ˘+hỏi ˘+ngã ˘+nặng

# Result of <vowel> + <modifier>, in the modifier order above.
_PAIRS_LOWER = {
    ("a", _PLAIN_TONES): "áàảãạ",
    ("a", _CIRCUMFLEX): "âấầẩẫậ",
    ("a", _BREVE): "ăắằẳẵặ",
    ("e", _PLAIN_TONES): "éèẻẽẹ",
    ("e", _CIRCUMFLEX): "êếềểễệ",
    ("i", _PLAIN_TONES): "íìỉĩị",
    ("o", _PLAIN_TONES): "óòỏõọ",
    ("o", _CIRCUMFLEX): "ôốồổỗộ",
    ("u", _PLAIN_TONES): "úùủũụ",
    ("y", _PLAIN_TONES): "ýỳỷỹỵ",
    # `ô`/`ö` become ơ/ư via _SINGLE first, so a tone can still follow them
    ("ơ", _PLAIN_TONES): "ớờởỡợ",
    ("ư", _PLAIN_TONES): "ứừửữự",
}


def _build_pair_table() -> dict[str, str]:
    table: dict[str, str] = {}
    for (base, modifiers), results in _PAIRS_LOWER.items():
        for modifier, result in zip(modifiers, results):
            table[base + modifier] = result
            # Uppercase base takes the uppercase result; the modifier's own case
            # is ignored, since real files write `AÙ` and `Aù` alike.
            table[base.upper() + modifier] = result.upper()
            table[base + modifier.upper()] = result
            table[base.upper() + modifier.upper()] = result.upper()
    return table


_PAIRS = _build_pair_table()
_MODIFIERS = set(_PLAIN_TONES + _CIRCUMFLEX + _BREVE)
_MODIFIERS |= {c.upper() for c in _MODIFIERS}


def decode_vni(text: str) -> str:
    """Transliterate `text` as if all of it were VNI. Unconditional — callers
    must have established the scope really is VNI (see `convert_text`)."""
    # Standalone letters first, so `ô`->`ơ` and `ö`->`ư` are in place before a
    # following tone modifier is applied to them (`ngöôøi` -> `người`).
    out: list[str] = []
    for ch in text:
        out.append(_SINGLE.get(ch, ch))

    result: list[str] = []
    for ch in out:
        if result and ch in _MODIFIERS:
            pair = _PAIRS.get(result[-1] + ch)
            if pair is not None:
                result[-1] = pair
                continue
        result.append(ch)
    return "".join(result)


def looks_vni(text: str) -> bool:
    """True when `text` carries a character VNI produces and Unicode never does."""
    return any(c in VNI_ONLY for c in text)


def looks_unicode(text: str) -> bool:
    """True when `text` carries a character only real Unicode Vietnamese has."""
    return any(c in UNICODE_ONLY for c in text)


# Modifiers that no Vietnamese Unicode letter can be, sitting where only VNI
# puts them: directly after a vowel. Both halves of that are load-bearing.
#
# The character alone is not proof — `ö ä ü ñ` are everyday German, Nordic and
# Spanish letters, and this kho holds foreign-language citations. `öffentliches`
# and `Acuña` became `ưffentliches` and `Acuđa` under a character-only rule,
# because those letters never follow a vowel there.
#
# The position alone is not proof either — a vowel followed by a *shared* tone
# mark (`oà`, `oá`) is ordinary Vietnamese, the tone landing on the second vowel
# of a cluster, which is what `Toà án`, `hoàn thiện` and `Hoàng` are made of.
# Reading that as VNI turned them into `Tồ án`, `hồn thiện` and `Hồng`.
#
# Requiring both — an exclusive modifier, immediately after a vowel — is what no
# other language and no Unicode Vietnamese produces. `ñ` is deliberately absent:
# it is a standalone letter in VNI, never a modifier, and Spanish `ñ` follows a
# vowel all the time.
_EXCLUSIVE_MODIFIERS = "øûïäåëü"
_VOWELS = "aeiouyAEIOUYôÔöÖ"
_PAIR_RE = re.compile(
    f"[{_VOWELS}][{_EXCLUSIVE_MODIFIERS}{_EXCLUSIVE_MODIFIERS.upper()}]")


def has_vni_evidence(text: str) -> bool:
    """True when `text` contains a sequence only VNI encoding produces.

    This is the gate for changing anything. Once a scope passes it, the whole
    scope is decoded with the full table — the shared letters are only ever
    reinterpreted with that proof standing behind them.
    """
    return bool(_PAIR_RE.search(text))


def _convert_word(word: str) -> str:
    # Word scope is only ever reached inside a line that already proved VNI, so
    # here a bare exclusive letter (`ñaõ`) is evidence enough — the foreign-word
    # worry that rules it out at document level does not apply to a word sitting
    # inside a Vietnamese VNI line. A word with neither is still left alone: it
    # could equally be ordinary Unicode.
    return decode_vni(word) if (has_vni_evidence(word) or looks_vni(word)) else word


def convert_text(text: str) -> str:
    """Decode the VNI parts of `text`, leaving the Unicode parts untouched.

    Widest unambiguous scope wins. A block proven VNI is decoded in one piece,
    which is what lets its shared-letter words (`cô` = `cơ`, `toâi` = `tôi`)
    resolve correctly — alone they carry no evidence at all. Only where a block
    mixes the two encodings does it narrow to lines, and then to words, where
    the standard tightens because the surrounding context no longer vouches.
    """
    if not text:
        return text
    if not has_vni_evidence(text):
        return text                      # nothing here proves VNI -> leave it
    if not looks_unicode(text):
        return decode_vni(text)          # wholly VNI: decode in one piece
    # Mixed: narrow the scope. Lines first, words only where one line still
    # mixes both encodings.
    lines = text.split("\n")
    if len(lines) > 1:
        return "\n".join(convert_text(line) for line in lines)
    return re.sub(r"\S+", lambda m: _convert_word(m.group(0)), text)


def normalize_text(text: str) -> str:
    """Convert VNI, then compose combining marks (NFC).

    PDF extraction sometimes leaves a tone mark as a separate combining
    character; NFC folds `i` + U+0301 back into `í` so search matches it.
    """
    return unicodedata.normalize("NFC", convert_text(text))
