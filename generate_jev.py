"""Build the private 'Jev' tab: combos chosen by TypeSafe's Jev (NBA, NFL, NBA+NFL) and the daily comparison against our own rules.

Data: data/jev_picks.json (jev/jev_combos.py) + data/jev_analysis.json (jev/jev_settle.py, merged into the picks file by jev/jev_publish.py).
The combo cards come from generate_combos (itself loaded from generate_nba.py), so they look like the other tabs; the leg 'Win%' is Jev's probability.
Usage: python generate_jev.py [output]
"""

import html
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import generate_combos

ROOT = Path(__file__).parent
PICKS = ROOT / "data" / "jev_picks.json"
LABEL = {"nba": "NBA", "nfl": "NFL", "total": "Total NBA + NFL"}


def pct(x: float | None) -> str:
    return "–" if x is None else f"{x * 100:.0f} %"


def unit(x: float) -> str:
    return f"{x:+.2f} u"


def verdict(j: dict, o: dict) -> str:
    if not j["n"] or not o["n"]:
        return "sin datos"
    if j["profit"] == o["profit"]:
        return "empate"
    return "Jev" if j["profit"] > o["profit"] else "Nosotros"


def comparison_html(analysis: dict | None) -> str:
    if not analysis or not analysis.get("comparison"):
        return ('<h2 class="sec">Jev contra nosotros</h2><p class="note">Todavía no hay combinadas de Jev liquidadas. En cuanto terminen los partidos de hoy '
                'aparecerá aquí la comparación, día a día.</p>')
    rows = []
    for scope, c in analysis["comparison"].items():
        j, o = c["jev"], c["ours"]
        rows.append(f'<tr><td>{LABEL[scope]}</td><td>{j["won"]}/{j["n"]}</td><td>{pct(j["won"] / j["n"] if j["n"] else None)}</td><td>{unit(j["profit"])}</td>'
                    f'<td>{o["won"]}/{o["n"]}</td><td>{pct(o["won"] / o["n"] if o["n"] else None)}</td><td>{unit(o["profit"])}</td><td><b>{verdict(j, o)}</b></td></tr>')
    total = ('<table class="cmp"><tr><th rowspan="2">Apartado</th><th colspan="3">Jev</th><th colspan="3">Nuestro método</th><th rowspan="2">Va ganando</th></tr>'
             '<tr><th>Acertadas</th><th>%</th><th>Beneficio</th><th>Acertadas</th><th>%</th><th>Beneficio</th></tr>' + "".join(rows) + "</table>")
    days = []
    for scope, c in analysis["comparison"].items():
        for d in reversed(c["days"]):
            j, o = d["jev"], d["ours"]
            days.append(f'<tr><td>{d["date"][5:]}</td><td>{LABEL[scope]}</td><td>{j["won"]}/{j["n"]}</td><td>{unit(j["profit"])}</td>'
                        f'<td>{o["won"]}/{o["n"]}</td><td>{unit(o["profit"])}</td><td>{verdict(j, o)}</td></tr>')
    daily = ('<table class="cmp"><tr><th>Día</th><th>Apartado</th><th>Jev</th><th>Beneficio</th><th>Nosotros</th><th>Beneficio</th><th>Mejor</th></tr>'
             + "".join(sorted(days, reverse=True)) + "</table>")
    b = analysis.get("brier")
    brier = ""
    if b:
        better = "Jev" if b["jev"] < b["ours"] else "Nuestro método"
        brier = (f'<p class="note">Calidad de la probabilidad en las mismas {b["n"]} piernas (error de Brier, menor es mejor): '
                 f'Jev {b["jev"]} · casas {b["ours"]} → mejor: <b>{better}</b>. Acierto real {pct(b["hit"])} · '
                 f'Jev decía de media {pct(b["jev_mean"])} · las casas {pct(b["ours_mean"])}.</p>')
    return ('<h2 class="sec">Jev contra nosotros</h2><p class="note" style="margin-top:0">Mismas reglas de combinada (3 piernas, partidos y jugadores distintos), '
            '1 unidad por combinada a la cuota guardada. Solo se comparan los días en que Jev ya tiene combinadas liquidadas.</p>'
            f'{total}{brier}<h2 class="sec">Día a día</h2>{daily}')


