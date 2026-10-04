# Rental Housing Law Navigator: Architecture and Build Spec

Audience: a coding sub-agent that will implement and test the system. Read sections 0-3 in full before writing code. Then build the milestones in section 5 in order. Do not start a milestone until the previous one's tests pass.

Sources this spec is derived from: `housing.pdf` (challenge brief) and `starter_pack/participant-final-no-hour16 3/README.md` (participant guide), plus the starter pack's schema, templates and data.

---

## 0. Hard rules (never break these)

1. **No hand-coded rules.** Every rule in `rules.json` must come from the LLM reading a corpus document. Do not write rule content (citations, numbers, dates, coverage cutoffs) into code or config. Test fixtures and test expectations may contain legal facts; pipeline code and outputs may not.
2. **No unverified quotes.** A rule enters the knowledge base only if its `quoted_span` is found in its source text by code (section 3.3).
3. **Never guess.** If a rule's coverage depends on a fact the data does not have, the result is `unknown`, with the missing fact named. Never silently omit a rule that might apply. Missing an applicable rule costs twice as much as other errors in scoring.
4. **No LLM at query time.** Lookups and change tracking are deterministic code over the knowledge base, so they are reproducible.
5. **Pending and failed law never applies.** Bills are `pending`. Struck or failed measures are `failed` and never appear as `applies`.
6. **Every interface and every output says "Not legal advice."**
7. **Public data only.** No scraping that violates a site's terms. Do not copy code from other teams' public repos for this event.
8. **Reproducible.** Every model call and every geocoder call is cached on disk. A full rerun from the cache must make zero network calls and produce byte-identical outputs.

---

## 1. Inputs (what exists on disk)

Root: `/Users/akashdeep/mycode/hackathon/hack7`. Create a symlink `starter -> "starter_pack/participant-final-no-hour16 3"`, since the folder name contains a space.

| Path (under `starter/`) | Contents | Notes |
|---|---|---|
| `corpus/corpus_manifest.csv` | 87 rows: `doc_id, jurisdictions, url, source_type, capture, retrieved_at, sha256, text_file, status` | `jurisdictions` is `CA`, `NJ`, `MA` or `City, ST` (13 jurisdictions incl. Santa Ana). `status` = `ok` or `link-only`. |
| `corpus/text/D###.txt` | 54 text files. The first two lines are `SOURCE: <url>` and `RETRIEVED: <date> UTC`, followed by a blank line and the body. | Sizes run from 164 to 26,016 words. D067 (NJ DCA Truth in Renting) is the largest. |
| `corpus/links_only.csv` | 33 sources with no text: law-firm and news pages, Justia mirrors of key NJ/CA statutes, ecode360 pages for Hoboken and Newark, and amlegal for LA | Rules from these cannot be quoted. See section 6, risk R1. |
| `data/sample_addresses.csv` | 500 rows: `address_id, street_address, postal_city, state, zip, year_built, units, use_code, use_description, source_dataset, retrieved_at` | Counts: CA 250, NJ 140, MA 110. Missing year_built: CA 98, NJ 106, MA 8. Missing units: CA 43, NJ 139, MA 60. Postal cities include neighborhoods (Dorchester, Allston, Brighton, Roxbury, East Boston, San Ysidro, ...). Some Cambridge rows have an empty `zip`. |
| `schema/rule_record.schema.json` | Required: `team_rule_id, jurisdiction, level (state or city), category (6 enums), status (in_force, not_yet_effective, pending, failed), title, requirement, citation, source_url, quoted_span (minLength 20)`. Optional: `key_value, coverage_conditions (string, object or null), exemptions, overrides[], interaction, effective_date (YYYY[-MM[-DD]]), source_doc_id, confidence, conflict_flag, conflict_note` | `level` has no `county`. |
| `dev/change_tests.json` | T1-T5 with answer-key rule ids (`CA-ALG-01`, `HOB-ALG-01`, `JC-ALG-01`, `NJ-ALG-01`, `MA-ALG-P1`, `MA-ALG-P2`, `MA-RENT-P1`), dates and expected behavior | T6 (a fictional Cambridge ordinance) is released at hour 16. |
| `submission_templates/` | Shapes for `rules.json` (`{"rules":[...]}`), `lookups.json` (`{"as_of", "lookups":{address_id:[{team_rule_id, result, explanation, conflict_flag}]}}`) and `changes.json` (`{test_id:{affected_address_ids, conflict_flag_address_ids, notes}}`) | |

**Not in the pack** (despite the brief): `score.py` and the dev answer key. Section 4 defines our own self-check to replace them. If the organizers release them, wire them into `make score`.

Categories: `rent_increase_limits, just_cause_eviction, security_deposits, application_screening_fees, screening_restrictions, algorithmic_rent_setting`.

Lookup result values: `applies, unknown, superseded, not_yet_effective, pending`. Leave out rules that don't apply. Default query date: `2026-10-01`.

---

## 2. Architecture

### 2.1 Overview

