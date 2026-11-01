"""Extra facts per leg for Jev: ESPN injury report (NBA + NFL), the player's median minutes and what he did against this line last season.

All public data, no keys. NBA minutes / game logs come from nuevas_ideas/data (refreshed with nuevas_ideas/espn_minutes.py); NFL has no
snap counts here, so NFL legs get injuries only.   context(leg) -> one short Spanish text for the leg's description.
"""

import json
import re
import unicodedata
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
MEDIANS = ROOT / "nuevas_ideas" / "data" / "minutes_median.json"
LOGS = ROOT / "nuevas_ideas" / "data" / "logs_2026.json"
URL = "https://site.api.espn.com/apis/site/v2/sports/{}/injuries"
SPORT_PATH = {"nba": "basketball/nba", "nfl": "football/nfl"}
PARTS = {"points": "pts", "rebounds": "reb", "assists": "ast"}

_inj: dict[str, dict] = {}
_logs: dict[str, list] | None = None
_med: dict[str, float] | None = None


def norm(n: str) -> str:
    s = unicodedata.normalize("NFKD", n).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\b(jr|sr|ii|iii|iv)\b\.?", "", s)
    return re.sub(r"[^a-z]+", " ", s).strip()


def injuries(sport: str) -> dict:
    """{'players': {norm name: (status, comment)}, 'out': {team displayName: [(name, status)]}} for Out / Doubtful / Questionable / Day-To-Day."""
    if sport not in _inj:
        players, out = {}, {}
        try:
            data = requests.get(URL.format(SPORT_PATH[sport]), timeout=30).json()
        except (requests.RequestException, ValueError):
            data = {"injuries": []}
        for team in data.get("injuries", []):
            for it in team.get("injuries", []):
                name = (it.get("athlete") or {}).get("displayName")
                status = it.get("status") or ""
                if not name:
                    continue
                players[norm(name)] = (status, (it.get("shortComment") or "")[:140])
                if status.lower() in ("out", "doubtful"):
                    out.setdefault(team.get("displayName", ""), []).append((name, status))
        _inj[sport] = {"players": players, "out": out}
    return _inj[sport]


def _load() -> None:
    global _logs, _med
    if _logs is not None:
        return
    _logs, _med = {}, {}
    if MEDIANS.exists():
        _med = json.loads(MEDIANS.read_text(encoding="utf-8"))
    if LOGS.exists():
        for team in json.loads(LOGS.read_text(encoding="utf-8")).values():
            for name, games in team.items():
                rows = [games[g] for g in sorted(games, key=int, reverse=True)]   # newest first (ESPN event ids grow with the date)
                _logs[norm(name)] = rows


def season_line(leg: dict) -> str:
    """How the player did against this exact line last season (points / rebounds / assists and their sums)."""
    _load()
    keys = [PARTS.get(s) for s in leg["stat"].split("+")]
    rows = _logs.get(norm(leg["player"]), [])
    if not rows or None in keys:
        return ""
    vals = [sum(r[k] for k in keys) for r in rows if all(k in r for k in keys)]
    if len(vals) < 10:
        return ""
    win = (lambda v: v > leg["line"]) if leg["side"] == "Over" else (lambda v: v < leg["line"])
    last = vals[:10]
    return (f'temporada pasada {leg["side"]} {leg["line"]}: {sum(map(win, vals)) / len(vals):.0%} de {len(vals)} partidos '
            f'(media {sum(vals) / len(vals):.1f}); últimos 10: {sum(map(win, last)) / 10:.0%}')


def context(leg: dict) -> str:
    sport = leg["sport"]
    inj = injuries(sport)
    parts = []
    status = inj["players"].get(norm(leg["player"]))
    if status and status[0].lower() != "active":
        parts.append(f"lesión: {status[0]} ({status[1]})")
    else:
        parts.append("lesión: ninguna en el parte")
    mates = [f"{n} ({s})" for n, s in inj["out"].get(leg.get("team", ""), []) if norm(n) != norm(leg["player"])]
    if mates:
        parts.append("compañeros baja: " + ", ".join(mates[:5]))
    if sport == "nba":
        _load()
        m = _med.get(norm(leg["player"]))
        if m:
            parts.append(f"minutos medianos temporada pasada: {m:g}")
        sl = season_line(leg)
        if sl:
            parts.append(sl)
    return " ; ".join(parts)
