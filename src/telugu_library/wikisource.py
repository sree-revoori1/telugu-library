"""Fetching Telugu literature from Wikisource.

Telugu Wikisource holds the classical canon as *edited Unicode text* rather than page
scans: Nannayya's Mahābhāratam, Pothana's Bhāgavatam, Rangānātha Rāmāyaṇam and the
śatakam tradition, in 23,736 articles under CC BY-SA 4.0. That matters more than it
sounds. Archive.org has some 12,887 Telugu texts, but they are overwhelmingly page
images with OCR, and Telugu OCR is poor enough — conjuncts and matras are exactly what
it loses — that a reader built on it would be quoting errors.

The verse markers are preserved because they are what makes the result citable rather
than merely readable:

    కం.   kanda padyam, a four-line metre
    వ.    vachanam, prose passage
    సీ.   sīsa padyam
    ఆ.    āṭaveladi
    తే.   tētagīti
    (1-185)   the canonical verse number, book-verse

A scholar cites `భాగవతం 1-185`, so the number has to survive fetching. Losing it
would make every quotation unverifiable.

Attribution is a licence condition, not a courtesy, so every fetched page records its
title, URL, revision id and licence.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field, asdict
from pathlib import Path

API = "https://te.wikisource.org/w/api.php"
LICENCE = "CC BY-SA 4.0"
LICENCE_URL = "https://creativecommons.org/licenses/by-sa/4.0/"

# Wikimedia rejects requests without a descriptive User-Agent — a bare urllib call
# gets HTTP 403. Their policy asks for a contact, so it names the project.
USER_AGENT = (
    "telugu-library/0.1 (https://github.com/sree-revoori1/telugu-library; "
    "building a parsing reader for Telugu literature)"
)

# Courtesy delay between requests. Wikimedia asks for serial access from a single
# client rather than a fixed rate, so this is deliberately unhurried: the whole corpus
# is fetched once and cached.
DELAY_SECONDS = 0.2

CACHE = Path.home() / ".cache" / "telugu-library"

# Verse-form markers that open a line in a Telugu poetic text. Kept as a set because
# recognising them is what lets the reader lay out verse as verse.
VERSE_MARKERS: tuple[str, ...] = (
    "కం.", "క.", "వ.", "సీ.", "ఆ.", "తే.", "మ.", "శా.", "ఉ.", "చ.", "గీ.", "ద్వి.",
)

# A canonical verse number, written `(1-185)` — book and verse.
VERSE_NUMBER = re.compile(r"\((\d+)\s*-\s*(\d+)\)")


@dataclass
class Page:
    """One fetched Wikisource page, with the provenance the licence requires."""

    title: str
    text: str
    revision: int = 0
    # The category path this page was reached through, which is what the site's
    # browse-by-genre navigation is built from.
    categories: list[str] = field(default_factory=list)

    @property
    def url(self) -> str:
        return "https://te.wikisource.org/wiki/" + urllib.parse.quote(
            self.title.replace(" ", "_")
        )

    @property
    def attribution(self) -> str:
        """The credit line, which CC BY-SA obliges us to carry."""
        return f"{self.title} — Telugu Wikisource, {LICENCE}"

    def verse_numbers(self) -> list[str]:
        """Canonical verse references found in the text, e.g. `1-185`."""
        return [f"{a}-{b}" for a, b in VERSE_NUMBER.findall(self.text)]

    def to_dict(self) -> dict:
        out = asdict(self)
        out["url"] = self.url
        out["licence"] = LICENCE
        return out


def _request(params: dict) -> dict:
    """One API call, with the User-Agent Wikimedia requires."""
    params = {"format": "json", "action": "query", **params}
    url = API + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def category_members(
    category: str, limit: int = 500
) -> tuple[list[str], list[str]]:
    """Pages and subcategories of a Wikisource category.

    Returns them separately because they are navigated differently: a subcategory is
    recursed into, a page is fetched.
    """
    if not category.startswith("వర్గం:"):
        category = "వర్గం:" + category
    pages: list[str] = []
    subcategories: list[str] = []
    continuation: dict = {}
    while True:
        data = _request(
            {
                "list": "categorymembers",
                "cmtitle": category,
                "cmlimit": min(limit, 500),
                **continuation,
            }
        )
        for member in data.get("query", {}).get("categorymembers", []):
            title = member["title"]
            if title.startswith("వర్గం:"):
                subcategories.append(title)
            else:
                pages.append(title)
        if "continue" not in data or len(pages) >= limit:
            break
        continuation = data["continue"]
        time.sleep(DELAY_SECONDS)
    return pages, subcategories


def fetch_page(title: str) -> Page | None:
    """One page as plain text, or None if it does not exist.

    `explaintext` is used rather than the wikitext, because the wikitext of a
    Wikisource page is mostly transclusion templates and page-scan references. The
    rendered plain text is the edited reading text, which is what a reader wants.
    """
    data = _request(
        {
            "prop": "extracts|revisions",
            "explaintext": 1,
            "rvprop": "ids",
            "titles": title,
        }
    )
    for page in data.get("query", {}).get("pages", {}).values():
        if "missing" in page:
            return None
        text = page.get("extract", "")
        if not text.strip():
            return None
        revisions = page.get("revisions") or [{}]
        return Page(
            title=page.get("title", title),
            text=text,
            revision=revisions[0].get("revid", 0),
        )
    return None


def cached_page(title: str, cache: Path = CACHE) -> Page | None:
    """A page, fetched once and reused.

    The corpus is fetched repeatedly during development — every layout change means
    rebuilding the site — and re-downloading it each time would be discourteous to a
    donated service as well as slow.
    """
    cache.mkdir(parents=True, exist_ok=True)
    # Hashed, because a Telugu title cannot be a filename. It contains slashes and
    # spaces, and percent-encoding it is worse than useless: every Telugu character
    # becomes nine ASCII bytes, so a normal chapter heading exceeds the 255-byte
    # filename limit and the write fails with ENAMETOOLONG. The title is stored inside
    # the file, so nothing is lost by the name being opaque.
    key = hashlib.sha256(title.encode("utf-8")).hexdigest()[:32]
    path = cache / f"{key}.json"
    if path.exists():
        return Page(**{
            k: v for k, v in json.loads(path.read_text(encoding="utf-8")).items()
            if k in ("title", "text", "revision", "categories")
        })
    page = fetch_page(title)
    time.sleep(DELAY_SECONDS)
    if page is not None:
        path.write_text(
            json.dumps(page.to_dict(), ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
    return page
