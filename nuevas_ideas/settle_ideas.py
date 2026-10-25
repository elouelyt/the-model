"""Settle every idea's paper combos with ESPN box scores and rewrite nuevas_ideas/RESULTADOS.md.

It reuses the production ESPN code (scripts/nba_settle.py: Espn, settle_file) on the idea snapshots under
nuevas_ideas/ideas/*/history/. Nothing in data/ is modified. Idea 01 ('prudente') lives inside the production
snapshot as a paper family, so its numbers are read from data/nba_analysis.json (written by nba_settle.py).

Flat 1 unit per combo. Plain multis: a voided leg is dropped from the odds. SGMs (same-game builder): one voided
leg voids the whole bet (Stake rule), the stake is returned.
"""

import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import BASE, ROOT  # noqa: E402
import nba_settle  # noqa: E402

OUT_MD = BASE / "RESULTADOS.md"
OUT_JSON = BASE / "resultados.json"


def settle_all() -> int:
    espn = nba_settle.Espn()
    done = 0
    for path in sorted((BASE / "ideas").glob("*/history/*.json")):
        done += nba_settle.settle_file(path, espn)
    return done


def collect() -> list[dict]:
    rows = []
    for path in sorted((BASE / "ideas").glob("*/history/*.json")):
        idea = path.parent.parent.name
        snap = json.loads(path.read_text(encoding="utf-8"))
        res = snap.get("results", {})
        for run in snap["runs"]:
            for c in run["combos"]:
                outs = [res.get(l["key"]) for l in c["legs"]]
                if not all(outs):
                    continue
                live = [(l, o) for l, o in zip(c["legs"], outs) if o["status"] != "void"]
                void = len(live) < len(c["legs"])
                if c.get("sgm"):
                    if void:
                        rows.append({"idea": idea, "date": snap["date"], "fam": c["families"][0], "prob": c["prob"], "odds": 1.0,
                                     "hit": False, "void": True, "ev": c.get("ev"), "profit": 0.0})
                        continue
                    odds = c["odds"]
                else:
                    odds = 1.0
                    for l, _ in live:
                        odds *= l["stake_odds"]
                    if not live:
                        continue
                hit = all(o["status"] == "won" for _, o in live)
                rows.append({"idea": idea, "date": snap["date"], "fam": c["families"][0], "prob": c["prob"], "odds": round(odds, 3),
                             "hit": hit, "void": False, "ev": c.get("ev"), "profit": (odds - 1) if hit else -1.0})
    return rows


def table(rows: list[dict], title: str) -> str:
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        groups[(r["idea"], r["fam"])].append(r)
    out = [f"### {title}", "", "| Idea | Familia | Combinadas | Aciertos | Acierto | Esperado | ROI |", "|---|---|---|---|---|---|---|"]
    for (idea, fam), rs in sorted(groups.items()):
        played = [r for r in rs if not r["void"]]
        if not played:
            continue
        hits = sum(r["hit"] for r in played)
        out.append(f"| {idea} | {fam} | {len(played)} | {hits} | {hits / len(played):.1%} | "
                   f"{sum(r['prob'] for r in played) / len(played):.1%} | {sum(r['profit'] for r in played) / len(played):+.1%} |")
    return "\n".join(out)


def main() -> None:
    n = settle_all()
    rows = collect()
    parts = [f"# Resultados de las nuevas ideas (generado {datetime.now():%Y-%m-%d %H:%M})", "",
             f"Liquidadas ahora: {n} piernas nuevas. Cada combinada vale 1 unidad plana; ROI = beneficio por combinada.", ""]
    if rows:
        parts.append(table(rows, "Todas las ideas en papel (carpeta nuevas_ideas)"))
        sgm = [r for r in rows if r["idea"].startswith("02") and not r["void"]]
        if sgm:
            pos = [r for r in sgm if (r["ev"] or 0) > 0]
            neg = [r for r in sgm if (r["ev"] or 0) <= 0]
            parts += ["", "### SGM del mismo partido: según el EV que calculamos antes del partido", "",
                      "| Grupo | Combinadas | Acierto | Esperado (indep.) | ROI |", "|---|---|---|---|---|"]
            for name, g in (("EV > 0", pos), ("EV <= 0", neg)):
                if g:
                    parts.append(f"| {name} | {len(g)} | {sum(r['hit'] for r in g) / len(g):.1%} | "
                                 f"{sum(r['prob'] for r in g) / len(g):.1%} | {sum(r['profit'] for r in g) / len(g):+.1%} |")
    else:
        parts.append("Aún no hay combinadas liquidadas (las pruebas empiezan con la tanda de la tarde del 25/10).")
    ana = ROOT / "data" / "nba_analysis.json"
    if ana.exists():
        a = json.loads(ana.read_text(encoding="utf-8"))
        prud = [c for c in a.get("combos", []) if "prudente" in c.get("families", [])]
        parts += ["", "### Idea 01 `prudente` (probabilidad justa - 1,5 puntos, dentro del seguimiento de producción)", ""]
        if prud:
            hits = sum(c["hit"] for c in prud)
            profit = sum((c["odds"] - 1) if c["hit"] else -1 for c in prud)
            parts.append(f"{len(prud)} combinadas, {hits} aciertos ({hits / len(prud):.1%}), esperado "
                         f"{sum(c['prob'] for c in prud) / len(prud):.1%}, ROI {profit / len(prud):+.1%}.")
        else:
            parts.append("Sin combinadas `prudente` liquidadas todavía.")
        parts += ["", "### Referencia: familias de producción (todos los días liquidados)", "",
                  "| Familia | Combinadas | Aciertos | ROI |", "|---|---|---|---|"]
        for f in a.get("combo_families", []):
            parts.append(f"| {f.get('name')} | {f.get('n')} | {f.get('hits')} | {f.get('roi', 0):+.1%} |")
    OUT_MD.write_text("\n".join(parts) + "\n", encoding="utf-8")
    OUT_JSON.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    print(f"settled {n} legs; {len(rows)} settled paper combos -> {OUT_MD.name}")


if __name__ == "__main__":
    main()
