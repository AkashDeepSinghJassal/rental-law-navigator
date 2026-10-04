# Rental Housing Law Navigator: Design Plan

Hack-Nation x RealPage, Challenge 02. Not legal advice.

This plan adapts two public references. **Agentic architecture** comes from the published README of [isaaclins/rental-law-navigator](https://github.com/isaaclins/rental-law-navigator). **Product design** comes from [RentRights](https://github.com/writingdeveloper/rentrights). They are ideas only: we write our own code, and we check the event rules before reusing anything.

## 1. Goal

For any of the 500 sample addresses and any date, return every housing rule that applies, with a plain-language summary and a verified quote from the source law. Say `unknown` when a needed fact is missing.

## 2. Architecture: LLMs read, code decides

```
corpus (87 docs)
   |
   v
[1 Extract]  LLM, per document ------------------+
   |                                              | retry once
   v                                              |
[2 Verify]   code: quote must appear in source ---+
   |   fail twice -> snap to closest passage, else drop the record
   v
[3 Consolidate] LLM, per jurisdiction: merge duplicates, probe empty
   |            categories -> "no rule at this level" findings
   v
[4 Resolve + Apply] code: Census geocode -> state/county/city stack,
   |                evaluator: time, facts, precedence, conflicts
   v
[5 Track change] code: diff results across dates / rule sets;
                 new law = 2 LLM calls (extract + consolidate), re-run all
```

### Components

| Component | Type | Does | Guardrail |
|---|---|---|---|
| Extractor | LLM | One schema-valid rule record per rule found | JSON schema; prompt names no specific law |
| Verifier | Code | Quote must occur verbatim in the source file (whitespace and quote-style tolerant) | Retry once, then snap to closest passage or drop |
| Consolidator | LLM | Merge duplicate rules per jurisdiction; probe empty categories | Produces explicit "no rule" findings |
| Coverage auditor | LLM | Independent second read of cutoffs, thresholds and exemptions | Disagreements go to the conflict note |
| Resolver | Code | Address to state, county, legal city | Census Geocoder, cached; reject house-number mismatches |
| Evaluator | Code | Per address and rule: time, facts, precedence, conflicts | Missing fact returns `unknown` |
| Change tracker | Code | Before/after diff, affected addresses, conflict flags | `pending` and `failed` never apply |

Cross-cutting: cache every model and geocoder response by a SHA-256 of the inputs (reproducible offline reruns), and write an audit log with one line per model call or pipeline decision.

Reference scale (as reported in the isaaclins README for its own corpus, not ours): about 106 model calls for the full corpus, about 10 minutes at 3 parallel calls, 2 calls for one new ordinance, and 0 calls plus well under a second to evaluate 500 addresses.

## 3. Data model

**Rule record** (extends the provided `rule_record.schema.json`): jurisdiction, category, status (`applies`, `pending`, `not_yet_effective`, `failed`, `no_rule`), effective date, coverage object, citation, source URL, retrieval date, quoted span, confidence, conflict note, secondary-source flag, plain-language summary (English and Spanish).

**Coverage object** (what the evaluator tests):

```json
{
  "min_units": 5,
  "year_built_before": "1979-06-13",
  "exemptions": ["new_construction"],
  "facts_needed": ["year_built", "units"],
  "unknown_if_missing": ["year_built"]
}
```

**Result values:** `applies`, `unknown`, `superseded`, `not_yet_effective`, `pending`.

**Dataset gaps to handle as `unknown`:** no year built for San Diego or Berkeley, no units for Berkeley, Boston, Jersey City, Newark and most of Hoboken, no owner type anywhere. Year built is not the certificate-of-occupancy date, so a building in a cutoff year is `unknown`.

## 4. Product design (from RentRights)

Flow: **enter address**, see the **jurisdiction stack**, read **one answer per category**, **confirm missing facts**, re-run.

Borrowed from RentRights:
- A confidence level on every answer.
- Dated rules: when a figure has lapsed, say "pending, confirm" and never show a stale number.
- Ask a confirming question instead of guessing. The user can supply year built, units or owner type and re-run.
- English and Spanish, plain language, accessible contrast, "not legal advice" on every page.

Different from RentRights, on purpose:
- No hand-written rules. Everything comes from automated extraction.
- Missing facts give `unknown`, not a protective-direction default, because the scoring gives credit for `unknown` and penalizes confident wrong answers.
- No LLM at answer time. Answers are pre-extracted rule summaries, and there is no free-form chat that could suggest ways around a rule.

### Screens

1. **Address lookup:** address, as-of date, jurisdiction stack, one row per category with a status chip written in words (not color alone), and a "confirm facts" panel for unknowns.
2. **Rule detail (one tap):** citation, quoted span, source link, retrieval date, conflict note, confidence.
3. **What's changing:** timeline of laws taking effect, affected addresses and before/after per law.
4. **Sources and method:** audit log, geocoding confidence, link to every source document.

## 5. Build plan (24 hours)

| Hours | Track | Deliverable |
|---|---|---|
| 0-2 | Foundation | Repo, schema validation, model client with cache and audit log |
| 2-6 | Extract + verify | Corpus run, quote gate, retry loop, self-check of results |
| 6-11 | Resolve + apply | Geocode 500 addresses, jurisdiction stacks, evaluator with `unknown` |
| 11-16 | Product | Address view, as-of date, confirm facts, English/Spanish |
| 16-20 | Change tracking | T1-T5, ingest command ready for the hour-16 ordinance |
| 20-24 | Ship | Score run, three videos, README, live demo link |

If time runs short: Modules A and B first, then change tracking, then the plain-language view, then stretch goals.

## 6. Acceptance checks

- Every quoted span is found in its source file.
- T1-T5 pass, and T3 raises the conflict flag for Jersey City and Hoboken.
- Missing facts return `unknown` and name the missing fact.
- Pending, failed and not-yet-effective rules never show as `applies`.
- An offline rerun from the cache gives identical outputs.
- Every interface says "not legal advice" and shows an as-of date.

## 7. Risks

| Risk | Response |
|---|---|
| Hallucinated rules or citations | Verbatim quote gate; drop on second failure |
| Mailing city is not the legal city | Resolve through the Census Geocoder; verify house number |
| Pending vs enacted confusion (MA bills, struck ballot question) | Status field on every rule; T4 and T5 tests |
| Preemption (NJ FAIR Act over local bans) | Conflict flag for human review |
| Link-only sources with no text | Lower confidence; evaluate as `unknown` |
| Reusing a competitor's code | Ideas only; confirm event rules with the organizers |
