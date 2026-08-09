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

**77.6% of Telugu words**, measured over 63,125 words across 150 texts. Coverage is
printed on every page, and a word the analyser cannot explain is rendered as plain text
rather than as a clickable word with an empty gloss — a reader who clicks and gets
nothing learns to distrust the glosses that work.

That figure was 26.5% before three things were fixed, and it is worth being precise
that almost all of the gain was correcting mistakes rather than adding capability.

**Most of the "epics" are not Telugu.** Wikisource's ఇతిహాసాలు category is dominated by
the Vālmīki Rāmāyaṇam — Sanskrit, transliterated into Telugu script. Of 396 cached texts
over 400 characters, 341 are Sanskrit. This was corrupting everything: a Telugu analyser
cannot parse Sanskrit, and where it did produce something the gloss was confident
nonsense — the Sanskrit locative `సూర్యే` came back as a habitual participle of an
invented Telugu verb `సూర్యు`. `language.py` separates them by word ending, which is
where the languages differ mechanically: Sanskrit ends words in visarga, a bare
consonant, `-స్య`, `-ేన`, and Telugu never does. The distribution is strongly bimodal —
Telugu under 10%, Sanskrit 21–32% — so the threshold sits in an empty gap. Sanskrit texts
are now presented as text and **labelled as Sanskrit** rather than mis-glossed.

**An uninflected word is not a failure.** The gap test also required a suffix to have
been peeled off, which is simply wrong: most Telugu tokens in running text are
uninflected, so `ఈ` (294,297 occurrences), `మీ` (148,590) and `తన` (111,810) analyse to
themselves, which is the correct answer. Marking them unanalysed made the commonest
words in the language look like gaps.

**Telugu digits were being analysed as words.** `[ఀ-౿]` includes U+0C66–6F, so every
verse number in Telugu numerals went to the analyser — `౩`, `౬౪`, `౨` were among the
commonest "unanalysed words" in the Rāmāyaṇam.

### What still limits it

**Orthography — fixed.** Classical Telugu marks a nasalised vowel with the arasunna (ఁ),
which modern Telugu dropped: 12.5% of classical tokens, against 379 of a modern corpus's
613,429 forms. Folding it is safe — of 251 arasunna forms whose stripped version is also
attested, every one is the same word and there are no minimal pairs.

**Cross-token sandhi — not fixed.** Classical verse writes sandhi *across* the word
boundary and breaks lines on the metrical foot, so `పురుషుండు ఆఢ్యుఁడు` prints as
`పురుషుం డాఢ్యుఁడు`. The printed token is the tail of one word plus the head of the next,
and no morphology parses it because it is not a word. This is most of the remaining 22%.

**A classical lexicon helps less than expected.** `classical_lexicon.py` harvests
vocabulary from the corpus itself — a word is admitted if it recurs across two texts or
occurs five times overall. It correctly admits `తతః`, `వాల్మీకి`, `నృపతి` and refuses the
fragment `డాఢ్యుఁడు`, but its measured contribution is only 0.1–1.0 points now that the
bugs above are fixed. Recorded because the idea sounds better than it measures.

### On dictionaries

[andhrabharati.com](https://andhrabharati.com/dictionary/) is the best Telugu dictionary
aggregator there is, and it was investigated as a data source. Its lookup is a
JavaScript POST to `getWM.php` carrying a session token, and the site states "All rights
reserved" over 94 dictionaries licensed individually from publishers — so copying their
definitions into a public static site would redistribute material under permissions
granted to someone else. The word panel **links out to it per lemma** instead, which is
what it is for and costs it nothing.

## Read it locally

```sh
pip install git+https://github.com/sree-revoori1/telugu-morph
git clone https://github.com/sree-revoori1/telugu-library && cd telugu-library

PYTHONPATH=src python3 -m telugu_library.build      # a sample, ~1 minute
PYTHONPATH=src python3 -m telugu_library.serve      # → http://localhost:8765/
```

`--all` builds all 4,842 texts. Every fetched page is cached, so a build is resumable —
necessary, because fetching is rate-limited out of courtesy to a donated service, and the
first full run takes a few hours.

## Publish it

The site is a folder of static files, so it hosts anywhere. **This repository is
private, which rules out GitHub Pages** — Pages needs a public repository on the free
plan. Two paths that work regardless:

**Cloudflare Pages** (free, private source, custom domain, one command):

```sh
PYTHONPATH=src:../telugu-morph/src python3 -m telugu_library.build --all
npx wrangler pages deploy site --project-name telugu-library
```

**Netlify** (same idea):

```sh
netlify deploy --dir=site --prod
```

Either gives a public URL while the code stays private. If you would rather use GitHub
Pages, make the repository public and add a deploy step — the workflow is one job away
from it, and the commit history explains what to add.

### The CI build

`.github/workflows/build.yml` runs the tests, builds every text, and uploads the site as
a downloadable artifact on each push and weekly. It deliberately does *not* deploy, for
the reason above.

It needs one secret, because telugu-morph is also private:

1. Create a fine-grained personal access token with **read** access to `telugu-morph`.
2. Add it to this repository as **Settings → Secrets and variables → Actions → New
   repository secret**, named `ACCESS_TOKEN`.

The default `GITHUB_TOKEN` will not do: it is scoped to this repository alone and cannot
read another private one. Without the secret the build fails at checkout with `could not
read Username for 'https://github.com'`.

The workflow caches the fetched corpus, so only the first run pays the several-hour
fetch, and the weekly rebuild exists because Wikisource is edited continuously.

## Layout

```
src/telugu_library/
  wikisource.py   fetching, with provenance and the User-Agent Wikimedia requires
  catalogue.py    walking the category tree into a list of works
  reader.py       text → parsed document, verse preserved, tokens analysed
  language.py     Telugu vs Sanskrit-in-Telugu-script, by word ending
  classical_lexicon.py  vocabulary harvested from the corpus itself
  site.py         static HTML: the reading page and the word panel
  build.py        fetch, parse, render
  serve.py        read it locally
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
words. Checking that the lemma is attested is what separates a gloss from a guess.

**Check what language the text is in before analysing it.** 86% of the cached corpus is
Sanskrit in Telugu script, and a Telugu analyser does not fail cleanly on it — it returns
confident nonsense. This was the single largest error in the project and it was invisible
until the glosses were read rather than counted.

**Averaging a metric across two languages describes neither.** Coverage is reported for
Telugu texts only, with Sanskrit counted separately.

## Licence

Code MIT. Texts from Telugu Wikisource under
[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/), attributed per page;
the generated site carries the same licence for the text it contains.
