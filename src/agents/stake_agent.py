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

    Looks inside groups[].markets[] for the market where:
      - name == "Winner"  (exact, case-insensitive)
      - specifiers == ""  (empty string — picks the plain match-winner, not
                           set/game handicap variants which share the same name)

    Outcome names from this endpoint are full player names ("Carlos Alcaraz"),
    so no extra normalisation is needed before fuzzy matching.
    """
    # /odds/{slug} returns the fixture object directly (no "fixture" wrapper)
    fixture = odds_response.get("fixture", odds_response)
    groups  = fixture.get("groups", [])

    for group in groups:
        for market in group.get("markets", []):
            if market.get("status") != "active":
                continue
            market_name  = (market.get("name") or "").strip()
            market_specs = (market.get("specifiers") or "").strip()
            if market_name.lower() != "winner" or market_specs != "":
                continue
            outcomes = market.get("outcomes", [])
            if len(outcomes) < 2:
                continue
            result: dict[str, float] = {}
            for outcome in outcomes:
                name  = (outcome.get("name") or "").strip()
                price = outcome.get("odds")
                if outcome.get("active") and price and name:
                    result[name] = float(price)
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
    logger.info(
        "[stake_agent] Pipeline player names for matching: %s",
        pipeline_player_names,
    )
    stake_odds: dict[str, float] = {}

    def _fetch_odds(fix: dict) -> dict[str, float]:
        odds_resp = _get(f"/odds/{fix['slug']}")
        if not odds_resp:
            return {}
        winner_odds = _extract_winner_odds(odds_resp)
        logger.info(
            "[stake_agent] Fixture %r — raw outcome names from Stake: %s",
            fix["slug"], list(winner_odds.keys()),
        )
        out: dict[str, float] = {}
        for stake_name, price in winner_odds.items():
            pipeline_name, score = _best_match(stake_name, pipeline_player_names)
            logger.info(
                "[stake_agent] Match attempt: Stake=%r → pipeline=%r (score=%.3f, cutoff=%.2f, pass=%s)",
                stake_name, pipeline_name, score, _FUZZY_CUTOFF, score >= _FUZZY_CUTOFF,
            )
            if pipeline_name and score >= _FUZZY_CUTOFF:
                out[pipeline_name] = price
                logger.info(
                    "[stake_agent] MATCHED %r → %r (score=%.3f) @ %.3f",
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