```
 BUILD TIME (offline, LLM agents)                                   QUERY TIME (deterministic code)
 ───────────────────────────────                                    ───────────────────────────────
 corpus_manifest.csv + text/   ─▶ [A0 Ingest]  ─▶ Source Library ─┐
                                                                   │
                                 [A1 Extractor agent, LLM] ◀──────┤ per document (or section chunk)
                                         │ candidate rules + quotes
                                         ▼
                                 [A2 Verifier, CODE] ── fail ─▶ 1 repair call (LLM) ─▶ re-verify ─▶ drop + log
                                         │ verified candidates
                                         ▼
                                 [A3 Consolidator agent, LLM]   per jurisdiction × category:
                                         │  merge duplicates, set precedence links,
                                         │  emit "no rule at this level" findings
                                         ▼
                                 [A4 Auditor agent, LLM]  independent re-read of coverage
                                         │  and dates; disagreements → conflict_note
                                         ▼
                                 ┌──────────────────────── KNOWLEDGE BASE (kb/) ─────────────────────────┐
                                 │ sources.jsonl │ rules.jsonl │ no_rule.jsonl │ jurisdictions.json │      │
                                 │ versions/     │ audit.jsonl │ test_rule_map.json                   │      │
                                 └────────────────────────────────────────────────────────────────────┘
                                         ▲                                    │
 sample_addresses.csv ─▶ [B1 Facts normalizer, CODE] ─▶ [B2 Resolver, CODE: Census] ─▶ address stack
                                                                              │
                                                     [B3 Evaluator, CODE] ◀───┘ reads KB, as-of date
                                                              │
                              ┌───────────────────────────────┼──────────────────────────────┐
                              ▼                               ▼                              ▼
                        lookups.json                    [C1 Change tracker]            web UI / CLI lookup
                                                         T1–T6 → changes.json
 new ordinance (hour 16) ─▶ ingest-new: A0→A1→A2→A3→A4 on one doc ─▶ new KB version ─▶ re-run B3 + C1
```

### 2.2 Component contract

| Id | Component | Type | Input | Output | Guardrail |
|---|---|---|---|---|---|
| A0 | Ingest | code | manifest and text files | `kb/sources.jsonl` | sha256 checked against the manifest; header lines stripped, body offsets recorded |
| A1 | Extractor | LLM | one document (or chunk), its manifest jurisdictions, category list | candidate rules (Pydantic) with quotes for the rule, effective date and key value | structured output schema; jurisdiction limited to the doc's manifest list; the prompt names no specific law |
| A2 | Verifier | code | candidate and source text | verified candidate with char offsets, or dropped | normalized exact match; one repair round; fuzzy snap ≥ 0.92 replaced by real source text; else drop |
| A3 | Consolidator | LLM | all verified candidates for one jurisdiction (all categories) and the parent state's rules | final rules, precedence links, no-rule findings | may only merge and link existing candidates, never create rule content; every no-rule finding needs a verified quote or is marked `evidence: none` |
| A4 | Auditor | LLM | one final rule and its source passage | agree, or a list of disagreements | disagreements go to `conflict_note` and lower `confidence`; never silently edits |
| B1 | Facts normalizer | code | address row | `BuildingFacts` (year_built, units, unit_range, use_code class, missing list) | derived facts are tagged `derived`, never `observed` |
| B2 | Resolver | code | address | `JurisdictionStack` (state, county, legal city, geocode confidence) | Census Geocoder, cached; house-number check; postal city is never trusted alone |
| B3 | Evaluator | code | stack, facts, KB, as_of | list of `LookupResult` | three-valued logic; missing fact → unknown |
| C1 | Change tracker | code | test definitions, KB versions | `changes.json` | before/after diff from the evaluator only |

### 2.3 Tech stack

- Python 3.11+, managed with `uv`. Dependencies: `anthropic`, `pydantic>=2`, `jsonschema`, `httpx`, `rapidfuzz`, `typer`, `fastapi`, `uvicorn`, `pytest`, `ruff`.
- Model: `claude-opus-5-5` for A1, A3 and A4. Set `output_config={"effort": "high"}` explicitly, because the default on this model is `medium`. Keep adaptive thinking (the default). Do not pass `thinking: disabled`, `budget_tokens` or `temperature`; they return 400 on this model.
- Structured output: `client.messages.parse(model=..., max_tokens=16000, output_format=<PydanticModel>, ...)` and read `response.parsed_output`. Check `response.stop_reason` before trusting the output: `refusal` or `max_tokens` means log the call and retry (for `max_tokens`, re-chunk smaller). Do not use the Citations API together with structured outputs; they are incompatible (400).
- Auth: zero-arg `anthropic.Anthropic()`. It resolves `ANTHROPIC_API_KEY` or an `ant auth login` profile.
- Concurrency: a thread pool of `NAVIGATOR_MAX_PARALLEL` (default 4). The SDK's default `max_retries=2` covers 429 and 5xx errors.
- Prompt caching: keep the system prompt and schema byte-stable (no timestamps), and put the document last. Check `usage.cache_read_input_tokens > 0` on the second call.
- If any SDK call shape here doesn't match the installed SDK, check the SDK docs and fix it. Do not guess.

### 2.4 Repository layout

