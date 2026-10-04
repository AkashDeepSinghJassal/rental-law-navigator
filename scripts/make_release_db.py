"""Build data/release.db: the knowledge base the deployed app serves.

Copies the working database and removes the full text of sources that are not in the official starter corpus
(law-firm and news pages fetched once during development), since we should not redistribute those pages.
Rules keep their short verified quotes and a link to the original page.
"""

import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "navigator.db"
DST = ROOT / "data" / "release.db"


def main() -> None:
    con = sqlite3.connect(SRC)
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    con.close()
    shutil.copyfile(SRC, DST)
    con = sqlite3.connect(DST)
    n = con.execute("UPDATE sources SET body = NULL WHERE in_corpus = 0 AND body IS NOT NULL").rowcount
    con.execute("DELETE FROM http_cache WHERE url LIKE '%addressbatch%'")  # large batch file, not needed at runtime
    con.commit()
    con.execute("VACUUM")
    con.execute("PRAGMA journal_mode=DELETE")
    con.close()
    print(f"{DST.relative_to(ROOT)}: {DST.stat().st_size / 1e6:.1f} MB; removed text of {n} non-corpus sources")


if __name__ == "__main__":
    sys.exit(main())
