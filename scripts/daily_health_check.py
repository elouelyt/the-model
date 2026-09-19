"""Daily health check — runs before generate_html.py in CI.

Checks:
1. rankings_cache.json exists and is fresh (< 3 days old)
2. At least 400 players ranked
3. Top 10 contains expected names (Sinner, Alcaraz, Djokovic...)
4. track_record.json is valid JSON
5. THE_ODDS_API_KEY is set

Prints a summary. Exits 0 (warning only) so the pipeline always continues,
but logs WARN for each issue so it's visible in Actions.
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
ISSUES: list[str] = []


def check(condition: bool, ok_msg: str, fail_msg: str) -> None:
    if condition:
        logger.info("  ✓ %s", ok_msg)
    else:
        logger.warning("  ✗ %s", fail_msg)
        ISSUES.append(fail_msg)


def check_rankings() -> None:
    path = ROOT / "data" / "rankings_cache.json"
    if not path.exists():
        ISSUES.append("rankings_cache.json missing")
        logger.warning("  ✗ rankings_cache.json missing")
        return

    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as e:
        ISSUES.append(f"rankings_cache.json invalid JSON: {e}")
        return

    ts = data.get("timestamp")
    if ts:
        age_days = (datetime.now(timezone.utc) - datetime.fromisoformat(ts)).days
        check(age_days < 3, f"rankings fresh ({age_days}d old)", f"rankings STALE — {age_days} days old")
    else:
        ISSUES.append("rankings_cache.json has no timestamp")

    rankings = data.get("rankings", {})
    check(len(rankings) >= 400, f"{len(rankings)} players in rankings", f"only {len(rankings)} players — scrape may have failed")

    top10 = sorted(rankings.items(), key=lambda x: x[1]["rank"])[:10]
    top10_names = [n for n, _ in top10]
    logger.info("  Top 5: %s", ", ".join(f"{r['rank']}. {n}" for n, r in top10[:5]))

    expected = ["Sinner", "Alcaraz", "Djokovic", "Zverev", "Fritz"]
    found = sum(1 for exp in expected if any(exp.lower() in n.lower() for n in top10_names))
    check(found >= 3, f"{found}/5 expected top players found in top 10", f"only {found}/5 expected top players in top 10 — rankings may be wrong")


def check_track_record() -> None:
    path = ROOT / "data" / "track_record.json"
    if not path.exists():
        ISSUES.append("track_record.json missing")
        return
    try:
        json.loads(path.read_text(encoding="utf-8-sig"))
        logger.info("  ✓ track_record.json valid")
    except Exception as e:
        ISSUES.append(f"track_record.json invalid: {e}")
        logger.warning("  ✗ track_record.json invalid: %s", e)


def check_env() -> None:
    key = os.environ.get("THE_ODDS_API_KEY", "")
    check(bool(key), "THE_ODDS_API_KEY set", "THE_ODDS_API_KEY not set — odds fetch will fail")


def main() -> None:
    logger.info("=== Daily health check ===")

    logger.info("Rankings:")
    check_rankings()

    logger.info("Track record:")
    check_track_record()

    logger.info("Environment:")
    check_env()

    logger.info("==========================")
    if ISSUES:
        logger.warning("ISSUES FOUND (%d):", len(ISSUES))
        for i, issue in enumerate(ISSUES, 1):
            logger.warning("  %d. %s", i, issue)
        logger.warning("Pipeline will continue but results may be degraded.")
    else:
        logger.info("All checks passed — pipeline looks healthy.")


if __name__ == "__main__":
    main()
