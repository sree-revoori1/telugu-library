"""The Dāśarathī Śatakam, with a word-by-word analysis written for this library.

Kancherla Gopanna — Bhakta Rāmadāsu, 17th century — writing to Rāma at Bhadrāchalam. The
hardest of the three śatakams here by a distance, and for two reasons a reader feels
immediately:

  * It is *utpalamāla* and *campakamāla*, long metres in which a word routinely breaks
    across the line end: verse 1 sets `శృంగార` as `…శృం` / `గార…`. The gloss therefore
    lists whole words, and the character-stream aligner attaches a split word to both
    printed tokens.
  * It is far more Sanskritised than Vemana or Sumatī, and built on long compounds:
    `కల్మషార్నవోత్తారకనామ` is `కల్మష` + `అర్ణవ` + `ఉత్తారక` + `నామ` — "the name that
    ferries one across the ocean of sin". Splitting those is the whole value of the gloss,
    since no dictionary lists the compound.

The refrain is `దాశరథీ కరుణాపయోనిధీ` — "O son of Daśaratha, ocean of compassion" — two
vocatives, the second a compound worth splitting. Verse 63 spells the first `దాసరథీ` with
స for శ; that is the source's, and it is quoted rather than corrected.
"""

from __future__ import annotations

from . import satakam

NAME = "dasarathi"
TITLE = "దాశరథీ శతకము"
SLUG = "dasarathi-satakam"

# Both vocatives, and the compound's parts, so the closing address is not re-glossed as
# though new in all 104 verses.
REFRAIN_WORDS = frozenset({"దాశరథీ", "దాసరథీ", "కరుణా", "పయోనిధీ", "కరుణాపయోనిధీ"})

PROVENANCE = (
    "the word-by-word analysis here is this project's own, not a scholar's — "
    "no published ప్రతిపదార్థము of the Dāśarathī Śatakam exists online"
)


def load() -> satakam.Satakam:
    return satakam.load(NAME, TITLE, SLUG, PROVENANCE, REFRAIN_WORDS)
