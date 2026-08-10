"""Checking the Vemana glosses against the verses they claim to explain.

Worth having because the gloss here is written by hand rather than parsed, so a typo or a
misremembered form has nothing to catch it. The check asks one question: does every glossed
form actually occur in its verse?

That is harder than string matching, because classical Telugu alters a word at both edges
when it joins the next one, and a naive check reports hundreds of false alarms:

    కలుగు  appears as  గలుగు      గసడదవాదేశ — an initial stop voices after a vowel
    తా      appears as  దా         the same rule
    అతకు   appears as  నతకు       the previous word's final consonant carries over
    అగును  appears as  మగును      likewise

So a form counts as present if the verse contains it, its voiced variant, or its form minus
a leading vowel — which covers the carry-over case, since what remains after the borrowed
consonant is the rest of the morpheme.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANNOTATED = ROOT / "data" / "vemana" / "annotated.json"

# The poet's signature, present in nearly every verse and glossed once.
REFRAIN = {"విశ్వద", "అభిరామ", "వినుర", "వేమ"}

# గసడదవాదేశ: an unvoiced stop at a word's start voices after a preceding vowel.
VOICING = {"క": "గ", "చ": "జ", "ట": "డ", "త": "ద", "ప": "వ"}

VOWELS = "అఆఇఈఉఊఎఏఐఒఓఔ"


# Endings a citation form carries that the printed line may not. The gloss lists the
# dictionary form — `దైవము`, `మరణములు`, `చూడన్` — while the verse writes it inflected or
# elided: `దైవమే`, `మరణములన`, `చూడన`. Trimming these is what lets the check compare a lemma
# against a running line.
CITATION_TAILS = ("ము", "లు", "న్", "ండ్రు", "డు", "ను", "ు", "ి", "్")


# Vowel length and a handful of spellings vary freely between a citation form and a printed
# line: the source writes `గాసీలు` where the lemma is `కాసిలు`, and `జ్ఞానహైన్యము` where the
# dictionary has `జ్ఞానహీన్యము`. Folding length differences lets the check compare the
# consonant skeleton, which is what actually identifies the word.
# Matras fold to matras and independent vowels to independent vowels. Mapping `ా` to `అ`
# would turn a vowel *sign* into a vowel *letter* — different character classes in an
# abugida — and made the check fail on 192 forms instead of 54.
LENGTH_FOLD = str.maketrans({
    "ీ": "ి", "ూ": "ు", "ే": "ె", "ో": "ొ", "ై": "ె", "ౌ": "ొ",
    "ఈ": "ఇ", "ఊ": "ఉ", "ఏ": "ఎ", "ఓ": "ఒ", "ఐ": "ఎ", "ఔ": "ఒ",
})


def skeleton(text: str) -> str:
    """The text with vowel length folded away.

    Length only. Voicing is *not* folded here: it is already handled by `variants`, which
    generates the voiced spelling of a form. Folding it in both places mapped `ప్రొద్దు` to
    `వ్రొద్దు` and then failed to find it in a line that plainly contains it — an error that
    tripled the reported failures.
    """
    return text.translate(LENGTH_FOLD)


def variants(form: str) -> set[str]:
    """Ways `form` may appear in the printed line.

    Three transformations, each a real fact about how classical Telugu is set rather than a
    licence to match anything: the seam may voice the onset, the previous word may have
    taken the onset, and the gloss may give a citation form where the line has an inflected
    one.
    """
    out = {form}
    if form and form[0] in VOICING:
        out.add(VOICING[form[0]] + form[1:])
    # A vowel-initial morpheme loses its onset to the previous word's final consonant,
    # so what survives in the printed line is the remainder.
    if len(form) > 1 and form[0] in VOWELS:
        out.add(form[1:])
    # The stem of a citation form, which is what a running line usually shows.
    for tail in CITATION_TAILS:
        if len(form) > len(tail) + 1 and form.endswith(tail):
            stem = form[: -len(tail)]
            out.add(stem)
            if stem and stem[0] in VOICING:
                out.add(VOICING[stem[0]] + stem[1:])
            if len(stem) > 1 and stem[0] in VOWELS:
                out.add(stem[1:])
    return {v for v in out if len(v) >= 2}


def main() -> int:
    data = json.loads(ANNOTATED.read_text(encoding="utf-8"))
    numbers = sorted(int(k) for k in data)
    gaps = [n for n in range(1, max(numbers) + 1) if n not in numbers]

    unmatched: list[tuple[str, str]] = []
    total = 0
    for key, verse in data.items():
        text = "".join(verse["lines"])
        for form, _ in verse["gloss"]:
            if form in REFRAIN:
                continue
            total += 1
            skeletons = {skeleton(v) for v in variants(form)}
            folded = skeleton(text)
            if not any(s and s in folded for s in skeletons):
                unmatched.append((key, form))

    print(f"verses: {len(numbers)} (1..{max(numbers)}), gaps: {gaps or 'none'}")
    print(f"glossed morphemes: {total}")
    print(f"forms not found in their verse: {len(unmatched)}")
    for key, form in unmatched[:20]:
        print(f"   verse {key}: {form!r}")
    return 1 if unmatched else 0


if __name__ == "__main__":
    sys.exit(main())
