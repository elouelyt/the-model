"""Permanent per-batch archive of the RAW data the production batches overwrite every time.

Each production batch rewrites data/nba_stake_cache.json (every Stake prop line + odds) and the reference-book caches
(FanDuel / Pinnacle / BettingPros). Production only keeps the picks it recommended, so anything not recommended is lost.
This copies the raw files (gzipped) into nuevas_ideas/archive/batches/<stake-timestamp>/ so any future rule can be
back-tested offline on the full set of lines. Local only (.gitignore). Idempotent: one folder per Stake timestamp.
"""

import gzip
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import BASE, ROOT  # noqa: E402

FILES = ["nba_stake_cache.json", "nba_fanduel_cache.json", "nba_pinnacle_cache.json", "nba_bettingpros_cache.json", "nba_picks.json"]
ARCHIVE = BASE / "archive" / "batches"


def archive_batch() -> str:
    stake = ROOT / "data" / "nba_stake_cache.json"
    if not stake.exists():
        return "no stake cache"
    stamp = json.loads(stake.read_text(encoding="utf-8"))["timestamp"][:19].replace(":", "").replace("-", "")
    dest = ARCHIVE / stamp
    if dest.exists():
        return f"batch {stamp} already archived"
    dest.mkdir(parents=True)
    saved = 0
    for name in FILES:
        src = ROOT / "data" / name
        if src.exists():
            with src.open("rb") as f_in, gzip.open(dest / (name + ".gz"), "wb", compresslevel=6) as f_out:
                shutil.copyfileobj(f_in, f_out)
            saved += 1
    size = sum(p.stat().st_size for p in dest.glob("*.gz")) // 1024
    return f"archived batch {stamp}: {saved} files, {size} KB"


if __name__ == "__main__":
    print(archive_batch())
