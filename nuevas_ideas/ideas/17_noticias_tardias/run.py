"""Idea 17 - late news: ESPN injury report at every batch, and what happened to the flagged players.

Each run saves the league injury report (player -> status: Out / Doubtful / Questionable / Day-To-Day) and which of the current production picks involve a flagged
player. Later the report joins the snapshots with the settled legs (data/nba_analysis.json): void / low-minute / hit rate for legs on flagged players vs the rest.
If flagged players are void or play few minutes far more often, the production picks should skip them (and a late batch would catch Out/Doubtful news).
Paper only: nothing in production changes. Output: history/<day>.json and RESULTADO.md in this folder.
"""

import json
import os
import sys
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
HIST = HERE / "snapshots"
URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return "".join(c for c in s if c.isalnum() or c == " ").replace(" jr", "").replace(" sr", "").replace(" ii", "").strip()


def fetch() -> tuple[dict[str, str], dict[str, list]]:
    """(player -> status for everyone on the report, team -> [(player, status)] for Out/Doubtful only: the 'role shift' trigger)."""
    d = requests.get(URL, timeout=30).json()
    out, absent = {}, {}
    for team in d.get("injuries", []):
        for it in team.get("injuries", []):
            name = it.get("athlete", {}).get("displayName")
            status = it.get("status") or (it.get("type") or {}).get("description")
            if name and status:
                out[norm(name)] = status
                if status.lower() in ("out", "doubtful"):
                    absent.setdefault(team.get("displayName", ""), []).append((name, status))
    return out, absent


def day_key() -> str:
    return (datetime.now() - timedelta(hours=6)).strftime("%Y-%m-%d")


def snapshot() -> None:
    HIST.mkdir(exist_ok=True)
    inj, absent = fetch()
    picks_path = ROOT / "data" / "nba_picks.json"
    legs = []
    if picks_path.exists():
        doc = json.loads(picks_path.read_text(encoding="utf-8"))
        for p in doc.get("picks", []) + doc.get("high_prob", []):
            legs.append({"player": p["player"], "stat": p["stat"], "side": p["side"], "line": p["line"], "fair_prob": p["fair_prob"], "team": p.get("team"), "status": inj.get(norm(p["player"]))})
    path = HIST / f"{day_key()}.json"
    snap = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"date": day_key(), "runs": []}
    snap["runs"].append({"at": datetime.now().isoformat(timespec="seconds"), "injuries": inj, "absent_by_team": absent, "legs": legs, "legs_flagged": [l for l in legs if l["status"]]})
    path.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
    flagged = [l for l in legs if l["status"]]
    print(f"[17_noticias_tardias] {len(inj)} injury-report entries, {len(flagged)} of {len(legs)} current pick/high-prob legs flagged: " +
          ", ".join(sorted({f'{l["player"]} ({l["status"]})' for l in flagged}))[:300])


def report() -> None:
    a = json.loads((ROOT / "data" / "nba_analysis.json").read_text(encoding="utf-8"))
    lines = ["# Idea 17 - noticias tardías (parte de lesiones de ESPN)", "", f"Generado {datetime.now():%Y-%m-%d %H:%M}.", ""]
    flagged_by_day: dict[str, dict[str, str]] = {}
    for f in sorted(HIST.glob("*.json")):
        snap = json.loads(f.read_text(encoding="utf-8"))
        d = flagged_by_day.setdefault(snap["date"], {})
        for run in snap["runs"]:                       # a player flagged in ANY run of the day counts (worst status kept)
            for l in run["legs_flagged"]:
                d[norm(l["player"])] = l["status"]
    legs = [l for l in a["legs"] if l["date"] in flagged_by_day]
    if not legs:
        lines.append("Aún sin piernas liquidadas con parte de lesiones guardado (el registro empieza el 27/10).")
    else:
        def row(name, rs):
            played = [r for r in rs if r.get("ok") is not None]
            if not rs:
                return ""
            low = sum(1 for r in played if (r.get("min") or 0) < 20)
            hit = sum(r["ok"] for r in played)
            return f"| {name} | {len(rs)} | {len(rs) - len(played)} | {low} | {hit / len(played):.0%} |" if played else f"| {name} | {len(rs)} | {len(rs)} | 0 | – |"
        flag = [l for l in legs if norm(l["player"]) in flagged_by_day[l["date"]]]
        rest = [l for l in legs if norm(l["player"]) not in flagged_by_day[l["date"]]]
        lines += ["| Grupo | Piernas | Anuladas (no jugó) | Jugó < 20 min | Acierto |", "|---|---|---|---|---|", row("jugador con estado en el parte", flag), row("resto", rest)]
    (HERE / "RESULTADO.md").write_text("\n".join(l for l in lines) + "\n", encoding="utf-8")


def main() -> None:
    if os.environ.get("IDEAS_SPORT", "nba") != "nba":
        return
    try:
        snapshot()
    except Exception as exc:  # noqa: BLE001
        print("[17_noticias_tardias] injury fetch failed:", str(exc)[:120])
    report()


if __name__ == "__main__":
    main()
