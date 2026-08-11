"""Checking the Sumatī glosses against the verses they claim to explain.

    python3 tools/check_sumati.py

Two questions, not one. The Vemana validator asked only whether every glossed form appears
in its verse, and that let a real gap through: verse 36 there had a printed word (`గమ`)
that no gloss accounted for, so the aligner mapped that token to nothing while the
validator reported a clean run. A missing entry is invisible to a check that only walks the
glosses.

So this asks both:

  1. does every glossed form occur in its verse?  (no invented words)
  2. does every printed token receive a morpheme?  (no unexplained words)

The matching rules are the ones classical Telugu orthography forces, carried over from the
Vemana checker with its corrections already applied:

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

from telugu_library.sumati import load  # noqa: E402

ANNOTATED = ROOT / "data" / "sumati" / "annotated.json"
VERSES = ROOT / "data" / "sumati" / "verses.json"

# గసడదవాదేశ: an unvoiced stop at a word's start voices after a preceding vowel. `ప` has two
# outcomes — `వ` in `ప్రొద్దు` → `వ్రొద్దు`, `బ` in `పట్టు` → `బట్టు`.
VOICING = {"క": "గ", "చ": "జ", "ట": "డ", "త": "ద", "ప": "వ"}
VOICING_ALT = {"ప": "బ", "క": "ఖ"}

VOWELS = "అఆఇఈఉఊఎఏఐఒఓఔ"

# An independent vowel becomes a matra on the preceding consonant when words join, because
# Telugu is an abugida: `కాశివాసులు` + `ఐన` is written `కాశివాసులైన`.
TO_MATRA = {
    "అ": "", "ఆ": "ా", "ఇ": "ి", "ఈ": "ీ", "ఉ": "ు", "ఊ": "ూ",
    "ఎ": "ె", "ఏ": "ే", "ఐ": "ై", "ఒ": "ొ", "ఓ": "ో", "ఔ": "ౌ",
}

# Endings a citation form carries that the printed line may not.
CITATION_TAILS = ("ము", "లు", "న్", "ండ్రు", "డు", "ను", "ు", "ి", "్")

# Vowel length varies freely between a citation form and a printed line. Matras fold to
# matras and letters to letters: mapping `ా` to `అ` would turn a vowel *sign* into a vowel
# *letter*, which are different character classes in an abugida.
LENGTH_FOLD = str.maketrans({
    "ీ": "ి", "ూ": "ు", "ే": "ె", "ో": "ొ", "ై": "ె", "ౌ": "ొ",
    "ఈ": "ఇ", "ఊ": "ఉ", "ఏ": "ఎ", "ఓ": "ఒ", "ఐ": "ఎ", "ఔ": "ఒ",
})


def skeleton(text: str) -> str:
    """The text with vowel length folded away. Length only — voicing is in `variants`."""
    return text.translate(LENGTH_FOLD)


def variants(form: str) -> set[str]:
    """Ways `form` may appear in the printed line."""
    out = {form}
    if form and form[0] in VOICING:
        out.add(VOICING[form[0]] + form[1:])
    if form and form[0] in VOICING_ALT:
        out.add(VOICING_ALT[form[0]] + form[1:])
    if len(form) > 1 and form[0] in VOWELS:
        out.add(form[1:])
        out.add(TO_MATRA[form[0]] + form[1:])
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


def main() -> int:
    data = json.loads(ANNOTATED.read_text(encoding="utf-8"))
    total_verses = len(json.loads(VERSES.read_text(encoding="utf-8")))
    numbers = sorted(int(k) for k in data)
    missing = [n for n in range(1, total_verses + 1) if n not in numbers]

    unmatched: list[tuple[str, str]] = []
    glossed = 0
    for key, verse in data.items():
        # Spaces stripped as well as line breaks: printing breaks on the metre, so one word
        # is routinely set as two.
        text = skeleton("".join("".join(verse["lines"]).split()))
        for form, _ in verse["gloss"]:
            glossed += 1
            if not any(s and s in text for s in {skeleton(v) for v in variants(form)}):
                unmatched.append((key, form))

    # The other direction, which the Vemana checker lacked: a printed token that no gloss
    # explains. Uses the real aligner, so this is the same mapping the reader sees.
    orphans: list[tuple[int, str]] = []
    tokens = 0
    for verse in load():
        for _, token, morphemes in verse.alignment:
            tokens += 1
            if not morphemes:
                orphans.append((verse.number, token))

    print(f"verses: {len(numbers)} of {total_verses}"
          f"{'' if not missing else f', missing {missing[:12]}'}")
    print(f"glossed morphemes: {glossed}")
    print(f"printed tokens: {tokens}")
    print(f"forms not found in their verse: {len(unmatched)}")
    for key, form in unmatched[:40]:
        print(f"   verse {key}: {form!r}")
    print(f"printed tokens with no gloss: {len(orphans)}")
    for number, token in orphans[:40]:
        print(f"   verse {number}: {token!r}")
    return 1 if (unmatched or orphans) else 0


if __name__ == "__main__":
    sys.exit(main())
