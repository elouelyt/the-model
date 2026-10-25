"""Build the 'universe' dataset: EVERY Stake line of every archived batch, with the reference-book fair probability at that
moment and the real result from the ESPN box score (all players, not only the ones we recommended).

Why: production only keeps recommended legs (a few hundred), so every calibration question (unders, rebounds, devig method,
number of books, probability buckets...) takes weeks. With this file the same question is answered with thousands of lines.

    python nuevas_ideas/universe.py            # download missing box scores, rebuild archive/universe.jsonl.gz, print report
Reads only nuevas_ideas/archive/ (batches written by archive.py) and ESPN; never touches production files.
"""

import gzip
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import BASE  # noqa: E402
import nba_ev  # noqa: E402
import nba_settle  # noqa: E402

ARCH = BASE / "archive"
BOX = ARCH / "boxscores"
UNIVERSE = ARCH / "universe.jsonl.gz"
MAX_AGE_H = 6.0  # a reference quote older than this (relative to its batch) is not used, same as production


def _load(path: Path):
    return json.loads(gzip.open(path, "rt", encoding="utf-8").read()) if path.exists() else None


def batch_books(batch: Path, batch_time: datetime) -> dict:
    """(fixture, norm player, stat, line) -> {book: (over, under)} from the archived reference-book caches."""
    index: dict[tuple, dict] = {}
    for book, fname in nba_ev.BOOK_FILES.items():
        doc = _load(batch / (fname + ".gz"))
        if not doc:
            continue
        if (batch_time - datetime.fromisoformat(doc["timestamp"])).total_seconds() > MAX_AGE_H * 3600:
            continue
        for r in doc["rows"]:
            if abs(r["over_american"]) > 400 or abs(r["under_american"]) > 400:
                continue
            name = r.get("book", book)
            if name == "Consensus":
                continue
            index.setdefault((r["fixture"], nba_ev.norm_name(r["player"]), r["stat"], r["line"]), {})[name] = (r["over_american"], r["under_american"])
    return index


def download_boxscores() -> int:
    """Final box score (every player) of each archived game, once the game is over."""
    BOX.mkdir(parents=True, exist_ok=True)
    espn = nba_settle.Espn()
    new = 0
    seen = set()
    for batch in sorted((ARCH / "batches").glob("*")):
        stake = _load(batch / "nba_stake_cache.json.gz")
        for g in (stake or {}).get("games", []):
            fx = g["fixture"]
            if fx in seen or (BOX / f"{fx}.json").exists():
                continue
            seen.add(fx)
            start = parsedate_to_datetime(g["start"])
            if start > datetime.now(timezone.utc) - timedelta(hours=3):
                continue
            ev = espn.find(g["teams"], start)
            box = espn.box(ev["id"]) if ev else None
            if box:
                (BOX / f"{fx}.json").write_text(json.dumps(box), encoding="utf-8")
                new += 1
    return new


def build() -> list[dict]:
    rows: dict[tuple, dict] = {}
    for batch in sorted((ARCH / "batches").glob("*")):
        stake = _load(batch / "nba_stake_cache.json.gz")
        if not stake:
            continue
        bt = datetime.fromisoformat(stake["timestamp"])
        starts = {g["fixture"]: (g["start"], g["teams"]) for g in stake["games"]}
        index = batch_books(batch, bt)
        for r in stake["rows"]:
            if r["stat"] not in nba_ev.ALLOWED_STATS or r["fixture"] not in starts:
                continue
            start_s, teams = starts[r["fixture"]]
            if parsedate_to_datetime(start_s) < bt + timedelta(minutes=10):
                continue  # only lines that were still open when the batch ran
            books = index.get((r["fixture"], nba_ev.norm_name(r["player"]), r["stat"], r["line"]))
            if not books:
                continue
            p_over = sum(nba_ev.fair_probs(o, u)[0] for o, u in books.values()) / len(books)
            for side, p, odds, opp in (("Over", p_over, r["over"], r["under"]), ("Under", 1 - p_over, r["under"], r["over"])):
                key = (r["fixture"], r["player"], r["stat"], r["line"], side)
                rows[key] = {  # the LAST batch before the game wins (closest to what the market believed)
                    "batch": batch.name, "fixture": r["fixture"], "game": " vs ".join(teams), "start": start_s, "player": r["player"],
                    "stat": r["stat"], "line": r["line"], "side": side, "stake_odds": round(odds, 3), "opp_odds": round(opp, 3),
                    "p": round(p, 4), "books": len(books), "ev": round(p * odds - 1, 4)}
    out = []
    for row in rows.values():
        f = BOX / f'{row["fixture"]}.json'
        if not f.exists():
            continue
        box = json.loads(f.read_text(encoding="utf-8"))
        pl = box["players"].get(nba_ev.norm_name(row["player"]))
        if not pl or pl["dnp"]:
            row["status"] = "void"
        else:
            actual = sum(pl.get(c, 0) for c in nba_settle.STAT_COLS[row["stat"]])
            row["actual"] = actual
            row["status"] = "won" if (actual > row["line"]) == (row["side"] == "Over") else "lost"
        out.append(row)
    with gzip.open(UNIVERSE, "wt", encoding="utf-8") as f:
        for r in out:
            f.write(json.dumps(r) + "\n")
    return out


