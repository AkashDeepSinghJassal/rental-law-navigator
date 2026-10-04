# Audio scripts (about 1 minute each, ~150 spoken words)

## 1. Design and features

> If you rent an apartment, which laws protect you, and which are about to change? Today, answering that means
> reading city codes and state statutes by hand. Rental Law Navigator answers it for one exact address.
>
> Start by choosing renter or housing provider, then type an address. You get a report: the state, county and
> legal city, then six topics: rent increases, eviction protections, deposits, fees, screening, and algorithmic
> rent-setting. Each rule shows a plain-language status (applies, unknown, superseded, not yet in force, or
> proposed) and quotes the law it comes from. One click opens the source with that sentence highlighted.
>
> The side panel shows what's changing at this address, with a jump to future dates. If an answer is unknown, add
> what you know, like the year built, and it re-checks. There are quick calculators, a map, official city links,
> and you can save, share, print, or compare up to three addresses. It works in English or Spanish, on mobile,
> in light or dark mode.
>
> It's not legal advice. It shows you the law, with proof.

## 2. Technical overview, architecture and flow

> Under the hood, language models only read the law. Plain code makes every decision.
>
> First, an extractor agent reads each of the corpus documents and writes structured rules, each with
> word-for-word quotes. A verifier, written in code, checks every quote against the source text. If a quote isn't
> found, the model gets one repair attempt, choosing only among real passages; otherwise the rule is dropped.
> A consolidator agent merges duplicates into one rule per law and links which rule overrides which. A coverage
> check and an independent auditor then re-read the sources and flag disagreements for human review.
>
> Everything lands in a versioned knowledge base in SQL, with every model call cached and logged, so any run can
> be replayed offline.
>
> At query time there's no model at all. The Census Geocoder finds the legal city, and a deterministic evaluator
> applies dates, building facts and precedence. Missing facts return unknown, never a guess. The model layer is
> provider-neutral: Claude, OpenAI, Gemini, Groq or a local Llama, switched in one setting. FastAPI serves a
> React front end.
