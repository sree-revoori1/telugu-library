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

4,842 texts from [Telugu Wikisource](https://te.wikisource.org), traversed from its
category tree:

| | |
|---|---|
| కవిత్వము — poetry | 1,290 |
| ఇతిహాసాలు — epics (Mahābhāratam, Rāmāyaṇam) | 1,082 |
| సంకీర్తనలు — devotional song | 928 |
| పురాణాలు — Purāṇas (Pothana's Bhāgavatam) | 752 |
| వేదాలు — Vedic and philosophical | 625 |
| శతకములు — hundred-verse sequences | 117 |
| నాటకాలు — drama | 48 |

Wikisource rather than archive.org, deliberately. Archive.org has some 12,887
Telugu texts, but they are overwhelmingly page scans with OCR, and Telugu OCR loses
exactly what matters — conjuncts and matras. A reader built on it would quote
errors. Wikisource's texts are hand-edited Unicode, with the verse markers (`కం.`,
`వ.`) and canonical verse numbers (`1-185`) intact, so a quotation stays citable.

## How much is actually glossed

**26.5% of words, measured over 21 texts of 100+ tokens.** This is the number to
judge the project by and it is not good yet:

| genre | glossed |
|---|---|
| నాటకాలు — drama | 45.4% |
| పురాణాలు — Purāṇas | 38.9% |
| కవిత్వము — poetry | 28.7% |
| శతకములు — śatakams | 26.7% |
| ఇతిహాసాలు — epics | **7.3%** |

The gradient is the story: drama is close to modern spoken Telugu, and the 11th-century
epics are furthest from it. Coverage is printed on every page, and a word the analyser
cannot explain is rendered as plain text rather than as a clickable word with an empty
gloss — a reader who clicks and gets nothing learns to distrust the glosses that work.

### Why it is 26% and not 90%

Two causes, both measured, and only one is fixed.

**Orthography — fixed.** Classical Telugu marks a nasalised vowel with the arasunna
(ఁ), which modern Telugu dropped. It appears in 12.5% of classical tokens and in 379
of a modern corpus's 613,429 forms, so nearly every classical word missed the lexicon
by one codepoint. Folding it is safe — of 251 arasunna forms whose stripped version is
also attested, every one is the same word (తెలుఁగు/తెలుగు, కుమారుఁడు/కుమారుడు) and
there are no minimal pairs. This took decomposition from 11.6% to 14.9%.

**Tokenisation — not fixed, and the larger problem.** Classical verse writes sandhi
*across* the word boundary and breaks lines on the metrical foot, so `పురుషుండు
ఆఢ్యుఁడు` is printed as `పురుషుం డాఢ్యుఁడు`. The printed token is the tail of one
word plus the head of the next, and no amount of morphology will parse it, because it
is not a word. Moving the initial consonant back does recover real words — `పురుషుండు`
is attested — but the recovered halves are largely Sanskrit vocabulary that a corpus of
Wikipedia and newspapers does not contain.

So the ceiling is set by the lexicon, not the grammar. Raising it needs a classical
lexicon: a Sanskrit-Telugu vocabulary and a cross-token sandhi resolver. Both are real
work and neither is done.

## Build it

```sh
pip install git+https://github.com/sree-revoori1/telugu-morph
python -m telugu_library.build            # a sample, for checking the layout
python -m telugu_library.build --all      # all 4,842 texts
```

Every fetched page is cached, so a build is resumable — necessary, because fetching is
rate-limited out of courtesy to a donated service.

## Layout

```
src/telugu_library/
  wikisource.py   fetching, with provenance and the User-Agent Wikimedia requires
  catalogue.py    walking the category tree into a list of works
  reader.py       text → parsed document, verse preserved, tokens analysed
  site.py         static HTML: the reading page and the word panel
  build.py        fetch, parse, render
data/catalogue.json   the 4,842 works, so a rebuild needs no re-traversal
```

## Notes for anyone touching this

**A Telugu title cannot be a filename.** Percent-encoding it makes every character
nine ASCII bytes, so a normal chapter heading exceeds the 255-byte limit and the write
fails with ENAMETOOLONG. Cache keys are hashes.

**Wikimedia returns 403 without a descriptive User-Agent.** Not a rate limit — a bare
`urllib` call simply fails.

**The category graph has cycles.** A subcategory can list its own parent, so traversal
needs a visited set; a plain recursion does not return.

**A parse is not a gloss.** A sandhi-split fragment analyses perfectly happily —
`డాఢ్యుఁడు` yields the "lemma" `డాఢ్యుడు`, which occurs zero times in 33 million
words. Checking that the lemma is attested is what separates a gloss from a guess, and
without it the site reported 19.1% coverage where the honest figure was 16.5%.

## Licence

Code MIT. Texts from Telugu Wikisource under
[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/), attributed per page;
the generated site carries the same licence for the text it contains.
