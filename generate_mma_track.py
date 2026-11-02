"""Build the private 'MMA Jev' tab: our MMA model's picks against Jev's, fight by fight, with the running comparison.

Data: data/mma_picks.json (mma/mma_publish.py: {timestamp, analysis}).  The look is borrowed from generate_combos (same CSS as the other tabs).
Usage: python generate_mma_track.py [output]
"""

import html
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import generate_combos

ROOT = Path(__file__).parent
PICKS = ROOT / "data" / "mma_picks.json"


def pct(x: float | None) -> str:
    return "–" if x is None else f"{x * 100:.0f} %"


def unit(x: float) -> str:
    return f"{x:+.2f} u"


def stats_row(label: str, s: dict) -> str:
    rate = pct(s["won"] / s["n"]) if s["n"] else "–"
    return f'<tr><td>{label}</td><td>{s["won"]}/{s["n"]}</td><td>{rate}</td><td>{unit(s["profit"])}</td><td>{pct(s["roi"])}</td></tr>'


def comparison_html(a: dict) -> str:
    c, b = a["comparison"], a["brier"]
    if not c["jev"]["n"] and not c["ours_all"]["n"]:
        body = ('<p class="note">Todavía no hay peleas liquidadas. Las apuestas se guardan en cuanto aparecen (solo peleas de la próxima semana) '
                'y se liquidan solas con los resultados de ESPN cuando terminan.</p>')
    else:
        body = ('<table class="cmp"><tr><th>Quién</th><th>Acertadas</th><th>%</th><th>Beneficio (1 u)</th><th>ROI</th></tr>'
                + stats_row("Jev (todas sus apuestas)", c["jev"]) + stats_row("Nosotros · value bets (las apostables)", c["ours_value"])
                + stats_row("Nosotros · value + marginales", c["ours_all"]) + "</table>")
    days = "".join(f'<tr><td>{d["date"][5:]}</td><td>{d["jev"]["won"]}/{d["jev"]["n"]}</td><td>{unit(d["jev"]["profit"])}</td>'
                   f'<td>{d["ours"]["won"]}/{d["ours"]["n"]}</td><td>{unit(d["ours"]["profit"])}</td></tr>' for d in reversed(c["days"]))
    days = (f'<h2 class="sec">Día a día</h2><table class="cmp"><tr><th>Día</th><th>Jev</th><th>Beneficio</th><th>Nosotros</th><th>Beneficio</th></tr>{days}</table>'
            if days else "")
    brier = ""
    if b["n"]:
        brier = (f'<p class="note">Calidad de la probabilidad de quién gana (error de Brier, menor es mejor) en {b["n"]} peleas: '
                 f'nuestro modelo {b["ours"] if b["ours"] is not None else "–"} · Jev {b["jev"] if b["jev"] is not None else "–"} · mercado sin margen {b["market"]}.</p>')
    return f'<h2 class="sec">Jev contra nosotros</h2>{body}{brier}{days}'


def pick_cell(side: dict, is_ours: bool) -> str:
    p = side.get("pick")
    if not p:
        return '<span style="color:#8aa0ad">no apuesta</span>'
    tag = ""
    if is_ours:
        tag = " · value" if p.get("kind") == "value" else " · marginal"
    return f'<b>{html.escape(p["fighter"])}</b> @{p["odds"]:.2f}<br><small>prob {pct(p["prob"])} · ventaja {p["edge"] * 100:+.0f} pts{tag}</small>'


def fights_html(a: dict) -> str:
    now = datetime.now().astimezone()
    up, done = [], []
    for f in a["fights"]:
        (done if f["winner"] else up).append(f)
    rows = []
    for f in sorted(up, key=lambda f: f["commence_time"]):
        if datetime.fromisoformat(f["commence_time"].replace("Z", "+00:00")) <= now:
            continue
        rows.append(f'<tr><td>{f["date"][5:]}</td><td>{html.escape(f["fighter1"])} ({f["odds1"]:.2f}) vs {html.escape(f["fighter2"])} ({f["odds2"]:.2f})'
                    f'<br><small>{html.escape(f["event"])}</small></td><td>{pick_cell(f["ours"], True)}</td><td>{pick_cell(f["jev"], False)}</td></tr>')
    upcoming = ('<h2 class="sec">Próximas peleas</h2><table class="cmp"><tr><th>Día</th><th>Pelea</th><th>Nuestro modelo</th><th>Jev</th></tr>'
                + "".join(rows) + "</table>") if rows else '<h2 class="sec">Próximas peleas</h2><p class="note">No hay peleas en la próxima semana.</p>'
    res = []
    for f in sorted(done, key=lambda f: f["commence_time"], reverse=True)[:40]:
        def mark(side):
            p = side.get("pick")
            if not p:
                return "–"
            won = f["winner"] != "void" and p["fighter"].split()[-1].lower() in f["winner"].lower()
            return ("✓ " if won else "✗ ") + html.escape(p["fighter"])
        res.append(f'<tr><td>{f["date"][5:]}</td><td>{html.escape(f["fighter1"])} vs {html.escape(f["fighter2"])}</td><td>{html.escape(f["winner"])}</td>'
                   f'<td>{mark(f["ours"])}</td><td>{mark(f["jev"])}</td></tr>')
    settled = ('<h2 class="sec">Liquidadas</h2><table class="cmp"><tr><th>Día</th><th>Pelea</th><th>Ganó</th><th>Nosotros</th><th>Jev</th></tr>'
               + "".join(res) + "</table>") if res else ""
    return upcoming + settled


def build(doc: dict) -> str:
    mod = generate_combos.load()
    base = mod.build({"picks": [], "combos": [], "combos_tracking": [], "timestamp": doc["timestamp"], "analysis": None})
    css = re.search(r"<style>(.*?)</style>", base, re.S).group(1)
    stamp = datetime.fromisoformat(doc["timestamp"]).astimezone()
    extra_css = ".cmp{width:100%;border-collapse:collapse;margin:8px 0;font-size:13px}.cmp th,.cmp td{border-bottom:1px solid #2f4553;padding:5px 8px;text-align:left;vertical-align:top}.cmp th{color:#8aa0ad;font-weight:600}small{color:#8aa0ad}"
    a = doc["analysis"]
    return f"""<title>MMA Jev</title>
<meta name="robots" content="noindex,nofollow">
<style>{css}{extra_css}</style>
<main>
<h1>MMA · nuestro modelo contra Jev</h1>
<p class="sub">Cada pelea de la próxima semana: el modelo propio y Jev deciden por separado a quién apostar (o no apostar). 1 unidad por apuesta a la cuota guardada · actualizado {stamp:%d/%m %H:%M}</p>
{comparison_html(a)}
{fights_html(a)}
</main>
"""


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "build" / "mma_track_src.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(json.loads(PICKS.read_text(encoding="utf-8"))), encoding="utf-8")
    print(f"Written {out}")


if __name__ == "__main__":
    main()