```
hack7/
  starter -> "starter_pack/participant-final-no-hour16 3"
  pyproject.toml  Makefile  README.md
  navigator/
    __init__.py
    config.py        # paths, AS_OF_DEFAULT, MODEL, PROMPT_VERSION, CATEGORIES, IN_SCOPE_CITIES
    models.py        # all Pydantic models (section 3.1)
    corpus.py        # A0
    llm.py           # cached client wrapper + audit log
    prompts.py       # system prompts for A1, A3, A4, repair
    extract.py       # A1
    verify.py        # A2
    consolidate.py   # A3
    auditor.py       # A4
    kb.py            # read/write knowledge base, versions, stable ids
    facts.py         # B1
    geo.py           # B2
    evaluate.py      # B3
    changes.py       # C1 + test_rule_map
    export.py        # rules.json / lookups.json / changes.json + schema validation
    selfcheck.py     # section 4.3
    cli.py           # typer app (section 2.6)
  web/  app.py  static/index.html      # milestone M7
  kb/                                  # generated knowledge base (committed)
  cache/llm/  cache/geo/               # committed for offline replay
  output/  rules.json lookups.json changes.json selfcheck.txt
  tests/  unit/  integration/  fixtures/
```

### 2.5 Knowledge base (kb/)

The KB is the system's core asset. It is plain JSON Lines so it can be diffed and audited.

| File | One record per | Key fields |
|---|---|---|
| `sources.jsonl` | corpus document | `doc_id, jurisdictions[], url, source_type (official, secondary, code publisher), capture, retrieved_at, sha256, text_path, body_offset, word_count, has_text` |
| `rules.jsonl` | final rule (superset of the schema) | all schema fields, plus `enacted: bool`, `instrument: statute, ordinance, regulation, bill, ballot_measure, agency_guidance`, `effective_date_span`, `key_value_span`, `quote_offsets: {doc_id, start, end}`, `coverage: Coverage` (section 3.1), `supersedes: [rule_id]`, `yields_to: [rule_id]`, `may_conflict_with: [rule_id]`, `secondary_source: bool`, `extracted_by: {call_hash, model, prompt_version}`, `kb_version_added` |
| `no_rule.jsonl` | (jurisdiction, category) cell with no rule | `jurisdiction, category, finding (for example "state bars local rent control"), citation, quoted_span (or null), evidence: quoted or none` |
| `jurisdictions.json` | jurisdiction | `{ "San Francisco, CA": {"state": "CA", "level": "city", "census_place_names": ["San Francisco city"]}, ... }`. Built from the manifest and Census place names (data, not law). |
| `test_rule_map.json` | answer-key test rule id | `{ "CA-ALG-01": "r-0012", ... }`. Generated by matching (jurisdiction, category, citation keywords from the test title). Review it by hand and commit it. It is test configuration, not rule content. |
| `versions/vNNN.json` | KB build | `{version, created_at, prompt_version, model, rule_ids[], source_sha256s[], parent}` |
| `audit.jsonl` | pipeline event | `{ts, stage, doc_id, call_hash, cache_hit, model, usage, decision, reason}`. Stages: extract, verify_pass, verify_repair, verify_snap, verify_drop, consolidate, audit, export. |

**Stable ids.** `team_rule_id = "r-" + 4-digit index` over rules sorted by `(state, level, jurisdiction, category, citation, effective_date)`. Ids must not change between reruns unless the rule set changes.

### 2.6 CLI (all through `uv run python -m navigator <cmd>`)

| Command | Does |
|---|---|
| `ingest` | A0 |
| `extract [--doc D023]` | A1 and A2 over all docs or one doc |
| `consolidate` | A3 and A4, then writes a new KB version |
| `geocode` | B1 and B2 for all 500 addresses, cached into `data/resolved_addresses.json` |
| `evaluate --as-of 2026-10-01 [--out path]` | B3 for all addresses |
| `lookup A0016 [--as-of DATE]` | prints one address's answer with citations |
| `changes` | C1, all tests |
| `ingest-new path.txt --jurisdiction "Cambridge, MA" --url URL [--retrieved DATE]` | the hour-16 flow (section 3.9) |
| `export` | writes and validates `output/*.json` |
| `selfcheck` | section 4.3, writes `output/selfcheck.txt` |
| `run-all` | ingest, extract, consolidate, geocode, evaluate, changes, export, selfcheck |

Env: `NAVIGATOR_OFFLINE=1` makes any cache miss raise an error, for replay and CI. `NAVIGATOR_MAX_PARALLEL=4`.

---

## 3. Component specs

### 3.1 Data models (`models.py`)

