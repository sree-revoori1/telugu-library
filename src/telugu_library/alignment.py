"""Mapping printed tokens to the morphemes that make them up.

Extracted from `bhagavatam` because a second text needed it and a second implementation
would have been a second set of bugs. The Vemana reader shipped without it: every word in
a verse carried the *whole verse's* gloss, so clicking any word listed every morpheme in
all four lines. That is not alignment, it is the absence of it.

The method is the one that finally worked for the Bhāgavatam after three failures, and the
reasons the others failed are worth keeping attached to the code:

  * Counting codepoints ignored that Telugu is an abugida — `జేరుటకునై` is 9 codepoints
    and 5 aksharams, so the arithmetic measured nothing real.
  * Counting aksharams greedily drifted: a greedy choice cannot be revised, so one token
    over-consuming shifted every later token, and clicking a word showed the *next* word's
    breakdown.
  * A global dynamic program over aksharam lengths stopped the cascade but still assumed a
    morpheme fits inside one token, and reached only 78%.

That assumption is false for classical verse, because printing breaks on the metre rather
than the word:

    పరికరస్యందనారూఢుం  డగు        as printed — two tokens
    పరికర స్యందన ఆరూఢుండు అగున్    as the editor separates it — four morphemes

The `డ` opening the second token is the final consonant of `ఆరూఢుండు`. So the two
character streams — the verse with its spaces removed, and the morphemes concatenated —
are aligned with a longest-common-subsequence matcher, and a morpheme is attached to every
token it has characters in. A morpheme spanning a boundary appears under both, which is
what the text actually does.
"""

from __future__ import annotations

import difflib
import re

# An aksharam: a consonant cluster plus its vowel, or a bare vowel. These are the units the
# metre counts and the units sandhi operates on.
AKSHARAM = re.compile(r"[ఀ-౿][ా-్ౖ]*(?:[్][ఀ-౿][ా-ౖ]*)*")


def aksharams(text: str) -> list[str]:
    return AKSHARAM.findall(text)


def is_telugu(character: str) -> bool:
    return "ఀ" <= character <= "౿"


def align_streams(tokens: list[str], forms: list[str]) -> list[list[int]]:
    """For each token, the indices of the morphemes that have characters in it.

    Both arguments are in reading order. The result is one list per token; an index may
    appear under more than one token, which means that morpheme straddles the boundary.
    """
    if not tokens or not forms:
        return [[] for _ in tokens]

    # The printed text as one run of Telugu characters, remembering the token each came
    # from.
    surface: list[str] = []
    token_of: list[int] = []
    for index, token in enumerate(tokens):
        for character in token:
            if is_telugu(character):
                surface.append(character)
                token_of.append(index)

    # The morphemes likewise.
    stream: list[str] = []
    morpheme_of: list[int] = []
    for index, form in enumerate(forms):
        for character in form:
            if is_telugu(character):
                stream.append(character)
                morpheme_of.append(index)

    if not surface or not stream:
        return [[] for _ in tokens]

    matcher = difflib.SequenceMatcher(
        None, "".join(surface), "".join(stream), autojunk=False
    )
    by_token: list[list[int]] = [[] for _ in tokens]
    for surface_start, stream_start, length in matcher.get_matching_blocks():
        for offset in range(length):
            token_index = token_of[surface_start + offset]
            morpheme_index = morpheme_of[stream_start + offset]
            if morpheme_index not in by_token[token_index]:
                by_token[token_index].append(morpheme_index)

    # A morpheme that matched nothing — usually a vowel wholly absorbed by sandhi, such as
    # the `ఐ` in `గంటకుండై` — is placed beside a neighbour so no gloss is lost.
    placed = {index for indices in by_token for index in indices}
    for index in range(len(forms)):
        if index in placed:
            continue
        for token_index, indices in enumerate(by_token):
            if any(neighbour in (index - 1, index + 1) for neighbour in indices):
                by_token[token_index].append(index)
                break

    return [sorted(indices) for indices in by_token]


def shared_indices(by_token: list[list[int]]) -> set[int]:
    """Morphemes appearing under more than one token, i.e. spanning a break."""
    seen: dict[int, int] = {}
    for indices in by_token:
        for index in indices:
            seen[index] = seen.get(index, 0) + 1
    return {index for index, count in seen.items() if count > 1}
