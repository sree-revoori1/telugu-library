"""Telling Telugu from Sanskrit written in Telugu script.

The single most important thing discovered while building this. Telugu Wikisource's
`ఇతిహాసాలు` (epics) category is dominated not by the Telugu Rāmāyaṇam but by the
**Vālmīki Rāmāyaṇam — Sanskrit, transliterated into Telugu script**. Of 381 cached
texts over 800 characters, only 40 are Telugu by the test below.

That mattered because it was silently corrupting the whole project. A Telugu
morphological analyser cannot parse Sanskrit, so those texts dragged reported coverage
down; worse, where it *did* produce something the gloss was nonsense — `సూర్యే`, the
Sanskrit locative of "sun", came back as a habitual participle of an invented Telugu
verb `సూర్యు`. Offering that to a reader is worse than offering nothing.

The test is word endings, because that is where the two languages differ most visibly
and most mechanically. Sanskrit's case system ends words in ways Telugu never does:

    ః        visarga            సర్గః, తతః
    ్        bare consonant     తస్మాత్, తస్మిన్
    ౌ        dual               వృక్షౌ
    స్య      genitive           రామస్య
    ేన       instrumental       రామేణ → రామేన

Telugu words end in a vowel, `-ం` or `-ము`. So the share of tokens with a Sanskrit
ending separates the two cleanly: real Telugu sits under 10%, and Sanskrit texts cluster
around 25–32%.

This is not a judgement about which text is worth reading. The Vālmīki Rāmāyaṇam matters
enormously — it simply needs a Sanskrit analyser, which this project does not have, so it
is presented as text without glosses rather than with wrong ones.
"""

from __future__ import annotations

import re

TELUGU_RUN = re.compile(r"[ఀ-౥౰-౿]+")

# Word endings that occur in Sanskrit and effectively never in Telugu. A Telugu word
# ends in a vowel, an anusvara or `-ము`; a bare consonant or a visarga at the end of a
# word is a Sanskrit case ending.
SANSKRIT_ENDINGS: tuple[str, ...] = (
    "ః",      # visarga
    "్",      # a word ending in a dead consonant
    "ౌ",      # the dual
    "స్య",   # genitive singular
    "ేన",    # instrumental
    "ేషు",   # locative plural
    "ాయ",    # dative
    "ాత్",   # ablative
    "ిన్",   # locative
)

# Above this share of Sanskrit-ending tokens, a text is Sanskrit. Measured rather than
# guessed: across 381 texts the distribution is strongly bimodal, with Telugu under 10%
# and Sanskrit clustering at 21–32% (median 25%). Ten per cent sits in the empty gap
# between them, so the exact value is not delicate.
SANSKRIT_THRESHOLD = 0.10

# Below this length the ending share is too noisy to judge — a four-word title can hit
# any ratio — so a short text is taken at face value.
MIN_LENGTH = 400


def sanskrit_share(text: str) -> float:
    """The fraction of tokens ending the way Sanskrit does and Telugu does not."""
    words = TELUGU_RUN.findall(text)
    if not words:
        return 0.0
    return sum(1 for w in words if w.endswith(SANSKRIT_ENDINGS)) / len(words)


def is_sanskrit(text: str, threshold: float = SANSKRIT_THRESHOLD) -> bool:
    """Whether a text is Sanskrit written in Telugu script."""
    if len(text) < MIN_LENGTH:
        return False
    return sanskrit_share(text) > threshold


def language_of(text: str) -> str:
    """`"sanskrit"` or `"telugu"`, for labelling a page."""
    return "sanskrit" if is_sanskrit(text) else "telugu"
