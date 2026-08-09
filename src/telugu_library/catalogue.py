"""The catalogue: which works exist, and how a reader navigates to them.

ancientlibrary.net's structure is the thing worth copying — browse by genre, then by
author, then by work, with an A–Z index across everything. Telugu Wikisource already
has that information in its category tree, so the catalogue is discovered rather than
hand-listed.

The tree is genuinely a tree and not a hierarchy, which takes some care. A work can
sit under several categories, categories contain other categories to arbitrary depth,
and there are cycles. So traversal is breadth-first with a visited set and a depth
bound, and each page records every path it was reached by.

Only the classical canon is collected. Wikisource also holds modern copyrighted-but-
released material, budget speeches and magazine scans; those are real texts but they
are not what a classical library is for, and mixing them would make the collection
incoherent.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .wikisource import DELAY_SECONDS, category_members, cached_page

# The genres a Telugu literary library is organised by, with the Wikisource category
# each is drawn from. Chosen rather than discovered: the top of Wikisource's tree mixes
# genre with housekeeping ("books being scanned", "works by copyright status"), and a
# reader wants the genres.
GENRES: dict[str, str] = {
    "ఇతిహాసాలు": "Epics — the Mahābhāratam and Rāmāyaṇam traditions",
    "పురాణాలు": "Purāṇas — the Bhāgavatam and its relatives",
    "శతకములు": "Śatakams — hundred-verse sequences, the great popular form",
    "కవిత్వము": "Poetry",
    "నాటకాలు": "Drama",
    "ప్రబంధములు": "Prabandhams — the courtly narrative poems",
    "వేదాలు": "Vedic and philosophical texts",
    "సంకీర్తనలు": "Devotional song",
}

# How deep to recurse. The Bhāgavatam sits three levels down — పురాణాలు → పోతన తెలుగు
# భాగవతము → skandham → chapter — and beyond four the tree stops being about genre and
# starts being about wiki housekeeping.
MAX_DEPTH = 4


@dataclass
class Work:
    """One text in the catalogue, before its content is fetched."""

    title: str
    genre: str
    # The category path it was reached by, which gives the breadcrumb a reader follows.
    path: list[str] = field(default_factory=list)

    @property
    def slug(self) -> str:
        """A URL-safe identifier, stable across builds.

        Hashed rather than transliterated. A transliteration scheme would have to be
        invented, would collide (`శ` and `ష` both give `sh`), and would change if the
        scheme were ever revised — breaking every link. The title is carried in the
        page itself, so the URL does not need to be legible.
        """
        import hashlib

        return hashlib.sha256(self.title.encode("utf-8")).hexdigest()[:12]

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "genre": self.genre,
            "path": self.path,
            "slug": self.slug,
        }


def walk_genre(
    genre: str, max_depth: int = MAX_DEPTH, limit: int = 4000
) -> list[Work]:
    """Every page reachable under one genre category.

    Breadth-first with a visited set, because the category graph has cycles — a
    subcategory can list its own parent — and a naive recursion never returns.
    """
    works: list[Work] = []
    seen_categories: set[str] = set()
    seen_titles: set[str] = set()
    frontier: list[tuple[str, list[str]]] = [(genre, [genre])]
    depth = 0

    while frontier and depth < max_depth and len(works) < limit:
        next_frontier: list[tuple[str, list[str]]] = []
        for category, path in frontier:
            if category in seen_categories:
                continue
            seen_categories.add(category)
            try:
                pages, subcategories = category_members(category)
            except Exception:
                # A category that fails to load should not abort the whole walk; the
                # catalogue is better incomplete than absent.
                continue
            for title in pages:
                if title in seen_titles:
                    continue
                seen_titles.add(title)
                works.append(Work(title=title, genre=genre, path=list(path)))
            for sub in subcategories:
                name = sub.replace("వర్గం:", "")
                next_frontier.append((sub, path + [name]))
        frontier = next_frontier
        depth += 1
    return works


def build(genres: dict[str, str] | None = None) -> list[Work]:
    """The whole catalogue, across every genre."""
    genres = genres or GENRES
    out: list[Work] = []
    seen: set[str] = set()
    for genre in genres:
        for work in walk_genre(genre):
            if work.title in seen:
                continue
            seen.add(work.title)
            out.append(work)
    return out


def save(works: list[Work], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([w.to_dict() for w in works], ensure_ascii=False, indent=1),
        encoding="utf-8",
    )


def load(path: Path) -> list[Work]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [
        Work(title=d["title"], genre=d["genre"], path=d.get("path", []))
        for d in data
    ]
