"""Command line: uv run python -m navigator <command>. Not legal advice."""

from __future__ import annotations

import json
from datetime import date

import typer

from navigator import DISCLAIMER, config

app = typer.Typer(add_completion=False, help=f"Rental Housing Law Navigator. {DISCLAIMER}")


@app.command()
def ingest():
    """A0: load the corpus into the source library."""
    from navigator import corpus

    typer.echo(corpus.ingest())


@app.command()
def extract(doc: list[str] = typer.Option(None, help="doc ids, default all with text")):
    """A1+A2: extract and verify rules."""
    from navigator import extract as ex

    res = ex.extract_all(doc or None, progress=lambda r: typer.echo(json.dumps(r)))
    errs = [r for r in res if "error" in r]
    typer.echo(f"done: {len(res)} docs, {sum(r.get('verified', 0) for r in res)} verified, {len(errs)} errors")


@app.command("fetch-supplementary")
def fetch_supplementary(doc: list[str] = typer.Option(None)):
    """Optional: fetch link-only sources once (robots.txt respected) as secondary text, then extract them."""
    from navigator import extract as ex
    from navigator import supplementary

    rep = supplementary.fetch_link_only(doc or None)
    for r in rep:
        typer.echo(json.dumps(r))
    fetched = [r["doc_id"] for r in rep if r["result"].startswith("fetched")]
    if fetched:
        res = ex.extract_all(fetched, progress=lambda r: typer.echo(json.dumps(r)))
        typer.echo(f"extracted {len(res)} supplementary docs")


@app.command()
def consolidate(no_audit: bool = typer.Option(False, help="skip the A4 auditor")):
    """A3+A4: merge, link, audit; writes a new knowledge-base version."""
    from navigator import consolidate as co

    typer.echo(co.build_kb(audit=not no_audit, note="full build" if not no_audit else "full build, auditor skipped"))


@app.command()
def geocode():
    """B1+B2: building facts and jurisdiction stacks for all sample addresses."""
    from navigator import geo

    typer.echo(geo.resolve_all())


@app.command()
def lookup(address_id: str, as_of: str = typer.Option(str(config.AS_OF_DEFAULT))):
    """Print one address's answer with citations."""
    from navigator import evaluate

    typer.echo(json.dumps(evaluate.lookup_address(address_id, date.fromisoformat(as_of)), indent=2))


@app.command()
def changes():
    """C1: run change tests T1-T5 (+ any ingested new law)."""
    from navigator import changes as ch

    typer.echo(json.dumps(ch.run_all(), indent=2)[:4000])


@app.command("ingest-new")
def ingest_new(path: str, jurisdiction: str, url: str, retrieved: str = typer.Option(None), test_id: str = "T6"):
    """Hour-16 flow: extract a new law, add it to a new KB version, report affected addresses."""
    from navigator import changes as ch

    typer.echo(json.dumps(ch.ingest_new(path, jurisdiction, url, retrieved, test_id), indent=2)[:4000])


@app.command()
def export():
    """Write output/rules.json, lookups.json, changes.json (schema-validated)."""
    from navigator import export as ex

    typer.echo(ex.export_all())


@app.command()
def selfcheck():
    """Write output/selfcheck.txt."""
    from navigator import selfcheck as sc

    typer.echo(sc.run())


@app.command("run-all")
def run_all(no_audit: bool = False):
    ingest()
    extract(None)
    consolidate(no_audit)
    geocode()
    export()
    selfcheck()


@app.command()
def serve(port: int = 8765):
    import uvicorn

    uvicorn.run("web.app:app", host="127.0.0.1", port=port)


def main():
    app()
