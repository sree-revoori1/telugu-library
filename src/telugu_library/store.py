"""The annotation store: a real data layer between alignment and rendering.

Until this existed, the analysis lived *only* as `data-` attributes inside generated
HTML — 687 pages averaging 141 KB, 94.5 MB in total. That made the site the database,
and so a whole class of ordinary operations was impossible without a rewrite of
`site.py`: search across texts, correct one gloss without rebuilding everything, accept
a scholar's emendation, version an annotation, serve an API, export CoNLL-U, or answer
"where else does this morpheme occur".

The shape is borrowed from Perseus' Scaife ATLAS, because it solves the problem this
text actually has — **overlapping hierarchies**. A verse is a unit of citation, a line
is a unit of printing, and a word belongs to both without either containing the other.
Classical Telugu makes this sharper than Greek does: printing breaks on the *metre*, so
a single morpheme routinely straddles two printed tokens.

Four decisions, each of which is expensive to reverse:

1. **Materialized path for the hierarchy.** `node.path` is a dotted run of fixed-width
   steps, so an entire subtree is one indexed `LIKE '0001.0003.%'` — no recursive query
   and no adjacency-list walk. (treebeard's `MP_Node`, without treebeard.)

2. **Every layer joins to token or morpheme *ids*, never to character offsets.** The
   cautionary case is VedaWeb: ~13 parallel layers aligned positionally, no
   cross-references, and 63 of 428 stanzas in Book 2 now disagree about how many tokens
   they contain. Ids cannot drift; offsets do, the moment anyone fixes a typo.

3. **Token↔morpheme is many-to-many, not a tree.** TEITOK's `<tok>`/`<dtok>` — an
   orthographic token for display, its constituent morphemes for indexing — is the right
   model, but its nesting assumes each `dtok` sits inside exactly one `tok`. Ours cannot:
   `ఆరూఢుండు` has characters in both `పరికరస్యందనారూఢుం` and `డగు`. Forcing a tree
   would mean picking one parent and being wrong, which is precisely the bug that made
   three earlier aligners useless. So the link is its own table, carrying `shared`.

4. **Provenance and confidence on every annotation, not on the corpus.** This is what
   lets an editorial `టీక`, a dictionary lookup, a computed guess and a human correction
   coexist in one table while remaining distinguishable — and it is what makes tiering
   the UI possible ("a scholar wrote this" vs "we inferred this"). A correction
   supersedes rather than overwrites, so the history survives.

Stdlib `sqlite3` only. ATLAS is Django, and Django would be the first dependency this
project has; the schema is what carries the value here, not the ORM. Static-first
rendering is unchanged — the store sits *behind* the build, which still emits plain
files.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / "data" / "library.db"

# Width of one materialized-path step. Four hex digits allows 65,535 children per parent;
# the largest fan-out here is a skandham's sections (~180) and a section's verses (~600).
STEP = 4
PATH_SEP = "."

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------- hierarchy
-- corpus → work → book (skandham) → section → verse, as a materialized path.
CREATE TABLE IF NOT EXISTS node (
    id        INTEGER PRIMARY KEY,
    path      TEXT    NOT NULL UNIQUE,
    depth     INTEGER NOT NULL,
    kind      TEXT    NOT NULL,   -- corpus|work|book|section|verse
    parent_id INTEGER REFERENCES node(id),
    -- A citable reference, in the CTS spirit: 'bhagavatam:1.34'. Stable across rebuilds
    -- because it is derived from the text's own numbering, not from row order.
    urn       TEXT    UNIQUE,
    ref       TEXT,               -- the reference within its parent ('1-34')
    label     TEXT,               -- display title
    meta      TEXT                -- JSON: source url, revision, licence, metre
);
CREATE INDEX IF NOT EXISTS node_path  ON node(path);
CREATE INDEX IF NOT EXISTS node_kind  ON node(kind);
CREATE INDEX IF NOT EXISTS node_parent ON node(parent_id);

-- ---------------------------------------------------------------- provenance
-- Who says so. Every annotation points here, so "a scholar wrote this" and "we computed
-- this" are different rows rather than indistinguishable strings.
CREATE TABLE IF NOT EXISTS source (
    id      INTEGER PRIMARY KEY,
    slug    TEXT UNIQUE NOT NULL,
    title   TEXT,
    url     TEXT,
    licence TEXT,
    kind    TEXT                  -- editorial|dictionary|computed|human
);

-- ---------------------------------------------------------------- tokens
-- The printed token, exactly as set. `line` and `part` record the printing, which is a
-- different hierarchy from the verse: see LineBreak below.
CREATE TABLE IF NOT EXISTS token (
    id       INTEGER PRIMARY KEY,
    node_id  INTEGER NOT NULL REFERENCES node(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,    -- 0-based, reading order within the verse
    text     TEXT    NOT NULL,    -- as printed, punctuation and all
    subref   TEXT,                -- 'bhagavatam:1.34@3' — citable per occurrence
    line     INTEGER,             -- which printed line of the verse it sits on
    UNIQUE (node_id, position)
);
CREATE INDEX IF NOT EXISTS token_node ON token(node_id);
CREATE INDEX IF NOT EXISTS token_text ON token(text);

-- ---------------------------------------------------------------- morphemes
-- A morpheme belongs to the *verse*, not to a token, because it may span two tokens.
-- `parent_id` is for compound decomposition (a samāsa's constituents); the editorial
-- ṭīka gives a flat list, so it is NULL today and the column exists so that adding
-- nesting later is an insert rather than a migration.
CREATE TABLE IF NOT EXISTS morpheme (
    id        INTEGER PRIMARY KEY,
    node_id   INTEGER NOT NULL REFERENCES node(id) ON DELETE CASCADE,
    ordinal   INTEGER NOT NULL,   -- reading order within the verse
    parent_id INTEGER REFERENCES morpheme(id),
    form      TEXT    NOT NULL,
    lemma     TEXT,
    pos       TEXT,
    etymology TEXT,
    is_suffix INTEGER NOT NULL DEFAULT 0,
    UNIQUE (node_id, ordinal)
);
CREATE INDEX IF NOT EXISTS morpheme_node ON morpheme(node_id);
CREATE INDEX IF NOT EXISTS morpheme_form ON morpheme(form);
CREATE INDEX IF NOT EXISTS morpheme_lemma ON morpheme(lemma);

-- The many-to-many that a tree cannot express. `shared` means this morpheme has
-- characters in more than one printed token — it straddles the line break.
CREATE TABLE IF NOT EXISTS token_morpheme (
    token_id    INTEGER NOT NULL REFERENCES token(id) ON DELETE CASCADE,
    morpheme_id INTEGER NOT NULL REFERENCES morpheme(id) ON DELETE CASCADE,
    shared      INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (token_id, morpheme_id)
);
CREATE INDEX IF NOT EXISTS tm_morpheme ON token_morpheme(morpheme_id);

-- ---------------------------------------------------------------- layers
-- Each annotation layer is its own table keyed on ids. Adding a layer never touches the
-- others, which is the property VedaWeb's positional alignment lacks.

-- The meaning of one morpheme. Versioned: a correction inserts a new row and points the
-- old one at it, so provenance and history both survive.
CREATE TABLE IF NOT EXISTS gloss (
    id            INTEGER PRIMARY KEY,
    morpheme_id   INTEGER NOT NULL REFERENCES morpheme(id) ON DELETE CASCADE,
    text          TEXT    NOT NULL,
    language      TEXT    NOT NULL DEFAULT 'te',
    source_id     INTEGER REFERENCES source(id),
    confidence    REAL,             -- 1.0 editorial; lower for computed
    annotator     TEXT,
    created       TEXT,
    superseded_by INTEGER REFERENCES gloss(id)
);
CREATE INDEX IF NOT EXISTS gloss_morpheme ON gloss(morpheme_id);
CREATE INDEX IF NOT EXISTS gloss_live ON gloss(morpheme_id) WHERE superseded_by IS NULL;

-- The భావము: a prose paraphrase of a whole verse. A verse-level layer, so it hangs off
-- the node rather than any token.
CREATE TABLE IF NOT EXISTS paraphrase (
    id         INTEGER PRIMARY KEY,
    node_id    INTEGER NOT NULL REFERENCES node(id) ON DELETE CASCADE,
    text       TEXT    NOT NULL,
    language   TEXT    NOT NULL DEFAULT 'te',
    source_id  INTEGER REFERENCES source(id),
    confidence REAL,
    created    TEXT
);
CREATE INDEX IF NOT EXISTS paraphrase_node ON paraphrase(node_id);

-- Metre. Verse-level today (`సీ`, `ఆ`, `కం` — what the source states). Foot-level
-- scansion — guru/laghu, yati, prāsa — is per-token and belongs here as extra columns
-- on a token-keyed row; recorded as a separate table for that reason rather than as a
-- column on node.
CREATE TABLE IF NOT EXISTS metrical_annotation (
    id        INTEGER PRIMARY KEY,
    node_id   INTEGER NOT NULL REFERENCES node(id) ON DELETE CASCADE,
    token_id  INTEGER REFERENCES token(id) ON DELETE CASCADE,
    code      TEXT,               -- the source's metre abbreviation
    name      TEXT,               -- expanded name
    foot_code TEXT,               -- reserved: gaṇa, when scansion is computed
    weight    TEXT,               -- reserved: guru|laghu
    source_id INTEGER REFERENCES source(id)
);
CREATE INDEX IF NOT EXISTS metre_node ON metrical_annotation(node_id);

-- Where the printed lines fall. TEI's @part: a token may be Initial, Medial or Final
-- part of a word broken across the line. This is the layer that makes the printing
-- recoverable without it constraining the verse hierarchy.
CREATE TABLE IF NOT EXISTS line_break (
    id       INTEGER PRIMARY KEY,
    node_id  INTEGER NOT NULL REFERENCES node(id) ON DELETE CASCADE,
    line     INTEGER NOT NULL,
    position INTEGER NOT NULL,    -- token position at which this line starts
    part     TEXT,                -- I|M|F for a word split across the break
    UNIQUE (node_id, line)
);

-- ---------------------------------------------------------------- search
-- Verse text, for cross-corpus search. Contentless FTS5 over a materialised column so
-- the index can be rebuilt without touching the source rows.
CREATE VIRTUAL TABLE IF NOT EXISTS verse_fts USING fts5(
    text, urn UNINDEXED, node_id UNINDEXED, tokenize = 'unicode61'
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: Path | str = DEFAULT_DB, fresh: bool = False) -> sqlite3.Connection:
    """An open store, schema applied.

    `fresh` drops the file first. Rebuilding from cached pages is cheap and deterministic,
    so a rebuild is preferred to a migration while the schema is still settling.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if fresh and path.exists():
        path.unlink()
        for suffix in ("-wal", "-shm"):
            extra = path.with_name(path.name + suffix)
            if extra.exists():
                extra.unlink()
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.executescript(SCHEMA)
    return connection


