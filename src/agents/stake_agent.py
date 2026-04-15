"""Stake Sports Data API agent — fetches pre-match ATP tennis odds.

Based on the official Stake Sports Data API (OpenAPI 3.1 spec: dist.yaml).
Base URL: https://odds-data.stake.com
Auth:     X-API-KEY header (STAKE_API_KEY env var — omit header if not set,
          the API may be accessible without auth from allowed IPs/regions).

Flow:
  1. GET /sport/tennis/category
       → all tennis categories; filter for ATP singles ones
  2. GET /sport/tennis/category/{cat_slug}/fixture
       → pre-match fixtures per category; each has competitors[] and slug
  3. Fuzzy-match competitors against pipeline player names (early filter —
       avoids fetching odds for fixtures we can't cross-reference)
  4. GET /fixtures/{fixture_slug}    (concurrent)
       → groups → markets → Match Winner outcomes → decimal odds
  5. Return {pipeline_player_name: stake_decimal_price}

Non-fatal throughout — returns {} on any network or parsing failure.
"""

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher

import requests

logger = logging.getLogger(__name__)

_BASE_URL   = "https://odds-data.stake.com"
_TIMEOUT    = 12
_MAX_WORKERS = 6
_FUZZY_CUTOFF = 0.72   # minimum similarity to accept a name match

# Substrings that identify a Match Winner / moneyline market (case-insensitive)
_WINNER_MARKET_FRAGMENTS: frozenset[str] = frozenset({
    "match winner", "moneyline", "twoway",
})

# Substrings that identify an ATP category slug or name (case-insensitive)
_ATP_FRAGMENTS: frozenset[str] = frozenset({
    "atp", "men's singles", "men singles", "men's tour",
})


# ── HTTP helper ────────────────────────────────────────────────────────────────

def _headers() -> dict[str, str]:
    h: dict[str, str] = {
        "Accept":     "application/json",
        "User-Agent": "Mozilla/5.0 (compatible; tennis-ai-pipeline/1.0)",
        "Origin":     "https://stake.com",
        "Referer":    "https://stake.com/",
    }
    api_key = os.getenv("STAKE_API_KEY", "")
    if api_key:
        h["X-API-KEY"] = api_key
    return h


def _get(path: str) -> dict | list | None:
    """GET {_BASE_URL}{path}. Returns parsed JSON or None on any error."""
    url = f"{_BASE_URL}{path}"
    try:
        r = requests.get(url, headers=_headers(), timeout=_TIMEOUT)
        r.raise_for_status()
        return r.json()
    except requests.HTTPError as exc:
        logger.warning("[stake_agent] HTTP %s for %s", exc.response.status_code, path)
    except Exception as exc:
        logger.debug("[stake_agent] GET %s failed: %s", path, exc)
    return None


# ── Fuzzy name matching ────────────────────────────────────────────────────────

def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def _best_match(
    stake_name: str,
    pipeline_names: list[str],
) -> tuple[str | None, float]:
    """Return (best_pipeline_name, score) for a Stake competitor name.

    Compares both the full string and the last token (surname) since Stake
    often uses surname-only names like "Alcaraz" or "Alcaraz C."
    """
    if not stake_name or not pipeline_names:
        return None, 0.0

    # Normalise: strip initials like "C." so "Alcaraz C." → "alcaraz"
    stake_tokens = [t for t in stake_name.split() if not (len(t) <= 2 and t.endswith("."))]
    stake_clean = " ".join(stake_tokens).lower()
    stake_last  = stake_tokens[-1].lower() if stake_tokens else stake_name.lower()

    best_name:  str | None = None
    best_score: float      = 0.0

    for name in pipeline_names:
        pipeline_last = name.split()[-1].lower()

        full_score = _similarity(stake_clean, name)
        last_score = _similarity(stake_last, pipeline_last) * 0.92  # slight last-name penalty

        effective = max(full_score, last_score)
        if effective > best_score:
            best_score = effective
            best_name  = name

    return best_name, best_score


# ── Category helpers ───────────────────────────────────────────────────────────

def _is_atp_category(cat: dict) -> bool:
    text = f"{cat.get('name', '')} {cat.get('slug', '')}".lower()
    return any(frag in text for frag in _ATP_FRAGMENTS)


# ── Odds extraction ────────────────────────────────────────────────────────────

def _extract_winner_odds(fixture_response: dict) -> dict[str, float]:
    """Parse /fixtures/{slug} response → {competitor_name: decimal_odds}.

    Looks inside fixture.groups[].markets[] for an active Match Winner market,
    returns its outcomes keyed by competitor name.
    """
    fixture = fixture_response.get("fixture", fixture_response)
    groups  = fixture.get("groups", [])

    for group in groups:
        for market in group.get("markets", []):
            if market.get("status") != "active":
                continue
            market_name = (market.get("name") or "").lower()
            if not any(frag in market_name for frag in _WINNER_MARKET_FRAGMENTS):
                continue
            outcomes = market.get("outcomes", [])
            if len(outcomes) < 2:
                continue
            result: dict[str, float] = {}
            for outcome in outcomes:
                if outcome.get("active") and outcome.get("odds"):
                    result[outcome["name"]] = float(outcome["odds"])
            if len(result) >= 2:
                return result

    return {}