```python
Category = Literal[
    "rent_increase_limits",
    "just_cause_eviction",
    "security_deposits",
    "application_screening_fees",
    "screening_restrictions",
    "algorithmic_rent_setting",
]
Fact = Literal[
    "year_built",
    "units",
    "owner_type",
    "certificate_of_occupancy",
    "use_type",
    "new_construction_filing",
    "owner_occupied",
    "subsidized",
    "other",
]


class Coverage(BaseModel):  # what the evaluator tests; all optional
    applies_to: str  # plain text summary, for display
    min_units: int | None = None  # rule covers buildings with units >= min_units
    max_units: int | None = None
    built_before: str | None = None  # ISO date; building must be built/certified BEFORE this
    built_after: str | None = None
    cutoff_basis: Literal["year_built", "certificate_of_occupancy", "unknown"] | None = None
    exemptions: list["Exemption"] = []
    requires_facts_not_in_data: list[Fact] = []  # coverage turns on facts we never have
    coverage_span: str | None = None  # verbatim quote supporting the cutoff/threshold


class Exemption(BaseModel):
    description: str
    max_units: int | None = None  # exemption only possible at or below this many units
    min_units: int | None = None
    built_after: str | None = None  # e.g. new-construction exemptions
    depends_on: list[Fact] = []  # facts needed to decide it


class CandidateRule(BaseModel):  # A1 output, one per rule
    jurisdiction: str  # must be one of the doc's manifest jurisdictions
    level: Literal["state", "city"]
    category: Category
    instrument: Literal["statute", "ordinance", "regulation", "bill", "ballot_measure", "agency_guidance"]
    enacted: bool  # False for bills / proposals / ballot questions
    failed: bool = False  # vetoed, struck, rejected
    title: str
    requirement: str  # 1–2 plain-language sentences
    key_value: str | None
    key_value_span: str | None  # verbatim quote containing the number/formula
    effective_date: str | None  # YYYY[-MM[-DD]]
    effective_date_span: str | None  # verbatim quote stating the date, null if none
    sunset_date: str | None = None
    citation: str
    quoted_span: str  # verbatim, >= 20 chars, supports the requirement
    coverage: Coverage
    interaction: str | None  # e.g. "yields to local rent control"
    preempts_or_preempted_by: str | None
    confidence: float


class ExtractionResult(BaseModel):
    rules: list[CandidateRule]
    categories_mentioned_without_rule: list[Category]  # feeds no-rule findings


class BuildingFacts(BaseModel):
    year_built: int | None
    units: int | None
    units_range: tuple[int | None, int | None] | None  # derived from use_code (section 3.6)
    use_code: str | None
    use_description: str | None
    missing: list[Fact]
    derived: list[Fact]


class JurisdictionStack(BaseModel):
    state: str
    county: str | None
    city: str | None  # city = "San Francisco, CA" or None if outside scope
    census_place: str | None
    method: Literal["batch", "oneline", "coordinates", "postal_fallback"]
    confidence: float
    note: str | None


class LookupResult(BaseModel):
    team_rule_id: str
    result: Literal["applies", "unknown", "superseded", "not_yet_effective", "pending"]
    explanation: str
    conflict_flag: bool
    missing_facts: list[Fact] = []
```

Export maps `rules.jsonl` to the schema. `status` is computed at `2026-10-01`. `coverage_conditions` holds the `Coverage` object dumped to a dict. `exemptions` is a joined string. `overrides` is `supersedes + yields_to`, and `interaction` is text stating the direction.

### 3.2 A0 Ingest (`corpus.py`)

1. Read the manifest. For `status == ok`, read the text file, verify its sha256 against the manifest (log a mismatch but continue), and split the header (`SOURCE:` and `RETRIEVED:` lines) from the body. Keep the raw body exactly as read. Never rewrite source text.
2. Store `normalized_body` only in memory, for matching (section 3.3).
3. Chunking: documents over 8,000 words are split at heading or section boundaries (lines matching `^(Section|SECTION|§|\d+[\.:]|[A-Z][A-Z ]{6,}$)`) into chunks of ≤ 8,000 words with a 300-word overlap. Record `chunk_start` offsets. Expect D067, D049, D073 and possibly D043 to chunk.
4. Link-only docs become sources with `has_text=false`. No extraction runs on them.

Tests: header stripping; the sha256 check; chunk boundaries never split mid-word; offsets map back to the original body.

### 3.3 A1 Extractor (`extract.py`, `prompts.py`) and A2 Verifier (`verify.py`)

**A1 system prompt** (byte-stable, cached), key points:
- "You extract housing rules from ONE legal source document for a renter-facing tool. Output only what this document states."
- List the six categories with one-line definitions from the brief's category table ("What to capture" column). Do not name any specific law.
- "`jurisdiction` must be one of: {doc manifest jurisdictions}. State-level rules use the state code. City rules use 'City, ST'."
- "Copy `quoted_span`, `effective_date_span`, `key_value_span` and `coverage_span` VERBATIM from the document, character for character. Never paraphrase inside a quote. If no sentence supports a field, set the field to null."
- "Bills, proposals and ballot questions: `enacted=false`. Mark `failed=true` only if the document states it failed, was vetoed or was struck."
- "Coverage: fill `min_units`, `built_before`, `cutoff_basis` and the exemptions only when the text states them. Put conditions that depend on owner identity, occupancy, subsidies or filings in `requires_facts_not_in_data` or `exemption.depends_on`."
- "If the document discusses a category but states there is no such rule at this level (for example a state bar on local rent control), extract that as a rule in its own category only if it is a legal requirement. Otherwise list the category in `categories_mentioned_without_rule`."
- "Secondary pages (law-firm, news): extract only rules they describe as enacted law, with the official citation if stated."

