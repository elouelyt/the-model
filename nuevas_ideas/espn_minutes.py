"""Download last season's regular-season game logs from ESPN and write data/minutes_median.json
(normalised player name -> median minutes) plus data/logs_2026.json (per-game pts/reb/ast/min, used by the
synergy analysis in ideas/05_sinergias_descartada). Run it once in a while (about 4 minutes, ~450 requests).

    python nuevas_ideas/espn_minutes.py [season]    # ESPN season = end year, 2026 = 2025-26
"""

import json
import re
import statistics as st
import sys
import time
import unicodedata
from pathlib import Path

import requests

BASE = Path(__file__).resolve().parent
H = {"User-Agent": "Mozilla/5.0"}
SEASON = sys.argv[1] if len(sys.argv) > 1 else "2026"


def norm(n: str) -> str:
    s = unicodedata.normalize("NFKD", n).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\b(jr|sr|ii|iii|iv)\b\.?", "", s)
    return re.sub(r"[^a-z]+", " ", s).strip()


def get(url: str) -> dict | None:
    for _ in range(3):
        try:
            r = requests.get(url, headers=H, timeout=30)
            if r.status_code == 200:
                return r.json()
        except requests.RequestException:
            pass
        time.sleep(1)
    return None


def main() -> None:
    teams = get("https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams")
    out: dict[str, dict] = {}
    for t in teams["sports"][0]["leagues"][0]["teams"]:
        tid, ab = t["team"]["id"], t["team"]["abbreviation"]
        roster = get(f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{tid}/roster") or {"athletes": []}
        team = {}
        for a in roster["athletes"]:
            g = get(f"https://site.web.api.espn.com/apis/common/v3/sports/basketball/nba/athletes/{a['id']}/gamelog?season={SEASON}")
            time.sleep(0.15)
            if not g:
                continue
            games = {}
            for stype in g.get("seasonTypes", []):
                if "Regular Season" not in stype.get("displayName", ""):
                    continue
                for cat in stype.get("categories", []):
                    for ev in cat.get("events", []):
                        s = ev["stats"]
                        try:
                            games[ev["eventId"]] = {"min": float(s[0]), "reb": float(s[7]), "ast": float(s[8]), "pts": float(s[13])}
                        except (ValueError, IndexError):
                            continue
            if len(games) >= 25:
                team[a["displayName"]] = games
        out[ab] = team
        print(ab, len(team), "players", flush=True)
    (BASE / "data").mkdir(exist_ok=True)
    (BASE / "data" / "logs_2026.json").write_text(json.dumps(out), encoding="utf-8")
    med = {norm(p): st.median(x["min"] for x in g.values()) for team in out.values() for p, g in team.items()}
    (BASE / "data" / "minutes_median.json").write_text(json.dumps(med), encoding="utf-8")
    print(len(med), "players with a median")


if __name__ == "__main__":
    main()
