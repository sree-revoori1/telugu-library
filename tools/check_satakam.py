"""Checking a śatakam's glosses against the verses they claim to explain.

    python3 tools/check_satakam.py            # every śatakam
    python3 tools/check_satakam.py dasarathi  # one

Two questions, because one is not enough:

  1. does every glossed form occur in its verse?  (no invented words)
  2. does every printed token receive a morpheme?  (no unexplained words)

Question 2 is the one that catches real gaps, and it is the one the first version of this
check lacked: Vemana's verse 36 had a printed word no gloss accounted for and the checker
reported a clean run for weeks. It runs through the real aligner, so it tests the mapping
the reader actually sees.

The matching rules are what classical Telugu orthography forces:

    కలుగు  appears as  గలుగు      గసడదవాదేశ — an initial stop voices after a vowel
    పట్టు   appears as  బట్టు      …and `ప` goes to `బ` as well as to `వ`
    అతకు   appears as  నతకు       the previous word's final consonant carries over
    ఐన     appears as  ైన         …or the vowel survives only as a matra
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from telugu_library import dasarathi, sumati, vemana  # noqa: E402

VOICING = {"క": "గ", "చ": "జ", "ట": "డ", "త": "ద", "ప": "వ"}
VOICING_ALT = {"ప": "బ", "క": "ఖ", "చ": "స"}

VOWELS = "అఆఇఈఉఊఎఏఐఒఓఔ"

TO_MATRA = {
    "అ": "", "ఆ": "ా", "ఇ": "ి", "ఈ": "ీ", "ఉ": "ు", "ఊ": "ూ",
    "ఎ": "ె", "ఏ": "ే", "ఐ": "ై", "ఒ": "ొ", "ఓ": "ో", "ఔ": "ౌ",
}

# Guṇa: a preceding `అ` absorbs this word's initial vowel into a single matra, so
# `కుల` + `ఈశ` is set `కులేశ` and `పర` + `దేవత` needs no change while `ఇ`/`ఈ` → `ే` and
# `ఉ`/`ఊ` → `ో`. Only the *replacement* matra is generated, since the word's own first
# letter has vanished from the line.
GUNA = {"ఇ": "ే", "ఈ": "ే", "ఉ": "ో", "ఊ": "ో", "ఋ": "ార్", "ఎ": "ై", "ఏ": "ై"}

CITATION_TAILS = ("ము", "లు", "న్", "ండ్రు", "డు", "ను", "ు", "ి", "్")

# Matras fold to matras and letters to letters: mapping `ా` to `అ` would turn a vowel sign
# into a vowel letter, which are different character classes in an abugida.
LENGTH_FOLD = str.maketrans({
    "ీ": "ి", "ూ": "ు", "ే": "ె", "ో": "ొ", "ై": "ె", "ౌ": "ొ",
    "ఈ": "ఇ", "ఊ": "ఉ", "ఏ": "ఎ", "ఓ": "ఒ", "ఐ": "ఎ", "ఔ": "ఒ",
})

# Classical orthography writes a nasal as arasunna where modern writing uses anusvara, and
# the sources here mix them freely. Folded so `వాఁడె` matches `వాడె`.
NASAL_FOLD = str.maketrans({"ఁ": "ం", "ँ": "ం"})

# The hyphen in the Dāśarathī source marks the *yati* caesura, and it falls wherever the
# metre demands — including inside a word. Verse 1 sets `త్రిజగత్` as `త్రిజ-గన్నుత`. It is
# not punctuation and must be removed before matching, not treated as a boundary.
YATI = "-"

# Sanskrit sandhi at a compound seam, which is where this text differs in kind from Vemana
# and Sumatī. A stem-final consonant voices and fuses with the next word's initial:
#
#     రంగత్ + అరాతి   → రంగదరాతి      (త్ → ద)
#     పూతకృత్ + గగన   → పూతకృద్గగన    (త్ → ద్)
#     లసత్ + ఝరీ      → లసజ్ఘరీ       (త్ → జ్, and ఝ → ఘ)
#
# So a form ending in a bare consonant may appear with that consonant voiced, or absent
# where it has merged into the following cluster. Both are generated rather than the check
# being loosened to a prefix match, which would accept anything.
FINAL_VOICING = {"త": "ద", "క": "గ", "ప": "బ", "ట": "డ", "చ": "జ"}

# Vowel sandhi at the same seam. A stem-final ఆ/ా absorbs a following ఉ into ఓ —
# `పరంపరా` + `ఉత్తుంగ` → `పరంపరోత్తుంగ` — so the stem survives with its last vowel changed.
# Generated per form rather than folded globally, since ా and ో are distinct elsewhere.
SEAM_VOWELS = {"ా": ("ో", "ె", "ై", ""), "ీ": ("ె", "ి", ""), "ూ": ("ొ", "ు", "")}


def skeleton(text: str) -> str:
    """Vowel length and nasal notation folded away. Voicing is handled by `variants`."""
    return text.translate(LENGTH_FOLD).translate(NASAL_FOLD)


def variants(form: str) -> set[str]:
    out = {form}
    # A Sanskrit stem ending in a bare consonant (`త్రిజగత్`, `లసత్`, `పూతకృత్`) loses or
    # voices that consonant at the seam.
    if len(form) > 1 and form[-1] in SEAM_VOWELS:
        for replacement in SEAM_VOWELS[form[-1]]:
            out.add(form[:-1] + replacement)
    if len(form) > 2 and form.endswith("్"):
        body, last = form[:-2], form[-2]
        out.add(body)
        if last in FINAL_VOICING:
            out.add(body + FINAL_VOICING[last])
            out.add(body + FINAL_VOICING[last] + "్")
    if form and form[0] in VOICING:
        out.add(VOICING[form[0]] + form[1:])
    if form and form[0] in VOICING_ALT:
        out.add(VOICING_ALT[form[0]] + form[1:])
    if len(form) > 1 and form[0] in VOWELS:
        out.add(form[1:])
        out.add(TO_MATRA[form[0]] + form[1:])
        if form[0] in GUNA:
            out.add(GUNA[form[0]] + form[1:])
    for tail in CITATION_TAILS:
        if len(form) > len(tail) + 1 and form.endswith(tail):
            stem = form[: -len(tail)]
            out.add(stem)
            if stem and stem[0] in VOICING:
                out.add(VOICING[stem[0]] + stem[1:])
            if stem and stem[0] in VOICING_ALT:
                out.add(VOICING_ALT[stem[0]] + stem[1:])
            if len(stem) > 1 and stem[0] in VOWELS:
                out.add(stem[1:])
                out.add(TO_MATRA[stem[0]] + stem[1:])
    return {v for v in out if len(v) >= 2}


TEXTS = {"vemana": vemana, "sumati": sumati, "dasarathi": dasarathi}


def check(module) -> int:
    text = module.load()
    verses = text.verses if hasattr(text, "verses") else text
    name = getattr(text, "title", module.TITLE)
    raw = json.loads(
        (ROOT / "data" / module.NAME / "verses.json").read_text(encoding="utf-8")
    ) if hasattr(module, "NAME") else {}

    unmatched = []
    glossed = 0
    for verse in verses:
        # Spaces stripped as well as line breaks: these metres break on the syllable count,
        # so one word is routinely set as two.
        folded = skeleton(
            "".join("".join(verse.lines).split()).replace(YATI, "")
        )
        for morpheme in verse.morphemes:
            glossed += 1
            if not any(
                s and s in folded for s in {skeleton(v) for v in variants(morpheme.form)}
            ):
                unmatched.append((verse.number, morpheme.form))

    orphans = [
        (v.number, token)
        for v in verses
        for _, token, morphemes in v.alignment
        if not morphemes
    ]
    tokens = sum(len(v.alignment) for v in verses)

    print(f"=== {name}")
    if raw:
        missing = [n for n in range(1, len(raw) + 1) if str(n) not in
                   {str(v.number) for v in verses}]
        print(f"  verses: {len(verses)} of {len(raw)}"
              f"{'' if not missing else f', missing {missing[:12]}'}")
    else:
        print(f"  verses: {len(verses)}")
    print(f"  glossed morphemes: {glossed}")
    print(f"  printed tokens: {tokens}")
    print(f"  forms not found in their verse: {len(unmatched)}")
    for number, form in unmatched[:40]:
        print(f"     verse {number}: {form!r}")
    print(f"  printed tokens with no gloss: {len(orphans)}")
    for number, token in orphans[:40]:
        print(f"     verse {number}: {token!r}")
    return 1 if (unmatched or orphans) else 0


def main(argv: list[str]) -> int:
    wanted = argv[1:] or list(TEXTS)
    status = 0
    for key in wanted:
        if key not in TEXTS:
            print(f"unknown text {key!r}; known: {', '.join(TEXTS)}")
            return 2
        status |= check(TEXTS[key])
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv))
