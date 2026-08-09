"""Parsing Pothana's Bhāgavatam, which arrives already glossed.

The single most useful discovery in this project. Telugu Wikisource's Bhāgavatam pages
are not bare text — each verse carries an editorial word-by-word gloss, introduced by
`టీక:-` and written as semicolon-separated `word = meaning` pairs:

    తెభా-1-1-శా.శ్రీ కైవల్య పదంబుఁ జేరుటకునై …
    టీక:- శ్రీ = శుభకర మైన; కైవల్య = ముక్తి; పదంబున్ = స్థితిని;
          చేరుట = పొందుట; కున్ = కోసము; ఐ = ఐ; …

That gloss solves precisely the problem the morphological analyser could not. Classical
verse fuses words across the line and breaks on the metrical foot, so `చేరుటకునై` is one
printed token standing for four morphemes — and the editor has already separated them:
`చేరుట` + `కున్` + `ఐ`. No amount of sandhi reversal was going to recover that reliably,
and here it is, done by someone who knows the text.

So the pipeline is:

  1. Split the page into verses on the `తెభా-<skandham>-<verse>-<metre>.` marker.
  2. Take the verse text and its `టీక:-` gloss.
  3. Align the gloss's morphemes to the printed tokens, which is the interesting part —
     the gloss is in reading order, so it can be walked against the surface string.
  4. Confirm each morpheme against andhrabharati for part of speech and etymology.

Steps 1–3 need no network and no guessing. Step 4 is where the dictionary earns its
place: the gloss says *what a morpheme means* but not *what it is grammatically*, and
that is what andhrabharati supplies.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

# The verse id: abbreviation, skandham, verse number, metre.
#
# Two formats occur in the source and both must be read:
#
#     తెభా-1-1-శా.     number and metre joined by a hyphen
#     తెభా-1-34.శా.    number and metre joined by a period
#
#     తెభా-10.1-1518-ఉ.  a *skandham* sub-number: tenth book, first āśvāsam
#     తెభా-1-189-సీ.   a sīsa verse
#     తెభా-1-189.1-ఆ.  its āṭaveladi companion, sub-numbered
#
# The last is the one that mattered. Classical Telugu sets a sīsa padyam together with a
# following āṭaveladi as a single unit, and the source numbers the second `189.1`. An
# earlier pattern read the separator too eagerly and paired that continuation with the
# wrong verse — so a verse of 12 tokens was handed a 50-morpheme gloss belonging to two
# verses at once. Almost nothing in it could align, and that was the entire "morphemes
# never placed" figure. The metre is also required to be Telugu letters, which is what
# distinguishes a real id from a decimal.
#
# The skandham may be sub-numbered too, and missing that silently lost two whole books.
# Pothana's fifth and tenth skandhams are long enough to be split into two āśvāsams, and
# the source numbers them `5.1`/`5.2` and `10.1`/`10.2`. A pattern allowing only digits
# there matched nothing on 399 pages of the tenth skandham — a third of the whole work —
# and the build reported success while skipping it.
VERSE_ID = re.compile(r"తెభా-(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)[.-]([ఀ-౿]{1,6})\.")

# The editorial gloss, which runs to the end of the verse block.
GLOSS_MARKER = "టీక:-"

# The whole-verse prose paraphrase, which follows the morpheme gloss. A third editorial
# layer, and the one a reader who wants the *sense* of a verse actually reads. It must be
# split off explicitly: without this it was silently swallowed into the last morpheme's
# meaning, so `సేసి = చేసి` came out carrying an entire paragraph.
PARAPHRASE_MARKER = "భావము:-"

# Metre abbreviations used in the verse id, expanded for display. These are the classical
# Telugu metres; naming them is part of what a reader of poetry wants.
METRES: dict[str, str] = {
    "శా": "śārdūlam",
    "మ": "mattēbham",
    "ఉ": "utpalamāla",
    "చ": "campakamāla",
    "క": "kanda",
    "కం": "kanda",
    "ఆ": "āṭavelaḍi",
    "తే": "tētagīti",
    "సీ": "sīsa",
    "వ": "vacanam",
    "ద్వి": "dvipada",
    "మత్త": "mattakōkila",
    "ఉత్సా": "utsāham",
}


# Bound morphemes — case endings, verb endings and clitics — which the editor separates
# out but no dictionary lists as a headword. They must be recognised here or every one
# counts as an unconfirmed gap, and worse, a stray match in a non-Telugu dictionary can
# label the dative `కున్` a noun.
#
# This is a closed list because Telugu's inflectional inventory is closed. It is also
# exactly what `telugu-morph` knows, so the two agree by construction rather than by
# coincidence.
SUFFIXES: frozenset[str] = frozenset({
    # Case
    "కున్", "కు", "కిన్", "కి", "ను", "న్", "ని", "తోన్", "తో", "చేన్", "చే",
    "లోన్", "లో", "వలన్", "వలన", "కై", "కొఱకు", "యందు", "అందున్", "అందు",
    # Number
    "లు", "లన్", "ల", "ులు", "ుల",
    # Verbal
    "ఎదన్", "ఎద", "ఏను", "ఏను.", "తిని", "తిమి", "ెను", "ెన్", "ిరి", "ినన్",
    "ుచు", "ుచున్", "ఇ", "ఐ", "అని", "గా", "గన్",
    # Particles and clitics
    "ఉన్", "ఉ", "ఏ", "ఓ", "కూడ", "ఐనన్", "ఐన", "అయి",
})


@dataclass
class Morpheme:
    """One morpheme of a verse, as the editor separated it."""

    form: str
    # The editor's Telugu gloss. Their words, so it is quoted and attributed rather than
    # rewritten.
    gloss: str
    # Filled in from andhrabharati where it can be.
    pos: str | None = None
    etymology: str | None = None
    english: str | None = None
    in_dictionary: bool = False

    @property
    def is_suffix(self) -> bool:
        return self.form in SUFFIXES

    @property
    def accounted(self) -> bool:
        """Whether this morpheme is explained, by either kind of evidence.

        Two sources, each authoritative for what it is good at. A dictionary knows
        lexical words and says nothing useful about bound morphemes; the closed
        inflectional inventory knows the suffixes exactly. A morpheme is accounted for if
        either identifies it — and the editor's gloss covers all of them regardless, so
        this measures how much can be *labelled grammatically*, not how much is
        understood.
        """
        return self.in_dictionary or self.is_suffix


@dataclass
class Verse:
    """One verse: its identity, its text as printed, and its morphemes."""

    # A string, not an integer: a long book is split into āśvāsams and numbered `10.1`.
    skandham: str
    number: str
    metre: str
    text: str
    # The editor's prose paraphrase of the whole verse — the `భావము`. Quoted, not
    # rewritten: it is their scholarship and it is what makes the verse comprehensible.
    paraphrase: str = ""
    morphemes: list[Morpheme] = field(default_factory=list)
    # Printed token → the morphemes inside it, filled by `align`.
    alignment: list = field(default_factory=list)

    @property
    def reference(self) -> str:
        """The citable reference, as a scholar would write it."""
        return f"{self.skandham}-{self.number}"

    @property
    def metre_name(self) -> str:
        return METRES.get(self.metre, self.metre)

    @property
    def glossed(self) -> int:
        return sum(1 for m in self.morphemes if m.gloss)

    @property
    def confirmed(self) -> int:
        """Morphemes with a grammatical label, from a dictionary or the suffix list."""
        return sum(1 for m in self.morphemes if m.accounted)


def split_gloss(block: str) -> list[tuple[str, str]]:
    """The `word = meaning; word = meaning` pairs of one `టీక:-` block.

    Kept in the editor's order, because that order is the reading order of the verse and
    is what makes alignment to the printed text possible.
    """
    pairs: list[tuple[str, str]] = []
    for chunk in block.split(";"):
        if "=" not in chunk:
            continue
        form, gloss = chunk.split("=", 1)
        form = form.strip().strip(".,")
        gloss = " ".join(gloss.split()).strip()
        # A gloss entry occasionally carries a trailing editorial note in parentheses;
        # the form itself never does.
        if form and not form.startswith("("):
            pairs.append((form, gloss))
    return pairs


def parse_page(text: str, glossed_only: bool = True) -> list[Verse]:
    """Every verse on a Bhāgavatam page, with its morphemes.

    By default only verses carrying an editorial `టీక` gloss are returned. 530 of the
    first skandham's 577 verses have one; the remaining 47 have no gloss block at all, so
    there is nothing to annotate and showing them would put unexplained text beside
    explained text with no way to tell why. They are skipped rather than shown bare.

    The page is one long string in which verses are delimited only by their id marker, so
    the split is on that marker and each piece is one verse plus its gloss.
    """
    verses: list[Verse] = []
    # A verse awaiting its gloss, which may be on the following id.
    pending: Verse | None = None
    matches = list(VERSE_ID.finditer(text))
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[start:end]

        if GLOSS_MARKER in body:
            surface, _, rest = body.partition(GLOSS_MARKER)
        else:
            surface, rest = body, ""
        gloss_block, _, paraphrase = rest.partition(PARAPHRASE_MARKER)

        verse = Verse(
            skandham=match.group(1),
            number=match.group(2),
            metre=match.group(3),
            text=" ".join(surface.split()),
            paraphrase=" ".join(paraphrase.split()),
        )
        verse.morphemes = [
            Morpheme(form=form, gloss=gloss)
            for form, gloss in split_gloss(gloss_block)
        ]
        # A sīsa padyam and its āṭaveladi companion are one literary unit, and the source
        # writes them as two ids — `తెభా-1-34-సీ.` then `తెభా-1-34.1-ఆ.`. Only the second
        # carries a `టీక`, and that gloss covers *both* halves.
        #
        # So they are merged. Treating them as separate verses was the whole of the 6.2%
        # "morphemes never placed": the sīsa half was dropped for having no gloss of its
        # own, and the continuation was handed a gloss twice the length of its text, so
        # most of it could not possibly align. Verse 1-34 vanished from the output
        # entirely while 1-34.1 carried a 52-morpheme gloss for a 12-token line.
        if "." in verse.number and pending is not None:
            base = verse.number.split(".")[0]
            if pending.number == base:
                pending.text = (pending.text + " " + verse.text).strip()
                pending.morphemes = verse.morphemes
                pending.paraphrase = verse.paraphrase or pending.paraphrase
                verses.append(pending)
                pending = None
                continue

        # An unglossed verse is held rather than dropped, because its gloss may be
        # arriving in the next id — a sīsa's `టీక` lives on its āṭaveladi continuation.
        # Dropping it immediately meant the continuation looked for a predecessor that had
        # already been discarded, so the merge never fired and the sīsa was lost.
        if pending is not None and not glossed_only:
            verses.append(pending)
        pending = None

        if not verse.morphemes:
            pending = verse
            continue
        verses.append(verse)

    if pending is not None and not glossed_only:
        verses.append(pending)
    return verses


def confirm(verses: list[Verse], lookup=None, limit: int | None = None) -> dict:
    """Confirms each distinct morpheme against andhrabharati.

    One lookup per distinct form across the whole text, not per occurrence — the same
    morphemes recur constantly, and the dictionary should be asked once. Returns a
    summary so the caller can report coverage honestly.
    """
    if lookup is None:
        from .andhrabharati import cached as lookup

    forms: dict[str, list[Morpheme]] = {}
    for verse in verses:
        for morpheme in verse.morphemes:
            forms.setdefault(morpheme.form, []).append(morpheme)

    # Suffixes are settled by the closed inventory, so they are never looked up. That is
    # both correct and a large saving: they are the commonest morphemes in the text.
    ordered = sorted(
        (f for f in forms if f not in SUFFIXES), key=lambda f: -len(forms[f])
    )
    if limit:
        ordered = ordered[:limit]

    found = 0
    blocked = False
    for form in ordered:
        if blocked:
            break
        try:
            result = lookup(form)
        except Exception as error:
            # A refusal stops the whole pass rather than retrying word by word. The
            # annotation does not depend on the dictionary — the editorial gloss already
            # covers every morpheme — so the right response is to carry on without it,
            # not to hammer a service that has said no.
            if type(error).__name__ == "Blocked":
                blocked = True
                continue
            raise
        if not result.found:
            continue
        found += 1
        for morpheme in forms[form]:
            morpheme.in_dictionary = True
            morpheme.pos = result.pos
            morpheme.etymology = result.etymology
            morpheme.english = result.english

    total_morphemes = sum(len(v.morphemes) for v in verses)
    accounted = sum(v.confirmed for v in verses)
    return {
        "dictionary_blocked": blocked,
        "verses": len(verses),
        "morphemes": total_morphemes,
        "distinct_forms": len(forms),
        "looked_up": len(ordered),
        "in_dictionary": found,
        "glossed_pct": (
            100.0 * sum(v.glossed for v in verses) / total_morphemes
            if total_morphemes
            else 0.0
        ),
        "labelled_pct": (
            100.0 * accounted / total_morphemes if total_morphemes else 0.0
        ),
    }


# An aksharam: a consonant cluster plus its vowel, or a bare vowel. Alignment counts in
# these because they are the units the metre counts and the units sandhi operates on.
AKSHARAM = re.compile(r"[ఀ-౿][ా-్ౖ]*(?:[్][ఀ-౿][ా-ౖ]*)*")


def aksharams(text: str) -> list[str]:
    return AKSHARAM.findall(text)


def align(verse: Verse) -> list[tuple[str, list[Morpheme]]]:
    """Maps each printed token of the verse to the morphemes that make it up.

    Done by aligning the two **character streams** — the verse with its spaces removed,
    and the editor's morphemes concatenated — and letting a standard longest-common-
    subsequence matcher decide the correspondence. The streams are 88% identical, because
    sandhi changes only the seams, so almost every character has an obvious counterpart.

    This is the fourth approach and the first correct one. The three that failed all shared
    a mistake: they tried to assign whole morphemes to whole tokens by *counting*.

      * Counting codepoints ignored that Telugu is an abugida — `జేరుటకునై` is 9 codepoints
        and 5 aksharams, so the arithmetic measured nothing real.
      * Counting aksharams greedily drifted, since a greedy choice cannot be revised: one
        token over-consuming shifted every later token, and a reader clicking a word saw
        the next word's breakdown.
      * A global dynamic program over aksharam lengths fixed the cascade but still assumed
        morphemes fit inside tokens, so it reached only 78% agreement.

    That assumption is simply false. Classical printing breaks lines on the metre, not the
    word, so a morpheme routinely straddles two tokens:

        పరికరస్యందనారూఢుం  డగు        as printed
        పరికర స్యందన ఆరూఢుండు అగున్    as the editor separates it

    The `డ` opening the second token is the final consonant of `ఆరూఢుండు`. Character
    alignment represents that directly — `ఆరూఢుండు` simply matches characters in both
    tokens — where any whole-morpheme assignment has to choose one and be wrong.

    A morpheme is attached to every token it has characters in, so a straddling morpheme
    appears under both. That is the truth about the text rather than a compromise: the word
    really does span the line break, and a reader clicking either half should see it.
    """
    tokens = [token for token in verse.text.split() if AKSHARAM.search(token)]
    if not tokens or not verse.morphemes:
        return [(token, []) for token in tokens]

    # The verse as one run of Telugu characters, remembering which token each came from.
    surface: list[str] = []
    token_of: list[int] = []
    for index, token in enumerate(tokens):
        for character in token:
            if _is_telugu(character):
                surface.append(character)
                token_of.append(index)

    # The morphemes likewise, remembering which morpheme each character came from.
    stream: list[str] = []
    morpheme_of: list[int] = []
    for index, morpheme in enumerate(verse.morphemes):
        for character in morpheme.form:
            if _is_telugu(character):
                stream.append(character)
                morpheme_of.append(index)

    matcher = difflib.SequenceMatcher(
        None, "".join(surface), "".join(stream), autojunk=False
    )
    # Which morphemes have characters in which tokens.
    by_token: list[list[int]] = [[] for _ in tokens]
    for surface_start, stream_start, length in matcher.get_matching_blocks():
        for offset in range(length):
            token_index = token_of[surface_start + offset]
            morpheme_index = morpheme_of[stream_start + offset]
            if morpheme_index not in by_token[token_index]:
                by_token[token_index].append(morpheme_index)

    # A morpheme that matched nothing — usually a single vowel wholly absorbed by sandhi,
    # such as the `ఐ` in `గంటకుండై` — is placed with its neighbour so no gloss is lost.
    placed = {index for indices in by_token for index in indices}
    for index in range(len(verse.morphemes)):
        if index in placed:
            continue
        for token_index, indices in enumerate(by_token):
            if any(neighbour in (index - 1, index + 1) for neighbour in indices):
                by_token[token_index].append(index)
                break

    return [
        (token, [verse.morphemes[i] for i in sorted(indices)])
        for token, indices in zip(tokens, by_token)
    ]


def _is_telugu(character: str) -> bool:
    return "\u0c00" <= character <= "\u0c7f"


@dataclass
class AnnotatedText:
    """One annotated section, ready to render."""

    title: str
    verses: list[Verse]
    url: str = ""
    revision: int = 0

    @property
    def morpheme_count(self) -> int:
        return sum(len(v.morphemes) for v in self.verses)

    @property
    def glossed_pct(self) -> float:
        total = self.morpheme_count
        return 100.0 * sum(v.glossed for v in self.verses) / total if total else 0.0

    @property
    def annotated_verses(self) -> int:
        """Verses carrying an editorial gloss.

        Reported alongside the morpheme figure because they answer different questions.
        Every morpheme the editors glossed has a meaning — that is 100% by construction.
        What varies is *which verses* they have reached: 530 of 577 in the first skandham,
        with the remaining 47 having no `టీక` block at all. A page whose verses are
        unglossed shows its text without word annotation, and saying so is better than
        letting it look like the aligner failed.
        """
        return sum(1 for v in self.verses if v.morphemes)

    @property
    def labelled_pct(self) -> float:
        """Morphemes carrying a grammatical label, from a dictionary or the suffix list.

        Reported separately from `glossed_pct` because they measure different things. The
        editor glosses every morpheme, so the gloss figure is ~100% and says the text is
        fully explained *in Telugu*. The label figure says how much also has a part of
        speech and an etymology — which is lower, and is the number to improve.
        """
        total = self.morpheme_count
        return 100.0 * sum(v.confirmed for v in self.verses) / total if total else 0.0


def annotate(page, lookup=None, limit: int | None = None) -> AnnotatedText:
    """A fetched Wikisource page as an annotated text.

    Runs the whole pipeline: split into verses, read the editorial gloss, align morphemes
    to printed tokens, and confirm each against the dictionary.
    """
    verses = parse_page(page.text)
    confirm(verses, lookup=lookup, limit=limit)
    for verse in verses:
        verse.alignment = align(verse)
    return AnnotatedText(
        title=page.title, verses=verses, url=page.url, revision=page.revision
    )
