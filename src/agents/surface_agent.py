"""Surface lookup agent — maps ATP sport keys to court surface types.

Uses a static lookup table covering all current ATP Tour events.
Matches by substring so partial/variant sport keys still resolve correctly.
Unknown keys default to "hard" (the most common ATP surface) with a warning.
"""

import logging

logger = logging.getLogger(__name__)

# Ordered lookup: first matching fragment wins.
# Longer/more-specific fragments must come before shorter ones to avoid
# false matches (e.g. "paris" before "hard").
_SURFACE_MAP: list[tuple[str, str]] = [
    # ── Grass ────────────────────────────────────────────────────────────────
    ("wimbledon",       "grass"),
    ("halle",           "grass"),
    ("queens",          "grass"),
    ("eastbourne",      "grass"),
    ("newport",         "grass"),
    ("hertogenbosch",   "grass"),
    ("mallorca",        "grass"),
    ("nottingham",      "grass"),
    ("stuttgart",       "grass"),   # currently grass (was clay pre-2015)
    # ── Clay ─────────────────────────────────────────────────────────────────
    ("roland_garros",   "clay"),
    ("monte_carlo",     "clay"),
    ("madrid",          "clay"),
    ("rome",            "clay"),
    ("barcelona",       "clay"),
    ("hamburg",         "clay"),
    ("rio",             "clay"),
    ("buenos_aires",    "clay"),
    ("santiago",        "clay"),
    ("marrakech",       "clay"),
    ("munich",          "clay"),
    ("lyon",            "clay"),
    ("geneva",          "clay"),
    ("kitzbuhel",       "clay"),
    ("umag",            "clay"),
    ("bastad",          "clay"),
    ("gstaad",          "clay"),
    ("cordoba",         "clay"),
    ("estoril",         "clay"),
    ("bucharest",       "clay"),
    ("budapest",        "clay"),
    ("istanbul",        "clay"),
    ("casablanca",      "clay"),
    # ── Indoor hard ──────────────────────────────────────────────────────────
    ("nitto",           "indoor_hard"),   # ATP Finals
    ("atp_finals",      "indoor_hard"),
    ("next_gen",        "indoor_hard"),
    ("paris",           "indoor_hard"),
    ("vienna",          "indoor_hard"),
    ("basel",           "indoor_hard"),
    ("rotterdam",       "indoor_hard"),
    ("marseille",       "indoor_hard"),
    ("montpellier",     "indoor_hard"),
    ("metz",            "indoor_hard"),
    ("antwerp",         "indoor_hard"),
    ("stockholm",       "indoor_hard"),
    ("sofia",           "indoor_hard"),
    ("dallas",          "indoor_hard"),
    ("memphis",         "indoor_hard"),
    ("milan",           "indoor_hard"),
    # ── Outdoor hard (explicit before generic fallback) ──────────────────────
    ("australian_open", "hard"),
    ("us_open",         "hard"),
    ("indian_wells",    "hard"),
    ("miami",           "hard"),
    ("toronto",         "hard"),
    ("montreal",        "hard"),
    ("canada",          "hard"),
    ("cincinnati",      "hard"),
    ("washington",      "hard"),
    ("beijing",         "hard"),
    ("shanghai",        "hard"),
    ("tokyo",           "hard"),
    ("dubai",           "hard"),
    ("doha",            "hard"),
    ("abu_dhabi",       "hard"),
    ("brisbane",        "hard"),
    ("adelaide",        "hard"),
    ("auckland",        "hard"),
    ("acapulco",        "hard"),
    ("los_cabos",       "hard"),
    ("winston_salem",   "hard"),
    ("atlanta",         "hard"),
    ("houston",         "hard"),
    ("seoul",           "hard"),
    ("chengdu",         "hard"),
    ("hangzhou",        "hard"),
    ("astana",          "hard"),
    ("nur_sultan",      "hard"),
    ("st_petersburg",   "hard"),
    ("pune",            "hard"),
    ("chennai",         "hard"),
    ("hong_kong",       "hard"),
    ("zhuhai",          "hard"),
    ("buenos",          "clay"),    # catch "buenos_aires" variants
]

# Human-readable labels for each surface
SURFACE_LABEL: dict[str, str] = {
    "clay":         "Clay",
    "grass":        "Grass",
    "hard":         "Hard",
    "indoor_hard":  "Indoor Hard",
}

# Short context note appended to recommendations — highlights where the
# ranking-points model is most likely to miss surface specialists.
SURFACE_NOTE: dict[str, str | None] = {
    "clay":         "Clay court — surface specialists may outperform the ranking model.",
    "grass":        "Grass court — serve and net skills add variance beyond rankings.",
    "indoor_hard":  "Indoor hard — fast, low-bounce conditions favour big servers.",
    "hard":         None,   # most generic surface; no special caveat needed
}


def get_surface(sport_key: str) -> str:
    """Return the court surface for a given ATP sport key.

    Iterates the lookup table in order and returns the surface for the first
    matching fragment. Defaults to ``"hard"`` for unknown keys.

    Args:
        sport_key: The-Odds-API sport key, e.g. ``"tennis_atp_roland_garros"``.

    Returns:
        One of ``"clay"``, ``"grass"``, ``"hard"``, ``"indoor_hard"``.
    """
    key_lower = sport_key.lower()
    for fragment, surface in _SURFACE_MAP:
        if fragment in key_lower:
            logger.debug("Surface resolved: %r → %s (fragment=%r)", sport_key, surface, fragment)
            return surface

    logger.warning("Unknown surface for sport_key %r — defaulting to 'hard'", sport_key)
    return "hard"
