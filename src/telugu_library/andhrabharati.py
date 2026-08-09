"""Looking a word up in andhrabharati's dictionary aggregator.

[andhrabharati.com](https://andhrabharati.com/dictionary/) searches some 94 Telugu
dictionaries, including the ones that matter for classical text: Śabdaratnākaramu (1912),
Āndhra Vācaspatyamu (1953), Śrīhari (2004), Śaṅkaranārāyaṇa Telugu–English (1953). For a
15th-century poem it is far better evidence than any modern corpus, because those
dictionaries were compiled *from* the classical literature.

What this module takes and what it deliberately does not:

  * **Taken**: whether the headword exists, which dictionaries have it, the grammatical
    abbreviation each gives (`వి.` noun, `విణ.` adjective, `క్రి.` verb, `అవ్య.`
    particle), and the etymology marker (`సం.` Sanskrit, `దే.` native Telugu). These are
    facts about the language — not copyrightable, and exactly what a parsing reader needs.
  * **Not taken**: the definition text. That is authored prose, the site reserves rights
    over it, and it holds those permissions from individual publishers rather than being
    free to sublicense. The reader links out per word instead, which sends andhrabharati
    the traffic and keeps the attribution where it belongs.

The request format was read from the site's own `abtd.*.js`. It is a POST to `getWM.php`
with the word, a dictionary-selection string, and a token that may be empty. Results are
cached on disk permanently: these texts are fixed, so a word looked up once never needs
looking up again, and re-asking would be discourteous.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field, asdict
from pathlib import Path

ENDPOINT = "https://andhrabharati.com/dictionary/getWM.php"
REFERER = "https://andhrabharati.com/dictionary/"
LOOKUP_URL = "https://andhrabharati.com/dictionary/?w="

# The dictionary selection the site itself sends when all are ticked, copied verbatim
# from `getWords2` in its JavaScript so the query is the same one a browser makes.
ALL_DICTIONARIES = (
    "W|E|N|Y|2|6|7|8|35|50|10|13|14|29|52|1|11|4|12|51|48|49|43|54|55|56|34|36|37|"
    "9|44|17|18|19|20|21|22|23|24|25|33|15|41|31|32|3|39|38|40|42|45|46|47|58"
)

USER_AGENT = (
    "telugu-library/0.1 (+https://github.com/sree-revoori1/telugu-library) "
    "classical Telugu annotation research"
)

# robots.txt asks for Crawl-delay: 1. Honoured, and doubled — nothing here is urgent.
DELAY_SECONDS = 2.0

CACHE = Path.home() / ".cache" / "telugu-library" / "andhrabharati"

# Grammatical abbreviations the Telugu dictionaries use, mapped to a part of speech.
# These are the traditional labels, and reading them is what makes the lookup useful
# beyond "the word exists".
PARTS_OF_SPEECH: dict[str, str] = {
    "విణ.": "adjective",     # విశేషణము
    "వి.": "noun",           # విశేష్యము / నామవాచకము
    "క్రి.": "verb",         # క్రియ
    "క్రి.వి.": "adverb",    # క్రియావిశేషణము
    "అవ్య.": "particle",     # అవ్యయము
    "సర్వ.": "pronoun",      # సర్వనామము
    "సం.వి.": "noun",
    "సం.విణ.": "adjective",
    "ఉభ.": "either",
}

# Etymology markers.
ETYMOLOGY: dict[str, str] = {
    "సం.": "sanskrit",       # సంస్కృత సమము — a Sanskrit loan
    "దే.": "native",         # దేశ్యము — native Telugu
    "అ.": "arabic",
    "హి.": "hindi",
    "ఉ.": "urdu",
    "ఆం.": "english",
}


@dataclass
class Entry:
    """One dictionary's evidence about a headword."""

    headword: str
    dictionary: str
    pos: str | None = None
    etymology: str | None = None
    # An English gloss *only* where a Telugu-English dictionary gives a short one. Kept
    # because it is what makes the annotation legible to a learner, and short factual
    # glosses of single words are not the expressive content the licence protects.
    english: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Lookup:
    """Everything andhrabharati knows about one queried form."""

    query: str
    entries: list[Entry] = field(default_factory=list)
    # Headwords the dictionaries actually matched, which may differ from the query in
    # orthography: `ఆఢ్యుడు` matches both `ఆఢ్యుఁడు` and `ఆఢ్యుడు`.
    headwords: list[str] = field(default_factory=list)

    @property
    def url(self) -> str:
        return LOOKUP_URL + urllib.parse.quote(self.query)

    @property
    def telugu_entries(self) -> list[Entry]:
        """Entries from Telugu dictionaries, discarding the other-language ones.

        The aggregator searches Urdu, Arabic and Hindi dictionaries alongside the Telugu
        ones, and a Telugu string can collide with a headword in any of them. `కున్` is
        the Telugu dative suffix and matches *only* Urdu dictionaries, which duly report
        a noun — so an unfiltered vote labelled a case marker as a noun. A match in a
        non-Telugu dictionary is evidence about that language, not this one.
        """
        return [
            entry
            for entry in self.entries
            if not any(
                marker in entry.dictionary
                for marker in ("ఉర్దూ", "ఉరుదూ", "అరబ", "హిందీ", "పార్సీ")
            )
        ]

    @property
    def found(self) -> bool:
        """Whether a *Telugu* dictionary lists it."""
        return bool(self.telugu_entries)

    @property
    def pos(self) -> str | None:
        """The part of speech the Telugu dictionaries agree on, if they do.

        Majority vote across dictionaries. They can disagree — a word may be listed as
        both noun and adjective, which in Telugu is often genuinely true — and where the
        vote ties, None is returned rather than a coin flip.
        """
        votes: dict[str, int] = {}
        for entry in self.telugu_entries:
            if entry.pos:
                votes[entry.pos] = votes.get(entry.pos, 0) + 1
        if not votes:
            return None
        best = max(votes.values())
        winners = [p for p, v in votes.items() if v == best]
        return winners[0] if len(winners) == 1 else None

    @property
    def etymology(self) -> str | None:
        for entry in self.telugu_entries:
            if entry.etymology:
                return entry.etymology
        return None

    @property
    def english(self) -> str | None:
        for entry in self.telugu_entries:
            if entry.english:
                return entry.english
        return None

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "headwords": self.headwords,
            "pos": self.pos,
            "etymology": self.etymology,
            "english": self.english,
            "dictionaries": [e.dictionary for e in self.entries],
            "entries": [e.to_dict() for e in self.entries],
            "url": self.url,
        }