User message: `<document doc_id=... url=... retrieved=... source_type=...>` + body + `</document>`, placed after the instructions.

**A2 verification algorithm**, for each quote field present:
1. `norm(s)`: NFKC; curly quotes to straight; en and em dashes to `-`; `§` kept; collapse all whitespace to single spaces; strip. Build the normalized body with an index map back to raw offsets.
2. If there is an exact match of `norm(quote)` in the normalized body: pass, and store the raw `start` and `end` offsets. Set `quoted_span` to the RAW source substring, not the model's text.
3. Otherwise, a case-insensitive match also passes the same way.
4. Otherwise, find the top 3 candidate windows with `rapidfuzz.fuzz.partial_ratio_alignment`. If the best score is ≥ 92, snap: replace the quote with the raw source window and log `verify_snap`.
5. Otherwise, make one **repair call**: give the model the 3 candidate windows (raw text) and ask it to return the exact sentence that supports the field, or null. Re-run steps 2-4 once.
6. Otherwise: if the field is `quoted_span`, drop the candidate and log `verify_drop` with the reason. If it is an optional span, set the field and its derived value to null. For example, an unverifiable `effective_date_span` sets `effective_date=null` and lowers confidence by 0.2.
7. Reject a `quoted_span` shorter than 20 characters, as the schema requires.

Confidence: start from the model's value. Cap at 0.6 if `secondary_source`. Lower by 0.1 per snap.

Tests: unit-test `norm()` and the offset map with tricky inputs (non-breaking spaces, curly quotes, `§`, line-wrapped sentences). Then test pass, case pass, snap, repair (with mocked LLM), drop, and optional-span nulling. Integration: run on 3 real docs (D024, D052, D066) and assert that 100% of surviving quotes are verbatim substrings of the raw body at their offsets.

### 3.4 A3 Consolidator (`consolidate.py`)

For each jurisdiction (13), call the LLM with all verified candidates for that jurisdiction and its parent state's candidates (as read-only context). The output (Pydantic) is:
- `merge_groups: list[list[candidate_idx]]`: duplicates of the same legal rule. Keep the member with the most authoritative source (official > code publisher > secondary), then the longest verified quote. Union the coverage fields only where they agree; where they disagree, raise a conflict.
- `links: list[{from_idx, to_idx, kind: supersedes|yields_to|may_conflict_with, reason, span}]`. Example: a local rent ordinance and the state rent cap that exempts units under local rent control. Each link's `span` must be verified by A2 in either rule's source. If it can't be verified, keep the link and set `conflict_flag=true`, with a note saying the link is model-inferred.
- `no_rule_findings: list[{category, finding, citation, quoted_span|null}]` for categories with no rule in this jurisdiction. Quotes are verified through A2. With no quote, set `evidence: none`. These are never exported as rules.

Rules: A3 may not change citations, dates, numbers or quotes. It only groups and links. Enforce this in code by rebuilding final records from the original verified candidates and their indices.

Cross-jurisdiction pass (code, not LLM): for every state rule with `preempts_or_preempted_by` text or a `may_conflict_with` link to a city rule, set `conflict_flag` on both. This handles the NJ FAIR Act vs the Jersey City and Hoboken bans.

### 3.5 A4 Auditor (`auditor.py`)

For each final rule, run a fresh call with no shared context. The input is the rule JSON and ±1,500 characters of raw source around `quote_offsets`. Ask: "Does the passage support each of: requirement, key_value, effective_date, coverage thresholds/cutoffs, status (enacted, pending, failed)? Answer per field: supported, contradicted or not_stated, with a verbatim quote."
- `contradicted`: set `conflict_flag=true`, append the auditor's reason to `conflict_note`, lower confidence by 0.3, and log it. Do not auto-edit the field.
- `not_stated` on `effective_date`: keep it only if `effective_date_span` was verified. Otherwise set it to null.
- Budget: one call per rule (about 60-80 calls). Skip with `--no-audit` when short on time.

### 3.6 B1 Facts normalizer (`facts.py`)

- Parse `year_built` and `units` as int, or None. Treat `0` and empty as missing.
- `units_range` from `use_code`/`use_description`. This is a data-dictionary mapping, not law. Put it in `navigator/use_codes.py` with a source comment for each entry, and only include entries the description text itself states. Examples: LA `0500 "Five or more apartments"` → (5, None); Cambridge `"4-8-UNIT-APT"` → (4, 8); NJ class `4C` (apartment) → (5, None) per the NJ MOD-IV class definitions. Unmapped codes give None.
- `missing` lists every fact that is None. `owner_type`, `certificate_of_occupancy` and `owner_occupied` are always missing.

Tests: every distinct `use_code` in the CSV is either mapped or explicitly listed as unmapped.

### 3.7 B2 Resolver (`geo.py`)

