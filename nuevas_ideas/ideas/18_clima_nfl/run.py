"""Idea 18 - NFL weather (National Weather Service, free API, no key) for open-air stadiums.

Each NFL run saves, for every game in the next 4 days (ESPN scoreboard: home team and kickoff), the hourly forecast at kickoff: wind, precipitation chance, temperature
(domes are marked and skipped). The report joins the snapshots with the settled NFL legs (nfl/data/nfl_analysis.json): hit rate of the Over legs on passing/receiving
markets in windy games (>= 15 mph) vs calm ones. The market already prices most of this, so the test is whether OUR legs miss more in the wind.
Paper only; writes history/<day>.json and RESULTADO.md here.
"""

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
HIST = HERE / "snapshots_nfl"
HEAD = {"User-Agent": "the-model-research (elouelyt@gmail.com)"}
ESPN = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
WIND_MPH = 15
# team abbreviation -> (lat, lon, dome)  - dome/closed roof games are skipped
STADIUMS = {
    "ARI": (33.53, -112.26, True), "ATL": (33.76, -84.40, True), "BAL": (39.28, -76.62, False), "BUF": (42.77, -78.79, False), "CAR": (35.23, -80.85, False),
    "CHI": (41.86, -87.62, False), "CIN": (39.10, -84.52, False), "CLE": (41.51, -81.70, False), "DAL": (32.75, -97.09, True), "DEN": (39.74, -105.02, False),
    "DET": (42.34, -83.05, True), "GB": (44.50, -88.06, False), "HOU": (29.68, -95.41, True), "IND": (39.76, -86.16, True), "JAX": (30.32, -81.64, False),
    "KC": (39.05, -94.48, False), "LV": (36.09, -115.18, True), "LAC": (33.95, -118.34, True), "LAR": (33.95, -118.34, True), "MIA": (25.96, -80.24, False),
    "MIN": (44.97, -93.26, True), "NE": (42.09, -71.26, False), "NO": (29.95, -90.08, True), "NYG": (40.81, -74.07, False), "NYJ": (40.81, -74.07, False),
    "PHI": (39.90, -75.17, False), "PIT": (40.45, -80.02, False), "SF": (37.40, -121.97, False), "SEA": (47.60, -122.33, False), "TB": (27.98, -82.50, False),
    "TEN": (36.17, -86.77, False), "WSH": (38.91, -76.86, False), "WAS": (38.91, -76.86, False),
}


def day_key() -> str:
    return (datetime.now() - timedelta(hours=6)).strftime("%Y-%m-%d")


def forecast(lat: float, lon: float, when: datetime) -> dict | None:
    p = requests.get(f"https://api.weather.gov/points/{lat},{lon}", headers=HEAD, timeout=30).json()
    hourly = requests.get(p["properties"]["forecastHourly"], headers=HEAD, timeout=30).json()["properties"]["periods"]
    best = min(hourly, key=lambda h: abs(datetime.fromisoformat(h["startTime"]) - when))
    if abs(datetime.fromisoformat(best["startTime"]) - when) > timedelta(hours=3):
        return None
    wind = [int(x) for x in re.findall(r"\d+", best.get("windSpeed", ""))]
    return {"wind_mph": max(wind) if wind else None, "precip_pct": (best.get("probabilityOfPrecipitation") or {}).get("value"), "temp_f": best.get("temperature")}


def snapshot() -> None:
    HIST.mkdir(exist_ok=True)
    now = datetime.now(timezone.utc)
    games = []
    for off in range(0, 5):
        d = (now + timedelta(days=off)).strftime("%Y%m%d")
        for ev in requests.get(ESPN, params={"dates": d}, timeout=30).json().get("events", []):
            comp = ev["competitions"][0]
            home = next(c for c in comp["competitors"] if c["homeAway"] == "home")["team"]
            away = next(c for c in comp["competitors"] if c["homeAway"] == "away")["team"]
            games.append({"id": ev["id"], "home": home["abbreviation"], "home_name": home["displayName"], "away_name": away["displayName"], "kickoff": ev["date"]})
    seen = {g["id"]: g for g in games}.values()
    out = []
    for g in seen:
        lat, lon, dome = STADIUMS.get(g["home"], (None, None, None))
        row = {**g, "dome": dome}
        if lat is not None and not dome:
            try:
                row["forecast"] = forecast(lat, lon, datetime.fromisoformat(g["kickoff"].replace("Z", "+00:00")))
            except Exception as exc:  # noqa: BLE001
                row["forecast_error"] = str(exc)[:80]
        out.append(row)
    path = HIST / f"{day_key()}.json"
    snap = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"date": day_key(), "runs": []}
    snap["runs"].append({"at": datetime.now().isoformat(timespec="seconds"), "games": out})
    path.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
    for g in out:
        f = g.get("forecast")
        print(f'[18_clima_nfl] {g["away_name"]} @ {g["home_name"]}: ' + ("dome" if g["dome"] else (f'wind {f["wind_mph"]} mph, rain {f["precip_pct"]} %, {f["temp_f"]} F' if f else "no forecast")))


def report() -> None:
    lines = ["# Idea 18 - clima NFL", "", f"Generado {datetime.now():%Y-%m-%d %H:%M}.", ""]
    weather: dict[str, dict] = {}
    for f in sorted(HIST.glob("*.json")):
        for run in json.loads(f.read_text(encoding="utf-8"))["runs"]:
            for g in run["games"]:
                if g.get("forecast"):
                    weather[(g["home_name"].split()[-1].lower(), g["kickoff"][:10])] = g["forecast"]      # last forecast before kickoff wins
    path = ROOT / "nfl" / "data" / "nfl_analysis.json"
    if not weather or not path.exists():
        lines.append("Aún sin partidos con previsión guardada y liquidados (el registro empieza el 27/10; el próximo partido con datos es el jueves).")
    else:
        a = json.loads(path.read_text(encoding="utf-8"))
        legs = [l for l in a["legs"] if l.get("ok") is not None and any(k in l["stat"] for k in ("passing", "receiving", "receptions")) and l["side"] == "Over"]
        rows = {"ventoso": [], "tranquilo": []}
        for l in legs:
            for (team, kick), w in weather.items():
                gap = abs((datetime.fromisoformat(kick) - datetime.fromisoformat(l["date"])).days)
                if team in l["game"].lower() and gap <= 1:
                    rows["ventoso" if (w.get("wind_mph") or 0) >= WIND_MPH else "tranquilo"].append(l)
                    break
        lines += ["| Partido | Piernas Over pase/recepción | Acierto | Esperado |", "|---|---|---|---|"]
        for k, rs in rows.items():
            if rs:
                lines.append(f"| {k} (viento {'>=' if k == 'ventoso' else '<'} {WIND_MPH} mph) | {len(rs)} | {sum(r['ok'] for r in rs) / len(rs):.0%} | {sum(r['win'] for r in rs) / len(rs):.0%} |")
    (HERE / "RESULTADO.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    if os.environ.get("IDEAS_SPORT", "nba") != "nfl":
        return
    try:
        snapshot()
    except Exception as exc:  # noqa: BLE001
        print("[18_clima_nfl] weather fetch failed:", str(exc)[:120])
    report()


if __name__ == "__main__":
    main()
