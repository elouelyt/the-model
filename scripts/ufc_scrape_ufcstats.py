"""Scrape fighter career stats from ufcstats.com — fills in reach_cm, sig_str_def,
td_def (never available from ESPN) and gives a second, more complete source for
sig_str_acc / td_acc.

ufcstats.com fronts every request with a small JS proof-of-work challenge (find n such
that sha256(f"{nonce}:{n}") starts with N zero hex digits, POST it to /__c, then retry).
It's solved here directly in Python - cheap (2 leading zeros), no browser needed.

Merges results into data/ufc_fighters_cache.json (matched by exact full name; fighters
with no match are skipped - this script only enriches the existing ESPN-sourced roster,
it doesn't replace it).
"""

import hashlib
import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logging.basicConfig(level=logging.INFO, format="%(asctime)s — %(levelname)s — %(message)s")
logger = logging.getLogger(__name__)

_BASE = "http://ufcstats.com"
_FIGHTERS_CACHE = Path(__file__).resolve().parents[1] / "data" / "ufc_fighters_cache.json"
_OUT = Path(__file__).resolve().parents[1] / "data" / "ufcstats_cache.json"
_WORKERS = 15
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


def _solve_pow(session: requests.Session, html: str) -> bool:
    m_nonce = re.search(r'var nonce="([0-9a-f]+)"', html)
    m_target = re.search(r"target=new Array\((\d+)\+1\).join", html)
    if not m_nonce or not m_target:
        return False
    nonce = m_nonce.group(1)
    zeros = int(m_target.group(1))
    target = "0" * zeros
    n = 0
    while hashlib.sha256(f"{nonce}:{n}".encode()).hexdigest()[:zeros] != target:
        n += 1
    r = session.post(f"{_BASE}/__c", data={"nonce": nonce, "n": n}, timeout=20)
    return r.status_code in (200, 204)


def _make_session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = _UA
    retry = Retry(total=3, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503])
    s.mount("http://", HTTPAdapter(max_retries=retry))
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s


def _get_authed_session() -> requests.Session:
    """One session with the PoW solved. Its cookie is reused (not re-solved) by workers."""
    s = _make_session()
    r = s.get(f"{_BASE}/", timeout=20)
    if "Checking your browser" in r.text:
        _solve_pow(s, r.text)
    return s


def _collect_fighter_links(auth_cookie: dict) -> list[str]:
    links: set[str] = set()
    for ch in "abcdefghijklmnopqrstuvwxyz":
        s = _make_session()
        s.cookies.update(auth_cookie)
        r = s.get(f"{_BASE}/statistics/fighters", params={"char": ch, "page": "all"}, timeout=30)
        if "Checking your browser" in r.text:
            _solve_pow(s, r.text)
            r = s.get(f"{_BASE}/statistics/fighters", params={"char": ch, "page": "all"}, timeout=30)
        found = re.findall(r'href="(http://ufcstats\.com/fighter-details/[a-f0-9]+)"', r.text)
        links.update(found)
        logger.info("char=%s -> %d fighter links (total so far: %d)", ch, len(set(found)), len(links))
        time.sleep(0.1)
    return sorted(links)


_HT_RE = re.compile(r"(\d+)'\s*(\d+)\"")
_PCT_RE = re.compile(r"(\d+)\s*%")
_NUM_RE = re.compile(r"[\d.]+")