# --------------------------------------------------------------------- writing


@dataclass
class Writer:
    """Accumulates a corpus into the store.

    Kept as a small explicit class rather than an ORM because the write path is a single
    pass: nodes in tree order, then tokens, morphemes and their links per verse.
    """

    connection: sqlite3.Connection
    _children: dict[int | None, int] = None  # parent id → children so far

    def __post_init__(self) -> None:
        if self._children is None:
            self._children = {}

    # -- hierarchy --------------------------------------------------------
    def add_node(
        self,
        kind: str,
        label: str = "",
        parent_id: int | None = None,
        urn: str | None = None,
        ref: str | None = None,
        meta: dict | None = None,
    ) -> int:
        """One node, appended as the next child of `parent_id`.

        The path is the parent's path plus a fixed-width step, which is what makes
        subtree queries a single indexed prefix match.
        """
        index = self._children.get(parent_id, 0) + 1
        self._children[parent_id] = index
        step = format(index, f"0{STEP}x")
        if parent_id is None:
            path, depth = step, 1
        else:
            row = self.connection.execute(
                "SELECT path, depth FROM node WHERE id = ?", (parent_id,)
            ).fetchone()
            path = row["path"] + PATH_SEP + step
            depth = row["depth"] + 1
        cursor = self.connection.execute(
            "INSERT INTO node (path, depth, kind, parent_id, urn, ref, label, meta)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (
                path,
                depth,
                kind,
                parent_id,
                urn,
                ref,
                label,
                json.dumps(meta, ensure_ascii=False) if meta else None,
            ),
        )
        return int(cursor.lastrowid)

    def add_source(
        self,
        slug: str,
        title: str = "",
        url: str = "",
        licence: str = "",
        kind: str = "editorial",
    ) -> int:
        self.connection.execute(
            "INSERT OR IGNORE INTO source (slug, title, url, licence, kind)"
            " VALUES (?,?,?,?,?)",
            (slug, title, url, licence, kind),
        )
        return int(
            self.connection.execute(
                "SELECT id FROM source WHERE slug = ?", (slug,)
            ).fetchone()["id"]
        )

    # -- a verse and everything in it -------------------------------------
    def add_verse(
        self,
        parent_id: int,
        urn: str,
        ref: str,
        alignment: list,
        morphemes: list,
        *,
        lines: list[list[str]] | None = None,
        paraphrase: str = "",
        metre_code: str = "",
        metre_name: str = "",
        source_id: int | None = None,
        confidence: float = 1.0,
    ) -> int:
        """A verse node with its tokens, morphemes, links and layers.

        `alignment` is `bhagavatam.align`'s output: `[(token, [Morpheme, ...]), ...]`.
        `morphemes` is the verse's flat morpheme list in reading order — the ordinal a
        morpheme gets here is what every layer refers to, so it is taken from this list
        rather than from the alignment (where a shared morpheme appears twice).
        """
        node_id = self.add_node(
            "verse",
            label=ref,
            parent_id=parent_id,
            urn=urn,
            ref=ref,
            meta={"metre": metre_code} if metre_code else None,
        )

        # Morphemes first: the links need their ids. Identity, not equality — two
        # morphemes in one verse can have the same form and different glosses.
        ordinal_of: dict[int, int] = {}
        morpheme_ids: list[int] = []
        for ordinal, morpheme in enumerate(morphemes):
            cursor = self.connection.execute(
                "INSERT INTO morpheme"
                " (node_id, ordinal, form, lemma, pos, etymology, is_suffix)"
                " VALUES (?,?,?,?,?,?,?)",
                (
                    node_id,
                    ordinal,
                    morpheme.form,
                    getattr(morpheme, "lemma", None),
                    morpheme.pos,
                    morpheme.etymology,
                    1 if morpheme.is_suffix else 0,
                ),
            )
            morpheme_id = int(cursor.lastrowid)
            morpheme_ids.append(morpheme_id)
            ordinal_of[id(morpheme)] = ordinal
            if morpheme.gloss:
                self.connection.execute(
                    "INSERT INTO gloss"
                    " (morpheme_id, text, source_id, confidence, annotator, created)"
                    " VALUES (?,?,?,?,?,?)",
                    (morpheme_id, morpheme.gloss, source_id, confidence, None, _now()),
                )

        # Which printed line each token sits on, so the printing is recoverable.
        line_of: dict[int, int] = {}
        if lines:
            position = 0
            for line_index, line_tokens in enumerate(lines):
                for _ in line_tokens:
                    line_of[position] = line_index
                    position += 1

        for position, (text, token_morphemes) in enumerate(alignment):
            cursor = self.connection.execute(
                "INSERT INTO token (node_id, position, text, subref, line)"
                " VALUES (?,?,?,?,?)",
                (node_id, position, text, f"{urn}@{position}", line_of.get(position)),
            )
            token_id = int(cursor.lastrowid)
            for morpheme in token_morphemes:
                ordinal = ordinal_of.get(id(morpheme))
                if ordinal is None:
                    # Should not happen: alignment returns the verse's own objects.
                    # Loudly skipped rather than silently mislinked.
                    continue
                self.connection.execute(
                    "INSERT OR IGNORE INTO token_morpheme"
                    " (token_id, morpheme_id, shared) VALUES (?,?,?)",
                    (token_id, morpheme_ids[ordinal], 1 if morpheme.shared else 0),
                )

        if lines:
            for line_index, line_tokens in enumerate(lines):
                start = sum(len(l) for l in lines[:line_index])
                self.connection.execute(
                    "INSERT OR IGNORE INTO line_break (node_id, line, position, part)"
                    " VALUES (?,?,?,?)",
                    (node_id, line_index, start, None),
                )

        if paraphrase:
            self.connection.execute(
                "INSERT INTO paraphrase"
                " (node_id, text, source_id, confidence, created) VALUES (?,?,?,?,?)",
                (node_id, paraphrase, source_id, confidence, _now()),
            )

        if metre_code or metre_name:
            self.connection.execute(
                "INSERT INTO metrical_annotation (node_id, code, name, source_id)"
                " VALUES (?,?,?,?)",
                (node_id, metre_code, metre_name, source_id),
            )

        text = " ".join(t for t, _ in alignment)
        self.connection.execute(
            "INSERT INTO verse_fts (text, urn, node_id) VALUES (?,?,?)",
            (text, urn, node_id),
        )
        return node_id


