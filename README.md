# Rental Housing Law Navigator

> **Not legal advice.** This tool summarizes public housing law for information only. Check with a qualified
> attorney or tenant organization before acting.

For an apartment address and a date, the Navigator answers: **which rental rules apply here, and what is about to
change?** Every answer shows the source law, a word-for-word quote that code has checked against the source text,
and the date the answer applies. Where a needed building fact is missing, the answer is **Unknown**, never a guess.

Built for the Hack-Nation x RealPage challenge (3 states, 9 cities with sample addresses, 6 rule categories).

## How it works

```
BUILD (LLM agents)                                           QUERY (plain code, no LLM)
corpus ─▶ Extractor ─▶ Verifier ─▶ Consolidator ─▶ Coverage ─▶ Auditor ─▶ KNOWLEDGE BASE ─▶ Evaluator ─▶ answers
          (LLM)        (code:      (LLM: merge,    check       (LLM:       (SQLite/any       (dates, facts,    web app,
                       quote must   link rules)    (LLM,       second       SQL database)     precedence,       JSON files
                       exist)                      verified)   read)                          conflicts)
addresses ─▶ Census Geocoder ─▶ legal city / state stack ─────────────────────────────────────▲
```

* **Extractor (LLM):** reads each document and writes one structured rule per rule, with verbatim quotes.
* **Verifier (code):** every quote must be found in the source text (whitespace/quote-style tolerant). A miss gets
  one repair round that may only choose among real source passages; otherwise the rule is dropped. The stored quote
  is always the raw source text.
* **Consolidator (LLM):** groups candidates into one rule per law, links rules (supersedes / narrow exception /
  possible conflict) and records "no rule at this level" findings. Code rebuilds every final field from verified
  candidates, so this step cannot change a number, date or quote.
* **Coverage check (LLM, verified):** re-reads related documents to fill building conditions (cutoff dates, unit
  thresholds, exemptions) the first pass left unstructured. A result is used only if its quote verifies.
* **Auditor (LLM):** independent second read of each rule against its source; disagreements raise a review flag.
* **Evaluator (code):** three-valued logic over time → coverage → precedence → conflicts. Pending bills and failed
  measures never apply. Missing facts return `unknown` and name the missing fact.

Results: `applies`, `unknown`, `superseded`, `not_yet_effective`, `pending`.

## Run it

```bash
make setup                      # needs uv (https://docs.astral.sh/uv/) and Python 3.12+
cp .env.example .env            # add your API key(s); pick the provider/model
make build-kb                   # ingest -> extract -> consolidate   (calls the LLM; cached in the database)
make outputs                    # geocode, export output/*.json, self-check report
make serve                      # http://127.0.0.1:8765
make test                       # real database, real LLMs, real Census Geocoder (no mocks)
make offline                    # replay everything from the cache with zero network calls
```

### Switching the AI model (`.env`)

One provider-neutral layer (`navigator/llm`) sits behind every model call. Set:

| `LLM_PROVIDER` | Default model | Key |
|---|---|---|
| `anthropic` | `claude-opus-5-5` | `ANTHROPIC_API_KEY` |
| `openai` | `gpt-5` | `OPENAI_API_KEY` |
| `gemini` | `gemini-flash-latest` | `GEMINI_API_KEY` |
| `groq` | `openai/gpt-oss-120b` | `GROQ_API_KEY` |
| `ollama` | `llama3.3` | none (`OLLAMA_BASE_URL`, local) |

`LLM_MODEL` overrides the default. Responses are cached in the database by a hash of provider, model, prompt and
input, so switching models re-runs only what the new model has not already answered.

### Database

SQLite at `data/navigator.db` by default; set `DATABASE_URL` to any SQLAlchemy URL (for example PostgreSQL).
Tables: source library, LLM call cache + audit, rule candidates, knowledge-base versions, rules, no-rule findings,
addresses, HTTP cache, audit events.

## Commands

```
python -m navigator ingest | extract | consolidate | geocode | export | selfcheck | changes | serve
python -m navigator lookup A0016 --as-of 2027-07-02
python -m navigator fetch-supplementary          # optional: link-only sources, robots.txt respected, marked secondary
python -m navigator ingest-new law.txt --jurisdiction "Cambridge, MA" --url https://...   # hour-16 flow
```

`ingest-new` runs the same agents on a newly released law, writes a new knowledge-base version, and appends a
change test (`T6`) listing affected addresses and conflict flags, for today and for the law's effective date.

## Outputs (`output/`)

`rules.json` (schema-valid, with citation and quote), `lookups.json` (all 500 addresses), `changes.json` (T1–T5,
plus any ingested law), `changes_detail.json`, `selfcheck.txt`.

## Web app (`frontend/`, React + TypeScript + Vite)

Product UI only (no challenge tooling). Built into `web/dist` and served by FastAPI at http://127.0.0.1:8765.

* **Search**: address autocomplete over the sample addresses, or any CA/NJ/MA address (geocoded live). A
  renter / housing-provider switch changes the framing ("your rights" vs "your obligations").
* **Address report**: jurisdiction trail (state › county › city), at-a-glance tiles per topic, a status bar, every
  rule grouped by topic with the reason, the citation and the quoted law, and a drawer that shows the source text
  with the quote highlighted.
* **What's changing here**: upcoming effective dates, recent changes and proposed bills for that address, with
  one-click time travel to see the answer on a future date.
* **Improve this answer**: add year built, unit count, government-regulated rent or owner occupancy; the same
  deterministic checks re-run.
* **Building & map**, **quick calculators** (largest increase / deposit / fee from rules that state a clear
  number), **official resources** for the city and state (from the source library, never invented links).
* **Save, share, print**: saved places and recent searches (on this device), shareable URLs that reproduce the
  answer (date and confirmed facts included), print-friendly layout.
* **Compare** up to three addresses side by side, **Law library** to browse and search every rule.
* English / Spanish interface (legal text stays in English), light / dark / system theme, keyboard and
  screen-reader friendly, mobile bottom navigation.

```bash
cd frontend && npm install && npm run build   # -> web/dist
npm run dev                                    # dev server with /api proxied to :8765
npx vitest run                                 # domain logic tests (calculator parsers, timeline)
```

## Deploy

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/AkashDeepSinghJassal/rental-law-navigator)

The `Dockerfile` builds the React UI and serves it with FastAPI and the knowledge base in `data/release.db`
(no API keys needed at runtime). Render: use the button above (`render.yaml`, free plan). Fly.io:
`fly launch --copy-config --no-deploy && fly deploy` (`fly.toml`). Rebuild the release database after a new
knowledge-base build with `python scripts/make_release_db.py`.

## Known limits

* Rules come only from the supplied corpus (54 text documents). Key texts that are link-only (for example several
  New Jersey statutes and the Hoboken and Newark ordinances) are covered only through secondary pages, marked
  lower-confidence and reported separately.
* The sample addresses lack owner type, certificate-of-occupancy dates and (in places) year built or unit counts,
  so many answers are honestly `unknown`.
* The starter pack's `score.py` and dev answer key were not in the download; `selfcheck` is our own stand-in.
* Summaries of law are for scoping and prototyping only. Not reviewed by counsel.
