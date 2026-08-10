# తెలుగు గ్రంథాలయం — a parsing reader for Telugu literature

Telugu's classical canon is online as plain text, and almost unusable as a result.
The verse is there, but the language is 500 to 1,000 years old, heavily
Sanskritised, and written in an orthography modern readers were never taught. A
student who can read a Telugu newspaper cannot read Pothana without a teacher.

This is [ancientlibrary.net](https://ancientlibrary.net)'s idea applied to Telugu:
**click any word for its lemma, morphology and part of speech.** The analysis is
computed at build time by [telugu-morph](https://github.com/sree-revoori1/telugu-morph),
so the site is static — it hosts free, works offline, and has no backend to fail.

```
కం. పురుషుం డాఢ్యుఁడు ప్రకృతికిఁ , బరుఁ డవ్యయుఁ డఖిల భూత బహిరంతర్ భా
                      ╰─ ప్రకృతి   noun<dat>
```

## What is in it

**Pothana's Telugu Bhāgavatam, complete and annotated** — all 14 skandhams:

| | |
|---|---|
| Sections | 374 |
| Verses | **5,535** |
| Morphemes with a Telugu meaning | **190,483 — 100%** |
| Clickable words | 147,074 |
| Tokens with no gloss | 1.2% |

Every verse carries three layers, all from the source:

1. the verse as Pothana set it, in its metre
2. **`టీక`** — a morpheme-by-morpheme Telugu gloss, sandhi and compounds already split
3. **`భావము`** — a prose paraphrase of the whole verse

Texts from [Telugu Wikisource](https://te.wikisource.org) under CC BY-SA 4.0, attributed
per page. Wikisource rather than archive.org deliberately: archive.org's ~12,887 Telugu
texts are overwhelmingly page scans, and Telugu OCR loses exactly the conjuncts and matras
that carry meaning.

## Why the editorial gloss, and not a morphological analyser

This began by running [telugu-morph](https://github.com/sree-revoori1/telugu-morph) over
classical verse. It reached 26% coverage and the failures were not fixable by better
rules, because classical printing breaks lines on the *metre*, not the word:

```
పరికరస్యందనారూఢుం  డగు          as printed — two tokens
పరికర స్యందన ఆరూఢుండు అగున్      as the editor separates it — four morphemes
```

The `డ` that opens the second token is the final consonant of `ఆరూఢుండు`. No amount of
sandhi reversal recovers that reliably, and a wrong gloss on a scriptural line is worse
than none.

Wikisource's Bhāgavatam already carries a scholar's word-by-word gloss. Using it is
strictly better than computing a worse one, so the analyser is not used here at all.

## How the alignment works

The gloss lists morphemes in reading order; the problem is mapping them to printed tokens.
Three approaches failed before the right one, and the reasons are worth stating:

| approach | why it failed |
|---|---|
| count codepoints | Telugu is an abugida — `జేరుటకునై` is 9 codepoints, 5 aksharams |
| count aksharams, greedily | one token over-consuming shifts every later token; clicking a word showed the **next** word's breakdown |
| global DP over aksharams | stopped the cascade but assumed morphemes fit inside tokens — 78% |
| **align character streams** | **0% unplaced** |

The verse with spaces removed and the morphemes concatenated are 88% identical, because
sandhi alters only the seams. A standard longest-common-subsequence match then decides the
correspondence, and a morpheme spanning a token boundary is shown under both tokens —
which is what the text actually does.

One structural fact had to be encoded too: a **sīsa padyam and its āṭaveladi companion are
one verse**. The source writes them as two ids (`తెభా-1-34-సీ.`, then `తెభా-1-34.1-ఆ.`)
and only the second carries a gloss, covering both halves. Parsed separately, the sīsa was
dropped and the continuation received a gloss twice the length of its text. That single
issue was the whole of the residual 6.2%.

## The data layer

The analysis lives in **`data/library.db`**, a SQLite store between alignment and
rendering. Before it existed the morphemes were only `data-` attributes inside 687
generated HTML files averaging 141 KB, which made the site the database — so search
across texts, correcting one gloss, accepting an emendation, versioning an annotation,
serving an API and exporting CoNLL-U were each a rewrite of `site.py` rather than a query.

```
wikisource cache → ingest → library.db → render → site/
```

| | |
|---|---|
| Verses | 8,980 |
| Tokens | 230,909 |
| Morphemes | 293,555 |
| Token↔morpheme links | 338,098 (**87,636 shared across a line break**) |
| Distinct morpheme forms | 74,566 |

The shape follows Perseus' Scaife ATLAS, because it solves the problem this text has:
**overlapping hierarchies.** A verse is a unit of citation, a line is a unit of printing,
and a word belongs to both without either containing the other.

Four decisions that are expensive to reverse:

1. **Materialized path** on `node` (`corpus → work → book → section → verse`), so a
   subtree is one indexed prefix match rather than a recursive query.
2. **Layers join to token and morpheme *ids*, never character offsets.** The cautionary
   case is VedaWeb: ~13 layers aligned positionally, and 63 of 428 stanzas in Book 2 now
   disagree about their own token count. Ids cannot drift; offsets do the moment someone
   fixes a typo.
3. **`token_morpheme` is many-to-many.** TEITOK's `<tok>`/`<dtok>` is the right model but
   assumes each morpheme nests inside one token. Ours cannot: `ఆరూఢుండు` has characters in
   both `పరికరస్యందనారూఢుం` and `డగు`. A tree would force a wrong parent — the exact bug
   that made three earlier aligners useless — so the link is its own row, carrying `shared`.
4. **Provenance and confidence on every gloss.** Editorial `టీక`, dictionary lookup,
   computed guess and human correction coexist in one table and stay distinguishable, and
   a correction supersedes rather than overwrites, so history survives.

**The store immediately caught a miscount.** Wikisource's section boundaries overlap: 32
verses are printed on two pages apiece, because a story's boundary is editorial and both
sections claim the verses that straddle it. 8,980 distinct + 32 repeats = the **9,012**
this project had been reporting, which the HTML pipeline had no way to notice.

Pages are now **41 KB, down from 141 KB**, because the analysis is fetched per section
instead of inlined per word. That makes it an API by construction — `data/<slug>.json` is
already what a client would ask for.

```sh
PYTHONPATH=src python3 -m telugu_library.ingest --all            # → data/library.db
PYTHONPATH=src python3 -m telugu_library.build_from_store        # → site/
```

## Read it locally

```sh
git clone https://github.com/sree-revoori1/telugu-library && cd telugu-library

PYTHONPATH=src python3 -m telugu_library.build_bhagavatam --all   # or --skandham 1
PYTHONPATH=src python3 -m telugu_library.serve                    # → http://localhost:8765/
```

No dependencies beyond the standard library. Every fetched page is cached, so a rebuild
costs nothing and the first fetch is resumable.

Click any underlined word: the panel shows each morpheme inside it with the editor's
meaning. The indented line under each verse is the `భావము` paraphrase.

## Publish it

`site/` is the whole artifact — 57 MB of static files, no backend. **This repository is
private, which rules out GitHub Pages** on the free plan. Two paths that keep the source
private:

```sh
npx wrangler pages deploy site --project-name telugu-library   # Cloudflare Pages
netlify deploy --dir=site --prod                               # Netlify
```

Both give a public URL. `.github/workflows/build.yml` builds and uploads the site as a CI
artifact on each push; it needs an `ACCESS_TOKEN` secret only if you re-enable the
telugu-morph dependency, which the Bhāgavatam pipeline does not use.

## On dictionaries

[andhrabharati.com](https://andhrabharati.com/dictionary/) is the best Telugu dictionary
aggregator there is, and it was used to add part of speech and etymology on top of the
gloss. That reached 8% before the site began refusing requests, and it has not been worked
around — the block is a clear signal and this is a donated scholarly resource. The word
panel links out to it per morpheme instead.

The failure mode is worth recording: with this project's User-Agent the site returns
**HTTP 200 with an empty body**, which is indistinguishable from "no results found". 325
words were silently cached as nonexistent, including `ముని` and `వేదము`. Those entries were
purged and refusals now raise rather than being recorded as absences.

## Layout

```
src/telugu_library/
  wikisource.py     fetching, with provenance and the User-Agent Wikimedia requires
  bhagavatam.py     verse parsing, the టీక gloss, and character-stream alignment
  store.py          the SQLite annotation store — hierarchy, tokens, morphemes, layers
  ingest.py         cached pages → library.db
  render.py         library.db → static pages + fetched analysis payloads
  build_from_store.py   the build, in three separable stages
  site.py           shared CSS and the older inline-payload renderer
  serve.py          read it locally
  catalogue.py      the wider Wikisource catalogue, 4,842 texts
  language.py       Telugu vs Sanskrit-in-Telugu-script, by word ending
  andhrabharati.py  dictionary lookup, cached permanently
data/bhagavatam-pages.json   the 912 Bhāgavatam pages
data/library.db              the annotation store
```

## Notes for anyone touching this

**A Telugu title cannot be a filename.** Percent-encoding it makes every character
nine ASCII bytes, so a normal chapter heading exceeds the 255-byte limit and the write
fails with ENAMETOOLONG. Cache keys are hashes.

**Wikimedia returns 403 without a descriptive User-Agent.** Not a rate limit — a bare
`urllib` call simply fails.

**The category graph has cycles.** A subcategory can list its own parent, so traversal
needs a visited set; a plain recursion does not return.

**Four identical measurements mean the code is not running.** After changing the verse-id
pattern three times and seeing byte-identical metrics each time, the honest conclusion was
that the edit was not reaching the parse — not that the pattern needed a fourth try. It
turned out an unglossed verse was being discarded before the code that needed it could run.

**A parse is not a gloss.** A sandhi-split fragment analyses perfectly happily —
`డాఢ్యుఁడు` yields the "lemma" `డాఢ్యుడు`, which occurs zero times in 33 million
words. Checking that the lemma is attested is what separates a gloss from a guess.

**Check what language the text is in before analysing it.** 86% of the cached corpus is
Sanskrit in Telugu script, and a Telugu analyser does not fail cleanly on it — it returns
confident nonsense. This was the single largest error in the project and it was invisible
until the glosses were read rather than counted.

**Averaging a metric across two languages describes neither.** Coverage is reported for
Telugu texts only, with Sanskrit counted separately.

**A UNIQUE constraint is a measurement.** Adding one on `node.urn` immediately found 32
verses being counted twice, which had been inflating the headline verse figure for weeks.
The HTML pipeline wrote each page independently and so could not have noticed. Where a
number matters, give the store a way to refuse the wrong one.

**One verse's gloss describes more text than the verse prints.** `bhagavatam:4.969` has
5 printed tokens and 18 morphemes, so 22 morphemes across the corpus (0.01%) attach to no
token. This is a source quirk, not an alignment failure — the old pipeline dropped them
silently, and the store keeps them queryable instead.

## Licence

Code MIT. Texts from Telugu Wikisource under
[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/), attributed per page;
the generated site carries the same licence for the text it contains.
