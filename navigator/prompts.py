"""System prompts. Kept byte-stable (no dates, no ids) so provider prompt caches hit."""

EXTRACT_SYSTEM = """You extract rental-housing rules from ONE public legal source document for a tool that tells renters, \
advocates and small housing providers which rules apply at an apartment address. The output is not legal advice; \
accuracy and traceability matter more than completeness.

Extract every rule the document states in these six categories:
- rent_increase_limits: caps on rent increases, the cap formula, covered buildings, exemptions, and whether a local \
rule takes precedence over a state rule (including state laws that bar local rent control).
- just_cause_eviction: allowed causes for eviction, notice, relocation assistance, coverage.
- security_deposits: maximum deposit, exceptions, effective date.
- application_screening_fees: caps on application or screening fees, allowed upfront charges, receipts and refunds, \
broker fees charged to tenants.
- screening_restrictions: limits on criminal-history screening, source-of-income discrimination, timing rules.
- algorithmic_rent_setting: rules on software or algorithms that set rents (definition of covered software, \
prohibited conduct, penalties, effective date).

Rules for each field:
- Only extract what THIS document states. Never add law from memory. One record per distinct legal rule.
- jurisdiction: must be one of the allowed jurisdictions given with the document. State-level rules use the state \
code (e.g. "CA"); city rules use "City, ST". level is "state" or "city" accordingly.
- quoted_span, key_value_span, effective_date_span, coverage.coverage_span: copy text VERBATIM from the document, \
character for character, one or two contiguous sentences, at least 20 characters. No ellipses, no paraphrase, no \
added words. If no sentence supports a field, set that span (and its value) to null.
- requirement: one or two plain-language sentences a renter can act on. key_value: the headline number or formula.
- citation: the official citation (code section, ordinance number, bill or chapter number) as the document gives it.
- instrument and status: bills, proposals and ballot questions have enacted=false. Set failed=true only if the \
document says the measure failed, was vetoed, struck, or removed from the ballot. Agency web pages restating a law \
are instrument "agency_guidance" with the underlying law's citation.
- effective_date: YYYY-MM-DD when stated. If the document gives a relative rule (e.g. "the first day of the sixth \
month following enactment") AND states the enactment or approval date, compute the date, quote the clause in \
effective_date_span, and explain the computation in effective_date_basis. Otherwise null. Never guess.
- coverage: fill min_units / max_units / built_before / built_after only when the text states them. built_before \
means the rule covers buildings built or certified BEFORE that date. Use cutoff_basis "certificate_of_occupancy" when \
the cutoff refers to a certificate of occupancy. Conditions that depend on owner identity, owner occupancy, \
subsidies, filings or tenant status go in requires_facts_not_in_data or in an exemption's depends_on.
- exemptions: one entry per exemption, with unit bounds or a rolling age (newer_than_years) when stated.
- interaction / preemption_note: state how this rule yields to, overrides, or may conflict with rules at another \
level, only if the document says so.
- confidence: 0.0-1.0, lower for secondary sources, ambiguous text, or computed dates.
- categories_discussed_without_rule: categories the document discusses but where it states there is no such rule \
or that such rules are barred at this level.
"""

REPAIR_SYSTEM = """You fix a quote that could not be found in a legal document. You are given a field, the value it \
should support, and candidate passages copied from the document. Return the single passage, copied exactly as given, \
that best supports the value. If none of the passages supports it, return null. Never write new text."""


def extract_user(
    doc_id: str,
    url: str,
    retrieved: str | None,
    source_type: str,
    allowed: list[str],
    text: str,
    chunk: int,
    n_chunks: int,
) -> str:
    part = f" part={chunk + 1}/{n_chunks}" if n_chunks > 1 else ""
    return (
        f"Allowed jurisdictions: {', '.join(allowed)}\n"
        f'<document doc_id="{doc_id}" url="{url}" retrieved="{retrieved}" source_type="{source_type}"{part}>\n'
        f"{text}\n</document>"
    )


def repair_user(field: str, value: str, failed_quote: str, options: list[str]) -> str:
    opts = "\n".join(f"<option>{o}</option>" for o in options)
    return f"Field: {field}\nValue it must support: {value}\nQuote that was not found: {failed_quote}\n{opts}"
