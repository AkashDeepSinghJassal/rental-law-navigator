"""Optional: fetch link-only manifest sources ONCE, politely (robots.txt, 2 s delay, cached), as secondary text.

These texts are NOT in the starter corpus: rules from them are marked secondary, capped at 0.6 confidence and
reported separately. Pages that refuse or need JavaScript are skipped and logged, never worked around.
"""

from __future__ import annotations

import time
from urllib import robotparser
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select

from navigator import config, db

UA = "RentalLawNavigator/0.1 (Hack-Nation hackathon research; one request per page, cached)"


def _allowed(url: str) -> bool:
    p = urlparse(url)
    rp = robotparser.RobotFileParser()
    try:
        r = httpx.get(
            f"{p.scheme}://{p.netloc}/robots.txt", headers={"User-Agent": UA}, timeout=20, follow_redirects=True
        )
        if r.status_code >= 400:
            return True  # no robots.txt
        rp.parse(r.text.splitlines())
        return rp.can_fetch(UA, url)
    except httpx.HTTPError:
        return False


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "nav", "header", "footer", "noscript", "form"]):
        t.decompose()
    main = soup.find("main") or soup.find("article") or soup.body or soup
    lines = [ln.strip() for ln in main.get_text("\n").splitlines()]
    return "\n".join(ln for ln in lines if ln)


def fetch_link_only(doc_ids: list[str] | None = None, delay: float = 2.0) -> list[dict]:
    with db.session() as s:
        q = select(db.Source).where(db.Source.has_text.is_(False))
        srcs = [x for x in s.scalars(q) if doc_ids is None or x.doc_id in doc_ids]
    out_dir = config.SUPPLEMENTARY_DIR / "text"
    out_dir.mkdir(parents=True, exist_ok=True)
    report = []
    for src in srcs:
        rec = {"doc_id": src.doc_id, "url": src.url}
        if not _allowed(src.url):
            rec["result"] = "skipped: robots.txt disallows"
        else:
            try:
                r = httpx.get(src.url, headers={"User-Agent": UA}, timeout=30, follow_redirects=True)
                text = html_to_text(r.text) if "html" in r.headers.get("content-type", "") else ""
                if r.status_code >= 400:
                    rec["result"] = f"skipped: HTTP {r.status_code}"
                elif len(text.split()) < 150:
                    rec["result"] = f"skipped: too little text ({len(text.split())} words; likely needs JavaScript)"
                else:
                    retrieved = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
                    (out_dir / f"{src.doc_id}.txt").write_text(f"SOURCE: {src.url}\nRETRIEVED: {retrieved}\n\n{text}")
                    with db.session() as s:
                        row = s.get(db.Source, src.doc_id)
                        row.body, row.has_text, row.in_corpus = text, True, False
                        row.retrieved_at, row.word_count = retrieved, len(text.split())
                    rec["result"] = f"fetched {len(text.split())} words"
            except httpx.HTTPError as e:
                rec["result"] = f"skipped: {type(e).__name__}"
        db.audit("supplementary", rec["result"].split(":")[0], src.doc_id, **rec)
        report.append(rec)
        time.sleep(delay)
    return report