def _strip(markup: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", markup))).strip()


def _first_english_sentence(text: str) -> str | None:
    """A short English gloss from a Telugu-English entry, if it reads like one."""
    if not re.search(r"[A-Za-z]", text):
        return None
    # `n.noun. one who is opulent or wealthy.` → the part after the abbreviation.
    # A Telugu-English entry looks like `n.noun. one who is opulent or wealthy.` — an
    # abbreviation, its expansion, then the gloss. Take the longest run of Latin text,
    # which is the gloss, and stop at the first sentence end.
    latin = re.findall(r"[A-Za-z][A-Za-z ,;'()/-]{3,}", text)
    if not latin:
        return None
    cleaned = max(latin, key=len).strip(" ,;-")
    # Drop a leading part-of-speech expansion: `noun. one who…` → `one who…`
    cleaned = re.sub(
        r"^(noun|verb|adjective|adverb|pronoun|particle|interjection)\b\.?\s*",
        "",
        cleaned,
        flags=re.I,
    ).strip()
    return cleaned[:90] if len(cleaned) > 2 else None


def parse_response(query: str, markup: str) -> Lookup:
    """Turns andhrabharati's HTML into structured facts."""
    lookup = Lookup(query=query)
    # Each hit is a `<dt>headword : dictionary</dt><dd>entry</dd>` pair.
    pairs = re.findall(r"<dt[^>]*>(.*?)</dt>\s*<dd[^>]*>(.*?)</dd>", markup, re.S)
    for raw_dt, raw_dd in pairs:
        head = _strip(raw_dt)
        body = _strip(raw_dd)
        if ":" in head:
            headword, dictionary = (part.strip() for part in head.split(":", 1))
        else:
            headword, dictionary = head, ""
        # Trim the dictionary name to its title, dropping the trailing index links.
        dictionary = re.split(r"\s+(?:గ్రంథసంకేత|\d{4})", dictionary)[0].strip()

        pos = None
        for marker, name in PARTS_OF_SPEECH.items():
            if marker in body[:60]:
                pos = name
                break
        etymology = None
        for marker, name in ETYMOLOGY.items():
            if body.startswith(marker):
                etymology = name
                break
        lookup.entries.append(
            Entry(
                headword=headword,
                dictionary=dictionary,
                pos=pos,
                etymology=etymology,
                english=_first_english_sentence(body),
            )
        )
        if headword and headword not in lookup.headwords:
            lookup.headwords.append(headword)
    return lookup


class Blocked(Exception):
    """The site has refused the request.

    Raised rather than returned, because the alternative is silently indistinguishable
    from "the word does not exist" — and that mistake corrupted 325 cache entries here
    before it was noticed. `ముని` and `వేదము` are unquestionably Telugu words; they were
    recorded as absent because a 403 returns a perfectly parseable empty page.
    """


def fetch(word: str, timeout: int = 45) -> Lookup:
    """One live lookup. Prefer `cached` — this does not rate-limit itself.

    Raises `Blocked` on any refusal. A dictionary that will not answer is not the same
    thing as a dictionary that answers "no", and conflating them poisons the cache
    permanently, since a cached absence is never retried.
    """
    body = urllib.parse.urlencode(
        {"w": word, "token": "", "opt": ALL_DICTIONARIES}
    ).encode("utf-8")
    request = urllib.request.Request(
        ENDPOINT,
        data=body,
        headers={
            "User-Agent": USER_AGENT,
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": REFERER,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            markup = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        if error.code in (403, 429, 503):
            raise Blocked(
                f"andhrabharati returned {error.code}. Access has been refused — "
                "do not retry or work around it."
            ) from error
        raise
    # A refusal can also arrive as a 200. Two shapes seen from this site, and the second
    # is the dangerous one:
    #
    #   * a 403 page — obvious;
    #   * **HTTP 200 with an empty body** (a single newline). This is indistinguishable
    #     from a successful search that found nothing, unless the emptiness itself is
    #     treated as suspicious. It is not: a real "no results" response still carries the
    #     `లభించినఫలితాలు: (0)` heading and the page furniture, so a body this short can
    #     only be a refusal.
    #
    # Conflating the second with a genuine absence is what poisoned 325 cache entries
    # here, recording `ముని` and `వేదము` — plainly Telugu words — as not existing.
    if "Forbidden" in markup[:200]:
        raise Blocked("andhrabharati returned a Forbidden page.")
    if len(markup.strip()) < 20:
        raise Blocked(
            "andhrabharati returned an empty body, which is a refusal rather than "
            "an absence of results."
        )
    return parse_response(word, markup)


def cached(word: str, cache: Path = CACHE) -> Lookup:
    """A lookup, fetched once and kept.

    Cached permanently and without expiry, which is right here: the texts are fixed and
    a dictionary from 1912 is not going to change its mind.
    """
    cache.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(word.encode("utf-8")).hexdigest()[:32]
    path = cache / f"{key}.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        lookup = Lookup(query=data["query"], headwords=data.get("headwords", []))
        lookup.entries = [Entry(**e) for e in data.get("entries", [])]
        return lookup

    try:
        lookup = fetch(word)
    except Blocked:
        # Never cached, and never retried in a loop. The site has said no; the caller
        # should fall back to what it already has rather than press on.
        raise
    except Exception:
        # A transient failure is not cached either: the word may be findable later, and
        # writing an empty result would make the failure permanent.
        return Lookup(query=word)
    time.sleep(DELAY_SECONDS)
    path.write_text(
        json.dumps(lookup.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return lookup


def exists(word: str) -> bool:
    """Whether any dictionary lists the word. The single most useful fact."""
    return cached(word).found