def priority_html(analysis: dict | None) -> str:
    pr = (analysis or {}).get("priority")
    if not pr:
        return ""
    def rows(res):
        return "".join(f'<tr><td>{r["rank"]}</td><td>{r["won"]}/{r["n"]}</td><td>{pct(r["hit"])}</td><td>{pct(r["avg_prob"])}</td>'
                       f'<td>{unit(r["profit"])}</td><td>{unit(r["weighted"])}</td></tr>' for r in res)
    head = '<tr><th>Prioridad</th><th>Acertadas</th><th>%</th><th>Prob. media</th><th>Beneficio (1 u)</th><th>Beneficio con el importe sugerido</th></tr>'
    return ('<h2 class="sec">¿Aciertan más las que llevan más importe?</h2><p class="note" style="margin-top:0">La extensión ordena las combinadas de cada día por '
            'probabilidad × cuota y sugiere 1,5× / 1,0× / 0,5× del importe base (1.ª, 2.ª, resto). Aquí se repite ese orden con todas las combinadas ya liquidadas.</p>'
            f'<h3 style="margin:10px 0 0;font-size:14px">Jev ({pr["jev_n"]} combinadas)</h3><table class="cmp">{head}{rows(pr["jev"])}</table>'
            f'<h3 style="margin:10px 0 0;font-size:14px">Nuestro método ({pr["ours_n"]} combinadas apostables)</h3><table class="cmp">{head}{rows(pr["ours"])}</table>')


def diffs_html(doc: dict) -> str:
    legs = {}
    for scope in ("nba", "nfl", "total"):
        for c in doc.get(scope, []):
            for l in c["legs"]:
                legs[l["key"]] = l
    rows = sorted(legs.values(), key=lambda l: -abs(l["fair_prob"] - l["our_prob"]))[:8]
    if not rows:
        return ""
    body = "".join(f'<tr><td>{html.escape(l["player"])}</td><td>{html.escape(str(l["stat"]))} {l["side"]} {l["line"]}</td>'
                   f'<td>{pct(l["our_prob"])}</td><td>{pct(l["fair_prob"])}</td></tr>' for l in rows)
    return ('<h2 class="sec">Dónde discrepa Jev</h2><p class="note" style="margin-top:0">Piernas de sus combinadas en las que más se aleja de la probabilidad de las casas.</p>'
            f'<table class="cmp"><tr><th>Jugador</th><th>Mercado</th><th>Casas</th><th>Jev</th></tr>{body}</table>')


def build(doc: dict) -> str:
    mod = generate_combos.load()
    dummy = {"picks": [], "combos": [], "combos_tracking": [], "timestamp": doc["timestamp"], "analysis": None}
    base = mod.build(dummy)
    css = re.search(r"<style>(.*?)</style>", base, re.S).group(1)
    js = "</script>\n<script>".join(re.findall(r"<script>(.*?)</script>", base, re.S)[-2:])
    bankroll = re.search(r'<div class="card bk">.*?</div>', base, re.S).group(0)
    track = base[base.index('<h2 class="sec">Mis apuestas'):base.index("</main>")]
    stamp = datetime.fromisoformat(doc["timestamp"]).astimezone()
    sections = "".join(generate_combos._section(mod, doc.get(scope, []), f"Jev · {LABEL[scope]}", sub) for scope, sub in (
        ("nba", "Combinadas de NBA: Jev elige las 3 piernas con todo el historial; no se aplican nuestras reglas de EV ni de probabilidad mínima."),
        ("nfl", "Combinadas de NFL: Jev elige las 3 piernas con todo el historial; no se aplican nuestras reglas."),
        ("total", "Combinadas que mezclan NBA y NFL: Jev elige las piernas; la probabilidad de la combinada es la que da Jev.")))
    extra_css = ".cmp{width:100%;border-collapse:collapse;margin:8px 0;font-size:13px}.cmp th,.cmp td{border-bottom:1px solid #2f4553;padding:5px 8px;text-align:left}.cmp th{color:#8aa0ad;font-weight:600}"
    return f"""<title>Jev</title>
<meta name="robots" content="noindex,nofollow">
<style>{css}{extra_css}</style>
<main>
<h1>Jev · combinadas de TypeSafe</h1>
<p class="sub">Jev (modelo de decisiones de TypeSafe) recibe todo el historial y elige él mismo las piernas de cada combinada (3 por apartado) · {doc.get("legs_evaluated", 0)} piernas valoradas · actualizado {stamp:%d/%m %H:%M}</p>
{comparison_html(doc.get("analysis"))}
{priority_html(doc.get("analysis"))}
{bankroll}
{sections}
{diffs_html(doc)}
{track}
</main>
<script>{js}</script>
"""


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "build" / "jev_src.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(json.loads(PICKS.read_text(encoding="utf-8"))), encoding="utf-8")
    print(f"Written {out}")


if __name__ == "__main__":
    main()
