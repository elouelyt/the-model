"""Scrape UFC fight history from ESPN Core API — seasons-based, ID-lookup approach."""

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

_OUT = Path(__file__).resolve().parents[1] / "data" / "ufc_fights_history.json"
_FIGHTERS_CACHE = Path(__file__).resolve().parents[1] / "data" / "ufc_fighters_cache.json"
_BASE = "https://sports.core.api.espn.com/v2/sports/mma/leagues/ufc"
_WORKERS = 15
_SEASONS = list(range(2008, 2026))

_METHOD_MAP = {
    "KO/TKO": "KO/TKO", "Submission": "SUB", "Technical Submission": "SUB",
    "Decision": "DEC", "Decision - Unanimous": "DEC", "Decision - Split": "DEC",
    "Decision - Majority": "DEC", "Disqualification": "DQ", "No Contest": "NC",
}


def _make_session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (compatible; UFC-scraper/1.0)"
    retry = Retry(total=3, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503])
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s


def _get(url: str, session: requests.Session | None = None, params: dict | None = None) -> dict | None:
    sess = session or _make_session()
    try:
        r = sess.get(url, params=params, timeout=20)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        logger.debug("GET %s: %s", url, exc)
        return None


def _load_id_map() -> dict[str, str]:
    """Build {espn_id: fighter_name} from fighters cache."""
    if not _FIGHTERS_CACHE.exists():
        logger.warning("fighters cache not found — will skip name lookups")
        return {}
    data = json.loads(_FIGHTERS_CACHE.read_text(encoding="utf-8"))
    id_map: dict[str, str] = {}
    for name, info in data.get("fighters", {}).items():
        eid = str(info.get("espn_id", ""))
        if eid:
            id_map[eid] = name
    logger.info("Loaded %d fighters into ID map", len(id_map))
    return id_map


def _parse_competition(comp: dict, event_name: str, event_date: str, id_map: dict) -> dict | None:
    competitors = comp.get("competitors") or []
    if len(competitors) < 2:
        return None

    winner_name = loser_name = None
    for c in competitors:
        athlete_id = str(c.get("id", ""))
        name = id_map.get(athlete_id, "")
        if not name:
            continue
        if c.get("winner"):
            winner_name = name
        else:
            loser_name = name

    if not winner_name or not loser_name:
        return None

    # weight class from competition type
    ctype = comp.get("type") or {}
    weight_class = ctype.get("text", "") if isinstance(ctype, dict) else ""

    return {
        "winner": winner_name,
        "loser": loser_name,
        "method": "UNK",  # method not in competition-level data
        "weight_class": weight_class,
        "event": event_name,
        "date": event_date,
    }


def _fetch_event_fights(args: tuple) -> list[dict]:
    event_ref, id_map = args
    sess = _make_session()
    data = _get(event_ref, sess)
    if not data:
        return []

    event_name = data.get("name") or data.get("shortName", "")
    event_date = (data.get("date") or "")[:10]

    fights = []
    for comp_item in (data.get("competitions") or []):
        # competitions are embedded in the event — no need to fetch ref
        if not isinstance(comp_item, dict):
            continue
        # comp_item may be inline or a ref
        if "$ref" in comp_item and len(comp_item) <= 3:
            comp_data = _get(comp_item["$ref"], sess)
        else:
            comp_data = comp_item
        if not comp_data:
            continue
        fight = _parse_competition(comp_data, event_name, event_date, id_map)
        if fight:
            fights.append(fight)

    return fights


def _collect_event_refs() -> list[str]:
    refs = []
    for year in _SEASONS:
        year_refs = []
        for stype in [1, 2, 3]:
            url = f"{_BASE}/seasons/{year}/types/{stype}/events"
            page = 1
            while True:
                data = _get(url, params={"limit": 100, "page": page})
                if not data or not data.get("items"):
                    break
                year_refs.extend(item["$ref"] for item in data["items"] if item.get("$ref"))
                if page >= data.get("pageCount", 1):
                    break
                page += 1
        logger.info("  Season %d: %d events", year, len(year_refs))
        refs.extend(year_refs)
        time.sleep(0.05)
    return list(dict.fromkeys(refs))


def main() -> None:
    id_map = _load_id_map()
    if not id_map:
        logger.error("No ESPN IDs in fighters cache — re-run ufc_scrape_fighters.py first")
        raise SystemExit(1)

    logger.info("Collecting event refs from ESPN seasons %d–%d...", _SEASONS[0], _SEASONS[-1])
    all_refs = _collect_event_refs()
    logger.info("Total unique events: %d", len(all_refs))

    if not all_refs:
        logger.error("No events found")
        raise SystemExit(1)

    all_fights: list[dict] = []
    done = 0
    total = len(all_refs)

    with ThreadPoolExecutor(max_workers=_WORKERS) as pool:
        futures = {pool.submit(_fetch_event_fights, (ref, id_map)): ref for ref in all_refs}
        for future in as_completed(futures):
            done += 1
            fights = future.result()
            all_fights.extend(fights)
            pct = done * 100 // total
            bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
            print(f"\r  [{bar}] {pct:3d}%  evento {done}/{total}  ✓ {len(all_fights)} peleas", end="", flush=True)

    print()
    logger.info("Total fights scraped: %d", len(all_fights))

    if not all_fights:
        logger.error("0 fights — check ESPN API or re-run fighters scraper with espn_id")
        raise SystemExit(1)

    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "ESPN Core API (seasons)",
        "count": len(all_fights),
        "fights": all_fights,
    }
    _OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Saved to %s", _OUT)


if __name__ == "__main__":
    main()