1. **Batch geocode** (one call, about 500 rows): `POST https://geocoding.geo.census.gov/geocoder/geographies/addressbatch` with form fields `benchmark=Public_AR_Current`, `vintage=Current_Current`, and a CSV file `id,street,city,state,zip`. Cache the raw response. Parse the match flag, matched address, coordinates, and state and county FIPS.
2. **Place lookup** for each matched point: `GET https://geocoding.geo.census.gov/geocoder/geographies/coordinates?x=LON&y=LAT&benchmark=Public_AR_Current&vintage=Current_Current&layers=Incorporated Places&format=json`. Cache each response. Read `geographies["Incorporated Places"][0]["NAME"]` (for example "San Francisco city", "Boston city", "Hoboken city"). Verify the actual response shape on the first call and adapt the parser.
3. **No match**: try `/geocoder/geographies/onelineaddress` with the full address string, then (stretch) OpenStreetMap Nominatim at 1 request per second, cached. As a last resort, use `postal_fallback`: map postal city to legal city with a small neighborhood table (Boston neighborhoods → Boston; San Ysidro → San Diego) at `confidence=0.5`, with a note.
4. **House-number check**: if the matched address's house number doesn't match the input's (allowing ranges like `1031-1035`), downgrade to `oneline` or a fallback and log it.
5. Map the Census place name to a KB jurisdiction through `kb/jurisdictions.json`. A place outside the 10 cities gives `city=None`, so only state rules apply, and the note says so.
6. Cache to `cache/geo/` keyed by sha256 of the request. Output `data/resolved_addresses.json`.

Tests: the parser handles a recorded fixture response; the neighborhood fallback; the house-number range check; `NAVIGATOR_OFFLINE` raises on a cache miss. Integration: all 500 resolve, and the self-check reports the count where postal city ≠ legal city.

### 3.8 B3 Evaluator (`evaluate.py`): the core logic

For each address, take candidate rules where `jurisdiction ∈ {stack.state, stack.city}`. For each rule, at date `as_of`:

**Step 1, time.**
- `failed`: omit.
- `enacted == False`: result `pending`. Stop.
- `effective_date` is None: in force.
- Partial dates (`YYYY` or `YYYY-MM`): the window is [first day, last day]. If `as_of` is before the window, `not_yet_effective`. If after, in force. If inside, `unknown` ("effective date known only to the month").
- `effective_date > as_of`: `not_yet_effective`. Coverage still runs, so we only report it for addresses it would cover. If coverage is false, omit.
- `sunset_date < as_of`: omit.

**Step 2, coverage** (three-valued: T, F, U; combine with AND).
- `min_units`/`max_units` against `units`. If units is None, use `units_range`. If that decides it, the result is T or F (mark derived). Otherwise U (missing `units`).
- `built_before`/`built_after` against `year_built`:
  - With `cutoff_basis == certificate_of_occupancy` (or unknown) and a year equal to the cutoff year: U, missing `certificate_of_occupancy`.
  - Year < cutoff year: T for `built_before`.
  - Year > cutoff year: F.
  - year_built None: U.
- `requires_facts_not_in_data` non-empty: U, naming those facts.
- **Exemptions.** An exemption is ruled out (F) if any of its stated bounds are contradicted by known facts (for example `exemption.max_units=2` and units ≥ 3). It is T if all its conditions are known and met. Otherwise U. Any T exemption makes coverage F. Any U exemption that isn't ruled out makes coverage U.
- Final: coverage F → omit the rule. Coverage U → result `unknown`, with an explanation listing the missing facts. Coverage T → continue.

**Step 3, precedence** (within the same category).
- If rule R is covered and in force, and another rule L applying to this address (result applies or unknown) has `L supersedes R` or `R yields_to L`:
  - L is `applies`: R is `superseded`.
  - L is `unknown`: R is `unknown` ("superseded if <L title> covers this building").
- A state-level rule that bars local rules of a category (for example a state bar on local rent control) is reported as a rule. Local rules of that category must not exist in a MA city. Assert this in the self-check, not in the evaluator.

**Step 4, conflicts.** `conflict_flag = rule.conflict_flag or (any may_conflict_with partner is also present for this address)`.

**Step 5, explanation.** Use deterministic templates only. Examples: `"Applies: {title} covers buildings with 5+ units; this building has 20 units ({source})."` and `"Unknown: coverage depends on certificate of occupancy date; year built 1979 equals the cutoff year."` Include `as_of`.

Performance target: all 500 addresses for one date in under 2 seconds.

Unit tests (`tests/unit/test_evaluate.py`): table-driven with synthetic rules (not real law), covering:
- each time branch, including partial dates;
- unit thresholds with missing units and with a range;
- a cutoff equal to the year built giving unknown;
- an exemption ruled out by units;
- an exemption giving unknown;
- precedence where the local rule applies (state superseded) and where it is unknown (state unknown);
- the conflict flag;
- pending, failed and sunset;
- that a rule whose coverage is unknown is never omitted.

### 3.9 C1 Change tracker (`changes.py`) and ingest-new

