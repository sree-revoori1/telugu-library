"""Building the annotated Bhāgavatam.

    python -m telugu_library.build_bhagavatam --skandham 1
    python -m telugu_library.build_bhagavatam --all

A separate entry point from `build`, because the material is different in kind. The
general builder renders a text with a per-word lemma from the morphological analyser; this
renders a text with an *editorial* morpheme breakdown, a Telugu meaning for every
morpheme, and a prose paraphrase per verse. Where that editorial layer exists it is
strictly better than anything computed, so it is used instead rather than alongside.

Coverage here is honest in a way the general builder's could not be: the gloss covers
100% of morphemes because a scholar wrote it, and the only thing missing is the
grammatical label that a dictionary would add.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from . import site
from .bhagavatam import annotate
from .wikisource import cached_page

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
OUT = ROOT / "site"

PREFIX = "పోతన తెలుగు భాగవతము/"

# The skandhams in reading order, since a dictionary of page titles has no order and a
# reader expects the first book first.
SKANDHAMS = [
    "ప్రథమ స్కంధము",
    "ద్వితీయ స్కంధము",
    "తృతీయ స్కంధము",
    "చతుర్ధ స్కంధము",
    "పంచమ స్కంధము (ప్రథమాశ్వాసము)",
    "పంచమ స్కంధము (ద్వితీయాశ్వాసము)",
    "షష్ఠ స్కంధము",
    "సప్తమ స్కంధము",
    "అష్ఠమ స్కంధము",
    "నవమ స్కంధము",
    "దశమ స్కంధము (ప్రథమాశ్వాసము)",
    "దశమ స్కంధము (ద్వితీయాశ్వాసము)",
    "ఏకాదశ స్కంధము",
    "ద్వాదశ స్కంధము",
]


def page_list() -> list[str]:
    path = DATA / "bhagavatam-pages.json"
    if not path.exists():
        sys.exit(f"missing {path}. Run the page enumeration first.")
    return json.loads(path.read_text(encoding="utf-8"))


def slug_for(title: str) -> str:
    import hashlib

    return "bh-" + hashlib.sha256(title.encode("utf-8")).hexdigest()[:10]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skandham", type=int, default=1, help="1-based, in order")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)

    pages = page_list()
    wanted = SKANDHAMS if args.all else [SKANDHAMS[args.skandham - 1]]

    by_skandham: dict[str, list[str]] = defaultdict(list)
    for title in pages:
        for name in wanted:
            if title.startswith(PREFIX + name + "/"):
                by_skandham[name].append(title)

    total_verses = total_morphemes = glossed = labelled = 0
    built: dict[str, list[tuple[str, str]]] = defaultdict(list)

    for name in wanted:
        titles = sorted(by_skandham.get(name, []))
        if not titles:
            continue
        for index, title in enumerate(titles, 1):
            try:
                page = cached_page(title)
            except Exception:
                continue
            if page is None or not page.text.strip():
                continue
            text = annotate(page)
            if not text.verses:
                # Not a verse page — a table of contents or a stub.
                continue
            slug = slug_for(title)
            site.write(
                args.out / "text" / f"{slug}.html", site.render_verse_text(text)
            )
            section = title.split("/")[-1]
            built[name].append((section, slug))
            total_verses += len(text.verses)
            total_morphemes += text.morpheme_count
            glossed += sum(v.glossed for v in text.verses)
            labelled += sum(v.confirmed for v in text.verses)
            if index % 20 == 0:
                print(f"  {name}: {index}/{len(titles)}", flush=True)

    for name, sections in built.items():
        site.write(
            args.out / "genre" / f"{name}.html", site.render_genre(name, sections)
        )
    # The front page, listing the skandhams in reading order rather than by size — a
    # reader of the Bhāgavatam expects the first book first.
    ordered = {name: built[name] for name in SKANDHAMS if name in built}
    site.write(
        args.out / "index.html",
        site.render_index(
            ordered,
            {name: f"{len(sections):,} sections" for name, sections in ordered.items()},
        ),
    )

    print(f"\nbuilt {sum(len(s) for s in built.values())} sections")
    print(f"  {total_verses:,} verses, {total_morphemes:,} morphemes")
    if total_morphemes:
        print(f"  glossed  {100*glossed/total_morphemes:.1f}%  (editorial)")
        print(f"  labelled {100*labelled/total_morphemes:.1f}%  (dictionary + suffixes)")
    print(f"  written to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