# --------------------------------------------------------------------- reading
# The queries that were impossible while HTML was the database. Each is a few lines
# here and would have been a change to `site.py` before.


def subtree(connection: sqlite3.Connection, node_id: int, kind: str = "") -> list:
    """Every descendant of a node, by range scan on the materialized path.

    Expressed as `path > prefix AND path < prefix_end` rather than `path LIKE prefix||'%'`.
    They select the same rows, but SQLite cannot use an index for `LIKE` against a bound
    parameter — `EXPLAIN QUERY PLAN` reported `SCAN node` — whereas the range form is
    `SEARCH node USING INDEX node_path`. That difference is the entire reason for storing
    a path, so it is worth writing the uglier predicate.
    """
    row = connection.execute(
        "SELECT path FROM node WHERE id = ?", (node_id,)
    ).fetchone()
    if row is None:
        return []
    prefix = row["path"] + PATH_SEP
    # `/` is the character after `.`, so this bounds the prefix without needing LIKE.
    upper = row["path"] + chr(ord(PATH_SEP) + 1)
    sql = "SELECT * FROM node WHERE path > ? AND path < ? "
    params: list = [prefix, upper]
    if kind:
        sql += "AND kind = ? "
        params.append(kind)
    return connection.execute(sql + "ORDER BY path", params).fetchall()


