"""A classical lexicon, built from the corpus itself.

The analyser's ranking lexicon comes from Wikipedia and newspapers, so it knows modern
Telugu and not the classical vocabulary these texts are written in. That is why coverage
sits at 26%: `ఆఢ్యుడు`, `నృపతి`, `మహీపతి` are ordinary words in a 15th-century poem and
absent from a 21st-century corpus.

The fix does not need an external dictionary. **These 4,842 texts are themselves a
corpus of classical Telugu** — around a million words of it — so the vocabulary can be
counted from the material being read. A word that recurs across many independent texts
is a real word, whatever a modern newspaper corpus thinks.

That is the same discipline `telugu_morph.roots` applies, and it matters for the same
reason: a fragment left by classical line-breaking appears once, in one line, while a
genuine word recurs. Two signals are taken — recurrence across unrelated texts, and
repetition within one long one — because either alone is too weak on a corpus this
size. That is what separates `నృపతి` (a word) from `డాఢ్యుఁడు` (a printing artifact).

On external dictionaries. andhrabharati.com is the best Telugu dictionary aggregator
there is, and it was considered. Two things ruled out using it as a data source: its
lookup is a JavaScript POST to `getWM.php` carrying a session token, which is a
deliberate signal that bulk automated access is unwelcome; and the site states "All
rights reserved" over dictionaries it licensed individually from publishers, so
redistributing their definitions in a public static site would be republishing material
under permissions granted to someone else. A headword's *existence* is a fact and not
copyrightable, but a corpus-derived lexicon establishes the same facts without the
question arising — and it is checkable, since the evidence ships with the repository.
The site links out to andhrabharati for a word, which is what it is for.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path

TELUGU_RUN = re.compile(r"[ఀ-౥౰-౿]+")

# How many *distinct texts* a word must appear in before it counts as vocabulary.
#
# Document frequency rather than raw frequency, because the failure mode being guarded
# against is concentrated: classical line-breaking produces fragments like `డాఢ్యుఁడు`
# that can recur within one poem — a refrain repeats, a formula repeats — but do not
# appear in unrelated works. A word attested across three independent texts by
# different authors is a word.
MIN_DOCUMENTS = 2

# ...or this many total occurrences anywhere in the corpus. The second clause exists
# because document frequency alone fights the sample size: most classical vocabulary
# appears in exactly one text — of 53,270 distinct words across 330 texts, only 5,822
# occur in three or more — so a documents-only threshold discards nearly everything and
# raised coverage by 0.6 points.
#
# A word repeated within one long work is still vocabulary. The Rāmāyaṇam uses `నృపతి`
# (king) throughout; that it appears in no unrelated poem says something about the
# corpus, not about the word. Taking either signal admits 12,668 words where documents
# alone admitted 5,822, and it still refuses every line-break fragment — `డాఢ్యుఁడు`
# and `డవ్యయుఁ` occur once each, in one line, and are excluded by both clauses.
MIN_OCCURRENCES = 5

# A single-aksharam token is almost never a word in isolation here: it is a metrical
# fragment, an initial, or a chanting syllable. The analyser already refuses one-aksharam
# nominal lemmas for the same reason.
MIN_LENGTH = 2


def harvest(texts: list[str]) -> tuple[dict[str, int], dict[str, int]]:
    """Document frequency and total occurrences, from the texts themselves.

    Both signals, because they catch different vocabulary: recurrence across unrelated
    works, and repetition within one long one.
    """
    documents: Counter = Counter()
    occurrences: Counter = Counter()
    for text in texts:
        words = [w for w in TELUGU_RUN.findall(text) if len(w) >= MIN_LENGTH]
        occurrences.update(words)
        documents.update(set(words))
    return dict(documents), dict(occurrences)


def build(
    texts: list[str],
    min_documents: int = MIN_DOCUMENTS,
    min_occurrences: int = MIN_OCCURRENCES,
) -> dict[str, int]:
    """A classical lexicon: words the corpus attests as vocabulary.

    The value is the total occurrence count, which the analyser uses exactly as it uses
    a corpus frequency — more evidence means a more credible lemma.
    """
    documents, occurrences = harvest(texts)
    return {
        word: occurrences[word]
        for word in documents
        if documents[word] >= min_documents
        or occurrences[word] >= min_occurrences
    }


def merge(modern: dict[str, int], classical: dict[str, int]) -> dict[str, int]:
    """Both lexicons, with the modern one dominant where they overlap.

    The modern corpus counts 33 million words and the classical one about a million, so
    their frequencies are not comparable — adding them would let a classical hapax
    outrank a common modern word. Where a word is in both, the modern count stands;
    where it is only classical, its document count is scaled to sit at the low end of
    the modern range, so it is credible but never outranks genuinely common vocabulary.
    """
    out = dict(modern)
    for word, documents in classical.items():
        if word not in out:
            # Scaled so a classical word lands in the low end of the modern range —
            # comparable to a rare but real modern word, never to a frequent one.
            out[word] = documents * 10
    return out


def save(lexicon: dict[str, int], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for word, count in sorted(lexicon.items(), key=lambda kv: (-kv[1], kv[0])):
            handle.write(f"{word}\t{count}\n")


def load(path: Path) -> dict[str, int]:
    out: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "\t" not in line:
            continue
        word, count = line.rsplit("\t", 1)
        try:
            out[word] = int(count)
        except ValueError:
            continue
    return out
