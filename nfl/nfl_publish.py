#!/usr/bin/env python3
"""Refresh NFL value bets and publish them (encrypted) for the private panel. Mirrors scripts/nba_publish.py.

Chain: settle -> Stake props (CDP, needs Chrome on stake.com) -> Pinnacle -> picks -> combos -> data/nfl_picks.enc
(AES with DASHBOARD_PASSWORD) -> git commit + push; the push triggers the 'Rebuild private panel' workflow (NFL tab).
Raw picks stay local (nfl/data); the repo only sees ciphertext.   python nfl/nfl_publish.py [--skip-fetch] [--no-push]   (--no-push: refresh, archive and encrypt locally, do not commit or push)
"""

import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from private_crypto import encrypt_file  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

NFL = ROOT / "nfl"
ENC = ROOT / "data" / "nfl_picks.enc"


def run(*cmd: str, check: bool = True) -> subprocess.CompletedProcess:
    logger.info("$ %s", " ".join(cmd))
    return subprocess.run(cmd, cwd=ROOT, check=check)


def main() -> None:
    load_dotenv(ROOT / ".env")
    if not os.environ.get("DASHBOARD_PASSWORD"):
        raise SystemExit("DASHBOARD_PASSWORD missing in .env")
    py = sys.executable
    run(py, "nfl/nfl_settle.py", check=False)
    if "--skip-fetch" not in sys.argv:
        run(py, "nfl/nfl_stake_scraper.py")
    run(py, "nfl/nfl_pinnacle.py")
    run(py, "nfl/nfl_ev.py")
    run(py, "nfl/nfl_combos.py")
    try:  # permanent raw archive for later back-testing (local only)
        sys.path.insert(0, str(ROOT / "nuevas_ideas"))
        import archive
        logger.info(archive.archive_nfl_batch())
    except Exception as exc:  # noqa: BLE001
        logger.warning("archive skipped: %s", exc)
    picks_path = NFL / "data" / "nfl_picks.json"
    doc = json.loads(picks_path.read_text(encoding="utf-8"))
    analysis = NFL / "data" / "nfl_analysis.json"
    if analysis.exists():
        doc["analysis"] = json.loads(analysis.read_text(encoding="utf-8"))
        picks_path.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    encrypt_file(picks_path, ENC)
    bundle = {p.name: json.loads(p.read_text(encoding="utf-8")) for p in sorted((NFL / "data" / "nfl_history").glob("*.json"))}
    (ROOT / "build").mkdir(exist_ok=True)
    (ROOT / "build" / "nfl_history_bundle.json").write_text(json.dumps(bundle, ensure_ascii=False), encoding="utf-8")
    encrypt_file(ROOT / "build" / "nfl_history_bundle.json", ROOT / "data" / "nfl_history.enc")  # encrypted backup

    if "--no-push" in sys.argv:
        logger.info("--no-push: data refreshed and archived locally, nothing committed")
        return
    mix_files: list[str] = []
    try:  # mixed NBA+NFL combos for the 'Combinadas' tab
        sys.path.insert(0, str(ROOT / "scripts"))
        import mix_publish
        mix_files = mix_publish.update()
    except Exception as exc:  # noqa: BLE001
        logger.warning("mix combos skipped: %s", exc)
    run("git", "add", "data/nfl_picks.enc", "data/nfl_history.enc", *mix_files)
    if run("git", "diff", "--cached", "--quiet", check=False).returncode == 0:
        logger.info("No changes to publish")
        return
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    run("git", "commit", "-m", f"chore: update NFL picks {stamp}")
    run("git", "pull", "--rebase", "--autostash", "origin", "main")
    run("git", "push", "origin", "main")
    logger.info("Published NFL picks; the panel rebuilds in GitHub Actions (~2 min)")


if __name__ == "__main__":
    main()