def _parse_fighter(url: str, auth_cookie: dict) -> dict | None:
    s = _make_session()
    s.cookies.update(auth_cookie)
    try:
        r = s.get(url, timeout=20)
        if "Checking your browser" in r.text:
            _solve_pow(s, r.text)
            r = s.get(url, timeout=20)
        html = r.text
    except Exception as exc:
        logger.debug("fetch failed for %s: %s", url, exc)
        return None

    m_name = re.search(r'b-content__title-highlight">\s*([^<]+?)\s*</span>', html)
    if not m_name:
        return None
    name = m_name.group(1).strip()

    def field(label: str) -> str | None:
        m = re.search(rf"{re.escape(label)}:\s*</i>\s*([^<]*)", html)
        return m.group(1).strip() if m else None

    height_raw = field("Height")
    reach_raw = field("Reach")
    stance = field("STANCE")
    slpm = field("SLpM")
    str_acc = field("Str. Acc.")
    sapm = field("SApM")
    str_def = field("Str. Def")
    td_avg = field("TD Avg.")
    td_acc = field("TD Acc.")
    td_def = field("TD Def.")
    sub_avg = field("Sub. Avg.")

    height_cm = None
    if height_raw:
        m = _HT_RE.search(height_raw)
        if m:
            height_cm = round((int(m.group(1)) * 12 + int(m.group(2))) * 2.54, 1)

    reach_cm = None
    if reach_raw and reach_raw.strip() not in ("", "--"):
        m = _NUM_RE.search(reach_raw)
        if m:
            reach_cm = round(float(m.group()) * 2.54, 1)

    def pct(raw: str | None) -> float | None:
        if not raw or raw.strip() in ("", "--"):
            return None
        m = _PCT_RE.search(raw)
        return round(int(m.group(1)) / 100.0, 4) if m else None

    def num(raw: str | None) -> float | None:
        if not raw or raw.strip() in ("", "--"):
            return None
        m = _NUM_RE.search(raw)
        return float(m.group()) if m else None

    return {
        "name": name,
        "height_cm": height_cm,
        "reach_cm": reach_cm,
        "stance": stance,
        "slpm": num(slpm),
        "sig_str_acc": pct(str_acc),
        "sapm": num(sapm),
        "sig_str_def": pct(str_def),
        "td_avg": num(td_avg),
        "td_acc": pct(td_acc),
        "td_def": pct(td_def),
        "sub_avg": num(sub_avg),
    }


def main() -> None:
    logger.info("Solving ufcstats.com proof-of-work challenge...")
    auth_session = _get_authed_session()
    auth_cookie = auth_session.cookies.get_dict()
    logger.info("Authenticated (cookie: %s)", list(auth_cookie.keys()))

    logger.info("Collecting fighter links (a-z)...")
    links = _collect_fighter_links(auth_cookie)
    logger.info("Found %d unique fighter links — fetching details with %d workers...", len(links), _WORKERS)

    fighters: dict[str, dict] = {}
    done = 0
    with ThreadPoolExecutor(max_workers=_WORKERS) as pool:
        futures = {pool.submit(_parse_fighter, url, auth_cookie): url for url in links}
        for fut in as_completed(futures):
            done += 1
            result = fut.result()
            if result:
                fighters[result["name"]] = result
            if done % 100 == 0:
                logger.info("  %d/%d done (%d parsed OK)", done, len(links), len(fighters))

    logger.info("Done. Parsed %d fighters.", len(fighters))

    _OUT.write_text(json.dumps({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "ufcstats.com",
        "count": len(fighters),
        "fighters": fighters,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Raw ufcstats cache saved to %s", _OUT)

    # --- Merge into the main ESPN-sourced cache (exact name match only) ---
    if not _FIGHTERS_CACHE.exists():
        logger.warning("%s not found — skipping merge", _FIGHTERS_CACHE)
        return

    main_cache = json.loads(_FIGHTERS_CACHE.read_text(encoding="utf-8"))
    main_fighters = main_cache.get("fighters", {})

    merged = 0
    filled_reach = filled_str_def = filled_td_def = 0
    for name, uf in fighters.items():
        target = main_fighters.get(name)
        if target is None:
            continue
        merged += 1
        if target.get("reach_cm") is None and uf.get("reach_cm") is not None:
            target["reach_cm"] = uf["reach_cm"]
            filled_reach += 1
        if uf.get("sig_str_def") is not None:
            target["sig_str_def"] = uf["sig_str_def"]
            filled_str_def += 1
        if uf.get("td_def") is not None:
            target["td_def"] = uf["td_def"]
            filled_td_def += 1
        # Prefer ufcstats for sig_str_acc/td_acc if ESPN didn't have it
        if target.get("sig_str_acc") is None and uf.get("sig_str_acc") is not None:
            target["sig_str_acc"] = uf["sig_str_acc"]
        if target.get("td_acc") is None and uf.get("td_acc") is not None:
            target["td_acc"] = uf["td_acc"]

    logger.info(
        "Merged %d/%d ufcstats fighters into main cache (reach filled: %d, str_def: %d, td_def: %d)",
        merged, len(fighters), filled_reach, filled_str_def, filled_td_def,
    )

    main_cache["fighters"] = main_fighters
    main_cache["ufcstats_merged_at"] = datetime.now(timezone.utc).isoformat()
    _FIGHTERS_CACHE.write_text(json.dumps(main_cache, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Updated %s", _FIGHTERS_CACHE)


if __name__ == "__main__":
    main()