def load_universe() -> list[dict]:
    if not UNIVERSE.exists():
        return []
    return [json.loads(l) for l in gzip.open(UNIVERSE, "rt", encoding="utf-8")]


def _row(name: str, rs: list[dict]) -> str:
    rs = [r for r in rs if r["status"] != "void"]
    if len(rs) < 10:
        return ""
    n = len(rs)
    hit = sum(r["status"] == "won" for r in rs) / n
    exp = sum(r["p"] for r in rs) / n
    se = math.sqrt(max(exp * (1 - exp), 0.01) / n)
    roi = sum((r["stake_odds"] - 1) if r["status"] == "won" else -1 for r in rs) / n
    return f"| {name} | {n} | {hit:.1%} | {exp:.1%} | {100 * (hit - exp):+.1f} ({(hit - exp) / se:+.1f} SE) | {roi:+.1%} |"


def report(rows: list[dict] | None = None) -> list[str]:
    rows = load_universe() if rows is None else rows
    played = [r for r in rows if r["status"] != "void"]
    out = ["", "### Universo completo: TODAS las líneas de Stake con casas de referencia (archivo por tanda + box scores)", ""]
    if not played:
        return out + ["Aún sin datos (el archivo empieza el 25/10; se llena con cada tanda y se liquida al terminar los partidos)."]
    days = sorted({r["start"][:16] for r in rows})
    out += [f"{len(played)} líneas liquidadas de {len(days)} horarios de partido. Se usa la última tanda antes del partido de cada línea.", "",
            "| Grupo | Líneas | Acierto | Esperado (casas) | Dif. pts | ROI a cuota Stake |", "|---|---|---|---|---|---|"]
    out.append(_row("TODAS las líneas, ambos lados", played))
    for side in ("Over", "Under"):
        out.append(_row(f"{side} (todas)", [r for r in played if r["side"] == side]))
    for lo, hi in ((0.0, 0.46), (0.46, 0.50), (0.50, 0.54), (0.54, 0.58), (0.58, 0.62), (0.62, 0.70), (0.70, 1.01)):
        for side in ("Over", "Under"):
            out.append(_row(f"{side}, prob casas {lo:.2f}-{hi:.2f}", [r for r in played if r["side"] == side and lo <= r["p"] < hi]))
    out += ["", "| Regla | Líneas | Acierto | Esperado | Dif. pts | ROI |", "|---|---|---|---|---|---|"]
    out.append(_row("producción: prob >= 54 %, EV > 0,5 %, >= 2 casas", [r for r in played if r["p"] >= 0.54 and r["ev"] > 0.005 and r["books"] >= 2]))
    out.append(_row("EV > 0,5 % (sin filtro de probabilidad)", [r for r in played if r["ev"] > 0.005]))
    out.append(_row("EV > 3 %", [r for r in played if r["ev"] > 0.03]))
    out.append(_row("alta probabilidad >= 62 %", [r for r in played if r["p"] >= 0.62]))
    out.append(_row("alta probabilidad >= 62 % y >= 2 casas", [r for r in played if r["p"] >= 0.62 and r["books"] >= 2]))
    for b in (1, 2, 3, 4):
        out.append(_row(f"{b} casa(s) de referencia", [r for r in played if r["books"] == b]))
    for stat in sorted({r["stat"] for r in played}):
        out.append(_row(f"mercado {stat}", [r for r in played if r["stat"] == stat]))
    return [l for l in out if l != ""] if False else out


if __name__ == "__main__":
    n = download_boxscores()
    rows = build()
    print(f"box scores new: {n}; universe rows: {len(rows)} ({sum(r['status'] != 'void' for r in rows)} settled)")
    print("\n".join(report(rows)))