def concordance(connection: sqlite3.Connection, form: str, limit: int = 50) -> list:
    """Every occurrence of a morpheme, with its verse and its gloss there.

    This is the query the HTML-only design could not answer at all, and it is the one a
    reader of classical verse most wants: *where else does this word occur, and what did
    the editor take it to mean there?*
    """
    return connection.execute(
        """
        SELECT n.urn, n.ref, m.ordinal, m.form, g.text AS gloss,
               (SELECT group_concat(t.text, ' ')
                  FROM token t WHERE t.node_id = n.id) AS verse
          FROM morpheme m
          JOIN node n ON n.id = m.node_id
          LEFT JOIN gloss g ON g.morpheme_id = m.id AND g.superseded_by IS NULL
         WHERE m.form = ?
         ORDER BY n.path
         LIMIT ?
        """,
        (form, limit),
    ).fetchall()


def senses(connection: sqlite3.Connection, form: str) -> list:
    """The distinct glosses a morpheme has been given, with counts.

    The measured fact this exposes: 31% of morphemes carry more than one gloss across
    the corpus, averaging 2.14 distinct meanings. That is sense variation, and it was
    invisible when each page held its own copy of the answer.
    """
    return connection.execute(
        """
        SELECT g.text AS gloss, COUNT(*) AS n
          FROM morpheme m
          JOIN gloss g ON g.morpheme_id = m.id AND g.superseded_by IS NULL
         WHERE m.form = ?
         GROUP BY g.text
         ORDER BY n DESC
        """,
        (form,),
    ).fetchall()


