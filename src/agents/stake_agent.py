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
  4. GET /odds/{fixture_slug}    (concurrent)
       → groups[][].markets[][] → "Winner" market (specifiers="") → decimal odds
  5. Return {pipeline_player_name: stake_decimal_price}

Non-fatal throughout — returns {} on any network or parsing failure.
"""

import logging
import os
from difflib import SequenceMatcher

import requests

logger = logging.getLogger(__name__)

_BASE_URL   = "https://odds-data.stake.com"
_TIMEOUT    = 12
_MAX_WORKERS = 6
_FUZZY_CUTOFF = 0.72   # minimum similarity to accept a name match

# Substrings that identify an ATP category slug or name (case-insensitive)
_ATP_FRAGMENTS: frozenset[str] = frozenset({
    "atp", "men's singles", "men singles", "men's tour",
})


# ── HTTP session (shared across all requests to preserve Cloudflare cookies) ───

def _make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "Accept":     "application/json",
        "User-Agent": "Mozilla/5.0 (compatible; tennis-ai-pipeline/1.0)",
        "Origin":     "https://stake.com",
        "Referer":    "https://stake.com/",
    })
    api_key = os.getenv("STAKE_API_KEY", "")
    if api_key:
        s.headers["X-API-KEY"] = api_key
    return s


_SESSION: requests.Session = _make_session()


def _get(path: str) -> dict | list | None:
    """GET {_BASE_URL}{path} using the shared session.

    Using a session preserves Cloudflare cookies (e.g. __cf_bm) set on
    the first request so subsequent requests to /odds/ are not blocked.
    Returns parsed JSON or None on any error.
    """
    url = f"{_BASE_URL}{path}"
    try:
        r = _SESSION.get(url, timeout=_TIMEOUT)
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


def _is_initial(token: str) -> bool:
    """Return True for single-letter tokens like 'C', 'C.', 'De.' etc."""
    t = token.rstrip(".")
    return len(t) <= 1


def _normalize_stake_name(name: str) -> list[str]:
    """Return all plausible normalized forms of a Stake/Betradar competitor name.

    Handles the main Betradar formats:
      "Alcaraz, Carlos"   → ["Carlos Alcaraz", "Alcaraz"]
      "Alcaraz C."        → ["Alcaraz"]
      "C. Alcaraz"        → ["Alcaraz"]
      "Alcaraz"           → ["Alcaraz"]
      "Carlos Alcaraz"    → ["Carlos Alcaraz", "Alcaraz"]
    """
    name = name.strip()
    if not name:
        return []

    candidates: list[str] = []

    # ── Format 1: "Lastname, Firstname" (Betradar standard) ──────────────────
    if "," in name:
        parts = [p.strip() for p in name.split(",", 1)]
        last_part  = parts[0].strip()
        first_part = parts[1].strip() if len(parts) > 1 else ""

        # Strip any initials from first_part ("Carlos" stays, "C." becomes "")
        first_tokens = [t for t in first_part.split() if not _is_initial(t)]
        first_clean  = " ".join(first_tokens)

        if first_clean:
            # "Carlos Alcaraz" — the canonical pipeline format
            candidates.append(f"{first_clean} {last_part}")
        # surname alone as fallback
        candidates.append(last_part)

    else:
        # ── Format 2 / 3 / 4: no comma — strip initials, keep real tokens ────
        tokens     = name.split()
        real_tokens = [t for t in tokens if not _is_initial(t)]
        clean      = " ".join(real_tokens).strip()

        if clean:
            candidates.append(clean)
            # Also try reversed order in case it's "Lastname Firstname" without comma
            if len(real_tokens) == 2:
                candidates.append(f"{real_tokens[1]} {real_tokens[0]}")
            # Surname-only fallback (last real token)
            candidates.append(real_tokens[-1])
        else:
            # All tokens were initials — keep original
            candidates.append(name)

    # Deduplicate while preserving order
    seen: set[str] = set()
    result: list[str] = []
    for c in candidates:
        cl = c.lower()
        if cl not in seen and c:
            seen.add(cl)
            result.append(c)
    return result


def _best_match(
    stake_name: str,
    pipeline_names: list[str],
) -> tuple[str | None, float]:
    """Return (best_pipeline_name, score) for a Stake competitor name.

    Generates multiple normalized candidate forms for the Stake name (handling
    Betradar formats: "Lastname, Firstname", "Lastname C.", "C. Lastname",
    "Lastname") and compares each against every pipeline name and its surname.
    """
    if not stake_name or not pipeline_names:
        return None, 0.0

    stake_candidates = _normalize_stake_name(stake_name)
    logger.debug(
        "[stake_agent] Stake name %r → normalized candidates: %s",
        stake_name, stake_candidates,
    )

    best_name:  str | None = None
    best_score: float      = 0.0

    for pipeline_name in pipeline_names:
        pipeline_last  = pipeline_name.split()[-1].lower()
        pipeline_lower = pipeline_name.lower()

        for candidate in stake_candidates:
            cand_lower = candidate.lower()
            cand_last  = candidate.split()[-1].lower()

            # Full-string similarity
            full_score = _similarity(cand_lower, pipeline_lower)

            # Surname-only similarity (both directions, slight penalty)
            last_score = max(
                _similarity(cand_last, pipeline_last),
                _similarity(cand_lower, pipeline_last),
            ) * 0.90

            effective = max(full_score, last_score)
            if effective > best_score:
                best_score = effective
                best_name  = pipeline_name

    logger.debug(
        "[stake_agent] Best match for %r → %r (score=%.3f)",
        stake_name, best_name, best_score,
    )
    return best_name, best_score


# ── Category helpers ───────────────────────────────────────────────────────────

def _is_atp_category(cat: dict) -> bool:
    text = f"{cat.get('name', '')} {cat.get('slug', '')}".lower()
    return any(frag in text for frag in _ATP_FRAGMENTS)


# ── Odds extraction ────────────────────────────────────────────────────────────

def _extract_winner_odds(odds_response: dict) -> dict[str, float]:
    """Parse GET /odds/{slug} response → {player_full_name: decimal_odds}.

    Mirrors test.py exactly: iterates data.get("groups", []) at the top level
    (no "fixture" wrapper), then markets[][] double-array, finds market where
    name == "Winner" and specifiers == "".
    """
    for group in odds_response.get("groups", []):
        for market_list in group.get("markets", []):
            if not isinstance(market_list, list):
                market_list = [market_list]
            for market in market_list:
                if market.get("name") == "Winner" and market.get("specifiers") == "":
                    outcomes = market.get("outcomes", [])
                    result: dict[str, float] = {
                        o["name"]: float(o["odds"])
                        for o in outcomes
                        if o.get("name") and o.get("odds")
                    }
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

    # ── Step 1: ATP tournaments (mirrors test.py exactly — hardcoded "atp" slug) ─
    # Dynamic category discovery added overhead and a different request pattern
    # vs test.py. Using the "atp" slug directly avoids the extra roundtrip and
    # keeps the session cookie state identical to the working test script.
    tour_data = _SESSION.get(f"{_BASE_URL}/sport/tennis/category/atp/tournament", timeout=_TIMEOUT)
    if not tour_data.ok:
        logger.warning("[stake_agent] /category/atp/tournament returned %s — skipping Stake odds", tour_data.status_code)
        return {}

    try:
        tournaments = tour_data.json().get("tournament", [])
    except Exception:
        logger.warning("[stake_agent] Failed to parse tournament list")
        return {}

    logger.info("[stake_agent] %d ATP tournaments found", len(tournaments))

    # ── Step 2: fixtures per singles tournament ───────────────────────────────
    all_fixtures: list[dict] = []
    seen_slugs: set[str] = set()

    for tour in tournaments:
        tour_slug = tour.get("slug", "")
        tour_name = tour.get("name", tour_slug).lower()
        if not tour_slug:
            continue
        # Skip doubles (mirrors test.py filter)
        if "double" in tour_slug or "double" in tour_name:
            logger.debug("[stake_agent] Skipping doubles: %s", tour_slug)
            continue
        resp = _SESSION.get(
            f"{_BASE_URL}/sport/tennis/category/atp/tournament/{tour_slug}/fixture",
            timeout=_TIMEOUT,
        )
        if not resp.ok:
            continue
        try:
            fixtures = resp.json().get("fixture", [])
        except Exception:
            continue
        for fix in fixtures:
            slug = fix.get("slug", "")
            if slug and slug not in seen_slugs:
                seen_slugs.add(slug)
                all_fixtures.append(fix)

    logger.info("[stake_agent] %d pre-match fixtures across ATP singles tournaments", len(all_fixtures))

    if not all_fixtures:
        return {}

    # ── Step 3: sequential /odds/ calls + player matching (mirrors test.py) ───
    # ThreadPoolExecutor was triggering Cloudflare rate-limiting (groups=[]).
    # Sequential calls with the shared session reproduce the working test.py flow.
    logger.info("[stake_agent] Pipeline players: %s", pipeline_player_names)
    stake_odds: dict[str, float] = {}

    for fix in all_fixtures:
        slug = fix.get("slug", "")
        name = fix.get("name", slug)
        if not slug:
            continue

        resp = _SESSION.get(f"{_BASE_URL}/odds/{slug}", timeout=_TIMEOUT)
        if not resp.ok:
            logger.debug("[stake_agent] /odds/%s → HTTP %s", slug, resp.status_code)
            continue
        try:
            data = resp.json()
        except Exception:
            continue

        winner_odds = _extract_winner_odds(data)
        logger.info("[stake_agent] %r — Stake outcomes: %s", name, list(winner_odds.keys()))

        for stake_name, price in winner_odds.items():
            pipeline_name, score = _best_match(stake_name, pipeline_player_names)
            if pipeline_name and score >= _FUZZY_CUTOFF:
                stake_odds[pipeline_name] = price
                logger.info(
                    "[stake_agent] MATCHED %r → %r (score=%.3f) @ %.3f",
                    stake_name, pipeline_name, score, price,
                )

    logger.info(
        "[stake_agent] Done — Stake odds for %d / %d pipeline players",
        len(stake_odds), len(pipeline_player_names),
    )
    return stake_odds
