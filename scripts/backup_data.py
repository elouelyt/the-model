#!/usr/bin/env python3
"""Copy every local betting record (history, raw batches, paper-test histories) into a dated zip OUTSIDE the project folder.

    python scripts/backup_data.py      # -> ~/the-model-backups/the-model_YYYY-MM-DD_HHMM.zip, keeps the last 20
Raw data is never uploaded to GitHub, so this is the only copy besides the encrypted history files in the repo.
"""

import logging
import zipfile
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
DEST = Path.home() / "the-model-backups"
SOURCES = ["data", "nfl/data", "nuevas_ideas"]
KEEP = 20


def main() -> Path:
    DEST.mkdir(exist_ok=True)
    out = DEST / f"the-model_{datetime.now():%Y-%m-%d_%H%M}.zip"
    n = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for src in SOURCES:
            for f in (ROOT / src).rglob("*"):
                if f.is_file() and "__pycache__" not in f.parts:
                    z.write(f, f.relative_to(ROOT).as_posix())
                    n += 1
    for old in sorted(DEST.glob("the-model_*.zip"))[:-KEEP]:
        old.unlink()
    logger.info("Backup: %d files, %.1f MB -> %s", n, out.stat().st_size / 1e6, out)
    return out


if __name__ == "__main__":
    main()