- Load `dev/change_tests.json`. Map each test `rule_ids` entry to our ids via `kb/test_rule_map.json`. If a mapping is missing, emit an empty affected set plus `notes: "rule not found in corpus"`. Never fabricate.
- `as_of` tests (T1, T3): evaluate all 500 at `as_of_before` and `as_of_after`. Affected = addresses whose result for the mapped rule changes from `not_yet_effective` to `applies` (or `unknown`). Conflict ids = addresses where that rule has `conflict_flag` at `as_of_after`.
- `boundary` (T2): affected = addresses where each rule is applies or unknown. Notes record the per-city counts and assert none are in Newark.
- `pending` (T4): affected = addresses where the rule's result is `pending` (what it would affect if enacted).
- `negative` (T5): affected = addresses that report any `rent_increase_limits` rule from the mapped id. The expected set is empty. Also assert that no MA address has any rent-cap rule with `applies`.
- Output for every test: `affected_address_ids`, `conflict_flag_address_ids`, `notes`, and `per_address` (before and after result, kept in our internal file and stripped if the scorer rejects extra keys).
- **`ingest-new`** (T6, hour 16): copy the text into `supplementary/new/` with a generated header, then add a manifest row with a new doc_id. Run A1 and A2 on that doc, then A3 for its jurisdiction (with the existing rules as context), then A4. Write a new KB version and re-evaluate. Append test `T6` (or the provided id) with an affected set where the result changes between the version before and after, at today and at the new rule's effective date. Target: under 2 minutes end to end. Rehearse it with a synthetic ordinance in `tests/fixtures/fake_ordinance.txt` (clearly fictional, jurisdiction "Cambridge, MA").

### 3.10 Export (`export.py`)

- `rules.json`: `{"rules": [...]}`, each validated with `jsonschema` against `rule_record.schema.json`. Failing records are dropped and logged; the build must report 0 failures. Add `"_disclaimer": "Not legal advice"` at top level only if the scorer tolerates extra keys. Otherwise put it in the README.
- `lookups.json`: `{"as_of": "2026-10-01", "lookups": {...}}` with all 500 address ids present, even if a list is empty.
- `changes.json`: keys `T1`–`T5` (and `T6`).
- Write files deterministically: sorted keys, sorted address ids, `indent=2`, UTF-8.

### 3.11 Web UI (milestone M7, after the scored outputs are done)

FastAPI serving a static page with these routes:
- `GET /api/lookup/{address_id}?as_of=` returns the stack, facts and results, with rule citation, quote, URL and retrieval date.
- `GET /api/rules`
- `GET /api/changes`
- `POST /api/lookup-facts`: the user supplies year_built, units or owner type and the evaluator re-runs. This is the "confirm facts" flow.

Every response carries the header `X-Not-Legal-Advice: true`, and the page shows the banner and the as-of date. Results are shown as word chips (Applies, Unknown, ...), never color alone. Spanish summaries are a stretch: one batch translation call per rule at build time, cached, while quotes and citations stay in English.

---

## 4. Testing strategy

### 4.1 Unit tests (fast, no network)
`tests/unit/`: corpus, verify, facts, geo parser, evaluate, changes, export. Mock the LLM by monkeypatching `llm.call()` to return fixture Pydantic objects. Target: under 10 seconds total.

### 4.2 Integration tests (cache-backed, `NAVIGATOR_OFFLINE=1` in CI)
- `test_extract_real_docs.py`: on D024 (CA Civ 1947.12), D052 (MA c.186 §15B) and D069 (NJ FAIR Act), assert at least one rule per expected category, and that every quote verifies at its offsets.
- `test_end_to_end.py`: runs `run-all` from cache and asserts the brief's expected behaviors:
  - **T1**: every CA address has the CA algorithmic rule `not_yet_effective` at 2025-12-31 and `applies` at 2026-01-02.
  - **T2**: the Hoboken ban applies only to Hoboken addresses and the Jersey City ban only to Jersey City addresses, with 0 in Newark. If either is missing from the corpus, the test is marked xfail with a reason. Do not fabricate the rule.
  - **T3**: the NJ FAIR Act is `not_yet_effective` at 2026-10-01 and `applies` at 2027-07-02 for NJ addresses, and the Jersey City and Hoboken addresses carry `conflict_flag`.
  - **T4**: the MA bills are `pending` for all 110 MA addresses and never `applies`.
  - **T5**: no MA address has any `rent_increase_limits` result of `applies` from a ballot measure. The T5 affected set is empty.
  - **Brief example** (an SF address with about 20 units built 1962, or the closest sample): the SF rent ordinance applies, the CA state cap is `superseded`, and there are just-cause, deposit, screening-fee and algorithmic results.
  - **Postal ≠ legal**: Boston neighborhood rows resolve to "Boston, MA".
  - **Determinism**: two consecutive offline runs produce identical output hashes.

The legal expectations in these tests come from the brief and the README. They live only in tests, never in pipeline code.