def search(connection: sqlite3.Connection, query: str, limit: int = 30) -> list:
    """Full-text search across every verse in the library."""
    return connection.execute(
        "SELECT urn, node_id, text FROM verse_fts WHERE verse_fts MATCH ? LIMIT ?",
        (query, limit),
    ).fetchall()


def verse_payload(connection: sqlite3.Connection, node_id: int) -> dict:
    """Everything the reader panel needs for one verse, as plain data.

    The point of this function: the analysis becomes a *fetched payload* rather than
    141 KB of `data-` attributes inlined into every page.
    """
    tokens = connection.execute(
        "SELECT id, position, text, line FROM token WHERE node_id = ? ORDER BY position",
        (node_id,),
    ).fetchall()
    rows = connection.execute(
        """
        SELECT tm.token_id, m.ordinal, m.form, m.pos, m.etymology, tm.shared,
               g.text AS gloss, g.confidence, g.annotator
          FROM token_morpheme tm
          JOIN morpheme m ON m.id = tm.morpheme_id
          LEFT JOIN gloss g ON g.morpheme_id = m.id AND g.superseded_by IS NULL
         WHERE m.node_id = ?
         ORDER BY tm.token_id, m.ordinal
        """,
        (node_id,),
    ).fetchall()
    by_token: dict[int, list] = {}
    for row in rows:
        entry = {
            "f": row["form"],
            "g": row["gloss"] or "",
            "p": row["pos"] or "",
            "e": row["etymology"] or "",
            "s": row["shared"],
        }
        # Provenance travels with the gloss so a caller can tell a scholar's reading from
        # an inferred one. Omitted when editorial, which keeps the common case small:
        # absence means confidence 1.
        if row["confidence"] is not None and row["confidence"] < 1:
            entry["c"] = row["confidence"]
            if row["annotator"]:
                entry["a"] = row["annotator"]
        by_token.setdefault(row["token_id"], []).append(entry)
    paraphrase = connection.execute(
        "SELECT text FROM paraphrase WHERE node_id = ? LIMIT 1", (node_id,)
    ).fetchone()
    return {
        "tokens": [
            {"t": t["text"], "m": by_token.get(t["id"], [])} for t in tokens
        ],
        "paraphrase": paraphrase["text"] if paraphrase else "",
    }


def statistics(connection: sqlite3.Connection) -> dict:
    """Counts, for asserting that an ingest actually ingested."""
    def one(sql: str) -> int:
        return int(connection.execute(sql).fetchone()[0])

    return {
        "nodes": one("SELECT COUNT(*) FROM node"),
        "verses": one("SELECT COUNT(*) FROM node WHERE kind = 'verse'"),
        "sections": one("SELECT COUNT(*) FROM node WHERE kind = 'section'"),
        "tokens": one("SELECT COUNT(*) FROM token"),
        "morphemes": one("SELECT COUNT(*) FROM morpheme"),
        "distinct_forms": one("SELECT COUNT(DISTINCT form) FROM morpheme"),
        "glosses": one("SELECT COUNT(*) FROM gloss WHERE superseded_by IS NULL"),
        "links": one("SELECT COUNT(*) FROM token_morpheme"),
        "shared_links": one("SELECT COUNT(*) FROM token_morpheme WHERE shared = 1"),
        "paraphrases": one("SELECT COUNT(*) FROM paraphrase"),
    }