# ── Public interface ───────────────────────────────────────────────────────────

def fetch_stake_odds(pipeline_player_names: list[str]) -> dict[str, float]:
    """Fetch Stake pre-match moneyline odds and cross-reference with pipeline players.

    Args:
        pipeline_player_names: Full player names from the current pipeline run
            (e.g. ["Carlos Alcaraz", "Jannik Sinner", ...]).

    Returns:
        Dict mapping each matched pipeline player name to their Stake decimal
        odds.  Empty dict if the API is unreachable or no fixtures match.

    Example return value::

        {
            "Carlos Alcaraz": 1.25,
            "Jannik Sinner":  3.80,
            "Alexander Zverev": 1.57,
        }
    """
    if not pipeline_player_names:
        return {}

    # ── Step 1: tennis categories ─────────────────────────────────────────────
    data = _get("/sport/tennis/category")
    if data is None:
        logger.warning("[stake_agent] /sport/tennis/category unreachable — skipping Stake odds")
        return {}

    raw_cats = data.get("category", []) if isinstance(data, dict) else (data or [])
    atp_cats = [c for c in raw_cats if _is_atp_category(c)]

    if not atp_cats:
        logger.info("[stake_agent] No ATP categories found — falling back to all tennis categories (%d)", len(raw_cats))
        atp_cats = raw_cats  # graceful fallback: use everything

    logger.info("[stake_agent] %d ATP categories to scan", len(atp_cats))

    # ── Step 2: pre-match fixtures per category ───────────────────────────────
    candidate_fixtures: list[dict] = []

    for cat in atp_cats:
        cat_slug = cat.get("slug", "")
        if not cat_slug:
            continue

        fix_data = _get(f"/sport/tennis/category/{cat_slug}/fixture")
        if not fix_data:
            continue

        fixtures = fix_data.get("fixture", []) if isinstance(fix_data, dict) else (fix_data or [])
        for fix in fixtures:
            if fix.get("status") != "active":
                continue  # skip live / ended
            competitors: list[str] = fix.get("competitors", [])
            slug: str = fix.get("slug", "")
            if len(competitors) >= 2 and slug:
                candidate_fixtures.append({
                    "slug":        slug,
                    "competitors": competitors,
                    "name":        fix.get("name", slug),
                })

    logger.info("[stake_agent] %d pre-match fixtures found across ATP categories", len(candidate_fixtures))

    if not candidate_fixtures:
        return {}

    # ── Step 3: fuzzy-filter — only fetch odds for relevant fixtures ──────────
    relevant: list[dict] = []

    for fix in candidate_fixtures:
        hits: dict[str, str] = {}  # stake_name → pipeline_name
        for competitor in fix["competitors"]:
            pipeline_name, score = _best_match(competitor, pipeline_player_names)
            if pipeline_name and score >= _FUZZY_CUTOFF:
                hits[competitor] = pipeline_name
        if hits:
            fix["hits"] = hits
            relevant.append(fix)

    logger.info("[stake_agent] %d fixtures matched pipeline players (fuzzy cutoff %.2f)", len(relevant), _FUZZY_CUTOFF)

    if not relevant:
        return {}

    # ── Step 4: fetch full odds concurrently ──────────────────────────────────
    stake_odds: dict[str, float] = {}

    def _fetch_odds(fix: dict) -> dict[str, float]:
        odds_resp = _get(f"/fixtures/{fix['slug']}")
        if not odds_resp:
            return {}
        winner_odds = _extract_winner_odds(odds_resp)
        out: dict[str, float] = {}
        for stake_name, price in winner_odds.items():
            pipeline_name, score = _best_match(stake_name, pipeline_player_names)
            if pipeline_name and score >= _FUZZY_CUTOFF:
                out[pipeline_name] = price
                logger.debug(
                    "[stake_agent] %r → %r (score=%.2f) @ %.3f",
                    stake_name, pipeline_name, score, price,
                )
        return out

    max_w = min(_MAX_WORKERS, len(relevant))
    with ThreadPoolExecutor(max_workers=max_w) as executor:
        futures = {executor.submit(_fetch_odds, fix): fix["name"] for fix in relevant}
        for future in as_completed(futures):
            fixture_name = futures[future]
            try:
                stake_odds.update(future.result())
            except Exception as exc:
                logger.warning("[stake_agent] Error fetching %s: %s", fixture_name, exc)

    logger.info(
        "[stake_agent] Done — Stake odds available for %d / %d pipeline players",
        len(stake_odds), len(pipeline_player_names),
    )
    return stake_odds
