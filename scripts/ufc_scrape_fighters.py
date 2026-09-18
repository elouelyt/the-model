"""Scrape UFC fighter stats from ESPN Core API — parallel version."""

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logging.basicConfig(level=logging.INFO, format="%(asctime)s — %(levelname)s — %(message)s")
logger = logging.getLogger(__name__)

_OUT = Path(__file__).resolve().parents[1] / "data" / "ufc_fighters_cache.json"
_BASE = "https://sports.core.api.espn.com/v2/sports/mma/leagues/ufc"
_WORKERS = 20


def _make_session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (compatible; UFC-scraper/1.0)"
    retry = Retry(total=3, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503])
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s


_SESSION = _make_session()


def _get(url: str, session: requests.Session | None = None, params: dict | None = None) -> dict | None:
    sess = session or _SESSION
    try:
        r = sess.get(url, params=params, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        logger.debug("GET %s failed: %s", url, exc)
        return None


def _espn_id_from_ref(ref: str) -> str:
    # e.g. "…/athletes/4916248?lang=…" → "4916248"
    import re
    m = re.search(r"/athletes/(\d+)", ref)
    return m.group(1) if m else ""


def _fetch_fighter(ref: str) -> dict | None:
    sess = _make_session()
    detail = _get(ref, sess)
    if not detail:
        return None

    name = detail.get("fullName") or detail.get("displayName")
    if not name:
        return None

    espn_id = _espn_id_from_ref(ref)
    height_in = detail.get("height")
    weight_lbs = detail.get("weight")
    height_cm = round(height_in * 2.54, 1) if height_in else None

    # fetch records inline
    wins = losses = tkos = subs = 0
    records_ref_data = detail.get("records")
    if isinstance(records_ref_data, dict) and "$ref" in records_ref_data:
        rec = _get(records_ref_data["$ref"], sess)
        if rec:
            stats = {}
            for item in rec.get("items", []):
                for s in item.get("stats", []):
                    stats[s["name"]] = s.get("value", 0)
            wins = int(stats.get("wins", 0))
            losses = int(stats.get("losses", 0))
            tkos = int(stats.get("tkos", 0))
            subs = int(stats.get("submissions", 0))

    total_finishes = tkos + subs
    finish_rate = round(total_finishes / wins, 4) if wins > 0 else 0.0
    win_rate = round(wins / (wins + losses), 4) if (wins + losses) > 0 else 0.5

    return {
        "name": name,
        "espn_id": espn_id,
        "height_cm": height_cm,
        "weight_lbs": weight_lbs,
        "reach_cm": None,
        "age": detail.get("age"),
        "wins": wins,
        "losses": losses,
        "tkos": tkos,
        "submissions": subs,
        "finish_rate": finish_rate,
        "win_rate": win_rate,
    }


def _collect_refs() -> list[str]:
    refs = []
    page = 1
    while True:
        data = _get(f"{_BASE}/athletes", params={"limit": 100, "page": page})
        if not data:
            break
        items = data.get("items", [])
        if not items:
            break
        refs.extend(item["$ref"] for item in items if item.get("$ref"))
        total_pages = data.get("pageCount", 1)
        if page >= total_pages:
            break
        page += 1
        time.sleep(0.1)
    return refs


def main() -> None:
    logger.info("Collecting fighter refs...")
    refs = _collect_refs()
    logger.info("Found %d fighters — fetching details with %d workers...", len(refs), _WORKERS)

    fighters: dict[str, dict] = {}
    done = 0

    with ThreadPoolExecutor(max_workers=_WORKERS) as pool:
        future_to_ref = {pool.submit(_fetch_fighter, ref): ref for ref in refs}
        for future in as_completed(future_to_ref):
            done += 1
            result = future.result()
            if result:
                fighters[result["name"]] = result
                pct = done * 100 // len(refs)
                bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
                print(f"\r  [{bar}] {pct:3d}%  {done}/{len(refs)}  ✓ {len(fighters)} guardados", end="", flush=True)
            elif done % 50 == 0:
                pct = done * 100 // len(refs)
                bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
                print(f"\r  [{bar}] {pct:3d}%  {done}/{len(refs)}  ✓ {len(fighters)} guardados", end="", flush=True)
    print()  # newline after progress bar

    logger.info("Done. Total fighters: %d", len(fighters))

    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "ESPN Core API",
        "count": len(fighters),
        "fighters": fighters,
    }
    _OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Saved to %s", _OUT)


if __name__ == "__main__":
    main()
