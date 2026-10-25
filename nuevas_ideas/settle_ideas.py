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
    sys.path.insert(0, str(ROOT / "nfl"))
    import nfl_settle
    nfl_espn = nfl_settle.Espn()
    for path in sorted((BASE / "ideas").glob("*/history_nfl/*.json")):
        done += nfl_settle.settle_file(path, nfl_espn)
    return done


def collect() -> list[dict]:
    rows = []
    for path in sorted(list((BASE / "ideas").glob("*/history/*.json")) + list((BASE / "ideas").glob("*/history_nfl/*.json"))):
        idea = path.parent.parent.name + (" (NFL)" if path.parent.name == "history_nfl" else "")
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


def leg_calibration(a: dict, title: str = "producción NBA") -> list[str]:
    """Daily watch on the production legs (data/nba_analysis.json): are 'value' legs (EV > 1 %) as good as their
    probability says? Sliced by side and by fair-probability bucket. Added 25/10 after day 2: legs with win >= 54 %
    (the combo rule) were calibrated, while Under legs with EV > 1 % and win < 54 % hit ~32 % vs ~52 % expected."""
    import math
    legs = a.get("legs", [])

    def row(name: str, rs: list[dict]) -> str:
        if not rs:
            return ""
        n = len(rs)
        hit = sum(r["ok"] for r in rs) / n
        exp = sum(r["win"] for r in rs) / n
        se = math.sqrt(max(exp * (1 - exp), 0.01) / n)
        roi = sum((r["odds"] - 1) if r["ok"] else -1 for r in rs) / n
        return f"| {name} | {n} | {hit:.1%} | {exp:.1%} | {100 * (hit - exp):+.1f} ({(hit - exp) / se:+.1f} SE) | {roi:+.1%} |"

    out = ["", f"### Calibración de piernas de {title} (vigilancia diaria)", "",
           "| Grupo | Piernas | Acierto | Esperado | Dif. pts | ROI |", "|---|---|---|---|---|---|"]
    for side in ("Over", "Under"):
        for lo, hi, tag in ((0.0, 0.54, "prob < 54 %"), (0.54, 1.01, "prob >= 54 %")):
            for val, vt in ((True, "EV > 1 %"), (False, "EV <= 1 %")):
                rs = [r for r in legs if r["side"] == side and lo <= r["win"] < hi and (r["ev"] > 0.01) == val]
                if len(rs) >= 5:
                    out.append(row(f"{side}, {tag}, {vt}", rs))
    for day in sorted({r["date"] for r in legs}):
        rs = [r for r in legs if r["date"] == day]
        out.append(row(f"Día {day} (todas)", rs))
    return out


def objective_section(a: dict, universe_rows: list[dict]) -> list[str]:
    """Progress towards the user's goal (65-70 %) measured in the ways it can be read, plus days in profit."""
    legs = a.get("legs", [])
    out = ["", "### Objetivo 65-70 %: dónde estamos (se mide de tres formas)", "",
           "| Medida | Hoy | Para 65 % | Para 70 % |", "|---|---|---|---|"]

    def rate(rs: list[dict], key_ok: str = "ok") -> str:
        return f"{sum(r[key_ok] for r in rs) / len(rs):.1%} (n={len(rs)})" if rs else "sin datos"

    out.append(f"| Acierto por pierna, todas las recomendadas | {rate(legs)} | 65 % | 70 % |")
    out.append(f"| Acierto por pierna, prob. casas >= 54 % | {rate([r for r in legs if r['win'] >= 0.54])} | 65 % | 70 % |")
    out.append(f"| Acierto por pierna, prob. casas >= 62 % | {rate([r for r in legs if r['win'] >= 0.62])} | 65 % | 70 % |")
    combos = a.get("combos", [])
    prod = [c for c in combos if not c.get("tracking")]
    out.append(f"| Acierto de combinadas de 3 (producción) | {sum(c['hit'] for c in prod) / len(prod):.1%} (n={len(prod)}) | " if prod else "| Acierto de combinadas de 3 (producción) | sin datos | ")
    out[-1] += f"cada pierna al {0.65 ** (1 / 3):.1%} | cada pierna al {0.70 ** (1 / 3):.1%} |"
    days = a.get("days", [])
    if days:
        pos = sum(d["roi"] > 0 for d in days)
        out.append(f"| Días con beneficio (apuestas simples a 1 u) | {pos} de {len(days)} | todos | todos |")
    played = [r for r in universe_rows if r["status"] != "void"]
    hi = [r for r in played if r["p"] >= 0.62]
    if len(hi) >= 10:
        hit = sum(r["status"] == "won" for r in hi) / len(hi)
        roi = sum((r["stake_odds"] - 1) if r["status"] == "won" else -1 for r in hi) / len(hi)
        out.append(f"| Universo: líneas con prob. >= 62 % (acierto / ROI a cuota Stake) | {hit:.1%} / {roi:+.1%} (n={len(hi)}) | 65 % | 70 % |")
    out += ["", "Lectura: el acierto y el beneficio se mueven en sentido contrario al elegir piernas más probables (la cuota baja). "
                "Una combinada de 3 al 65 % exige piernas al 86,6 %, que no existen en este mercado; el objetivo realista es acierto alto "
                "por pierna con ROI positivo, y esta tabla enseña si algún grupo logra las dos cosas a la vez."]
    return out


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
        parts += leg_calibration(a)
        for label, path in (("NFL", ROOT / "nfl" / "data" / "nfl_analysis.json"), ("combinadas mezcladas NBA+NFL", ROOT / "data" / "mix_analysis.json")):
            if path.exists():
                other = json.loads(path.read_text(encoding="utf-8"))
                if other.get("legs"):
                    parts += leg_calibration(other, label)
                    fams = other.get("combo_families", [])
                    if fams:
                        parts += ["", f"Familias de combinadas ({label}):", "", "| Familia | Combinadas | Aciertos | ROI |", "|---|---|---|---|"]
                        parts += [f"| {f.get('name')} | {f.get('n')} | {f.get('hits')} | {f.get('roi', 0):+.1%} |" for f in fams]
        try:
            import nfl_universe
            nfl_universe.download_boxscores()
            parts += nfl_universe.report(nfl_universe.build())
        except Exception as exc:
            parts += ["", f"(universo NFL no disponible: {exc})"]
        try:
            import universe
            nb = universe.download_boxscores()
            urows = universe.build()
            parts += objective_section(a, urows)
            parts += universe.report(urows)
        except Exception as exc:  # the universe is an extra: never break the report
            parts += ["", f"(universo no disponible: {exc})"]
        parts += ["", "### Referencia: familias de producción (todos los días liquidados)", "",
                  "| Familia | Combinadas | Aciertos | ROI |", "|---|---|---|---|"]
        for f in a.get("combo_families", []):
            parts.append(f"| {f.get('name')} | {f.get('n')} | {f.get('hits')} | {f.get('roi', 0):+.1%} |")
    OUT_MD.write_text("\n".join(parts) + "\n", encoding="utf-8")
    OUT_JSON.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    print(f"settled {n} legs; {len(rows)} settled paper combos -> {OUT_MD.name}")


if __name__ == "__main__":
    main()