### 4.3 Self-check report (`selfcheck`, our stand-in for score.py)
`output/selfcheck.txt` must report:
1. Schema validity: N of N rules valid.
2. Quote verification: % of `applies` answers whose rule quote is found verbatim in a corpus text file (target 100% for corpus-sourced rules), and the count from secondary or supplementary sources.
3. Coverage matrix: jurisdiction × category, each cell holding a rule id, a no-rule finding, or a gap.
4. Result distribution per city: applies, unknown, superseded, not_yet_effective, pending. Flag any city with more than 60% unknown for review.
5. Missing-fact counts driving unknowns.
6. T1-T5 pass/fail with counts.
7. Geocoding: method counts, postal ≠ legal count, low-confidence list.
8. The four known open questions from the README §9, each shown with what the KB holds (for example both of Berkeley's effective dates, with `conflict_flag`).
9. Audit counts: extract calls, cache hits, snaps, repairs, drops, auditor contradictions.

### 4.4 Quality gates (CI, `make check`)
`ruff check`, `ruff format --check`, `pytest -q` (unit and offline integration), `navigator export` (schema 0 failures), `navigator selfcheck` (T1-T5 pass, quote verification 100% for corpus sources).

---

## 5. Milestones (build in order, each with a definition of done)

| # | Milestone | Done when |
|---|---|---|
| M0 | Scaffold: uv project, layout, config, Makefile, `llm.py` cache + audit, symlink | `make check` passes on empty tests; a cached dummy LLM call round-trips; an offline cache miss raises |
| M1 | A0 ingest + A1 extract + A2 verify on 3 docs | Unit tests for verify pass; 3-doc integration passes; audit log shows the decisions |
| M2 | Extract the full corpus (54 docs, chunked) | All docs processed; drop rate reported; cost and calls logged; `cache/llm` committed |
| M3 | A3 consolidate + A4 audit + KB v001 + `rules.json` export | Schema 0 failures; coverage matrix printed; `test_rule_map.json` reviewed |
| M4 | B1 facts + B2 geocode | 500 addresses resolved and cached; geo tests pass |
| M5 | B3 evaluator + `lookups.json` | Evaluator unit tests pass; the brief example test passes; all 500 addresses present |
| M6 | C1 changes T1-T5 + `ingest-new` rehearsal with the fake ordinance | T1-T5 integration tests pass (or xfail with a documented reason); the fake T6 runs in under 2 minutes |
| M7 | Web UI + README + selfcheck polish | UI shows lookup, changes and sources; "Not legal advice" everywhere |
| M8 | Hour 16: run `ingest-new` on the real T6 file | `changes.json` has T6; video-ready output |

Priority if time runs short: M0-M5 (Modules A and B, the minimum entry), then M6, then M7.

---

## 6. Known risks and required handling

| Id | Risk | Handling |
|---|---|---|
| R1 | Key texts are link-only: NJ Anti-Eviction Act and deposit statutes (Justia), Hoboken and Newark ordinances (ecode360), the LA RSO code (amlegal), the Jersey City algorithmic ban (news only), and the MA ballot story (news). | First, extract from official pages that restate them (D036 Jersey City landlord-tenant page, D067 NJ DCA guide, D041 LA RSO overview, D040 LA JCO, D048 MA c.40P). Optional M2b: fetch link-only pages once, only where the site's terms permit, into `supplementary/text/` with header and retrieval date. Mark `secondary_source=true` with confidence ≤ 0.6, and report them separately in the self-check, since scoring checks quotes against the corpus. Never fetch ecode360 or amlegal in bulk. |
| R2 | Mailing city ≠ legal city | B2 resolver plus neighborhood fallback; reported in the self-check |
| R3 | Missing year built or units | Three-valued evaluator; derived unit ranges from use codes; `unknown` lists the missing facts |
| R4 | Certificate-of-occupancy cutoffs (SF 1979-06-13, LA 1978-10-01) | `cutoff_basis` from extraction; a year equal to the cutoff gives `unknown` |
| R5 | Two published effective dates (Berkeley ch. 13.63, the LA RSO formula) | Keep both candidates. A3 merges them with `conflict_flag` and a note; the evaluator uses the verified official-source date and the explanation mentions the other |
| R6 | Owner-type exemptions (CA small-landlord deposit rule) | `exemption.depends_on=["owner_type"]` plus unit bounds, so they are ruled out when units are known to be above the bound, and `unknown` otherwise |
| R7 | LLM drift between runs | Prompt version in the cache key; outputs are produced only from the cache in CI |
| R8 | Answer-key rule ids for tests | `test_rule_map.json`, generated and then reviewed by hand; a missing mapping gives an empty set and a note, never an invented rule |
| R9 | Cost and time | About 54-70 extraction calls, 13 consolidation calls and about 70 audit calls on Opus 5.5 at high effort. Log `usage` per call and print the totals in the self-check. Use `--no-audit` to skip A4 if needed. |

---

## 7. Deliverables checklist

- `output/rules.json`, `output/lookups.json` (500 addresses, as_of 2026-10-01), `output/changes.json` (T1-T5, plus T6 after hour 16)
- `output/selfcheck.txt`, `kb/` (committed), `cache/` (committed, for offline replay)
- `README.md`: how to run (`make setup`, `make run-all`, `make offline`, `make serve`), architecture summary, limitations, "Not legal advice"
- Demo: live `ingest-new` rerun, `lookup` for a Boston neighborhood address and an SF address, and the self-check on screen
