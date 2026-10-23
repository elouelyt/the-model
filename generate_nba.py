"""Build the private NBA value-bets page (plain HTML, encrypted afterwards with staticrypt).

Usage: python generate_nba.py [output_path]
Reads data/nba_picks.json written by scripts/nba_ev.py.
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import escape
from pathlib import Path

ROOT = Path(__file__).parent
PICKS = ROOT / "data" / "nba_picks.json"
DEFAULT_OUT = ROOT / "build" / "nba_src.html"

STAT_ES = {
    "points": "Puntos", "rebounds": "Rebotes", "assists": "Asistencias", "threesmade": "Triples",
    "points+rebounds": "Pts + Reb", "points+assists": "Pts + Ast",
    "assists+rebounds": "Ast + Reb", "points+assists+rebounds": "Pts + Ast + Reb",
}
STALE_AFTER = timedelta(hours=4)


def local_time(raw: str) -> str:
    try:
        return parsedate_to_datetime(raw).astimezone().strftime("%d/%m %H:%M")
    except (TypeError, ValueError):
        return raw


def build(doc: dict) -> str:
    picks = doc["picks"]
    stamp = datetime.fromisoformat(doc["timestamp"])
    stale = datetime.now(timezone.utc) - stamp > STALE_AFTER
    stats_present = sorted({p["stat"] for p in picks}, key=lambda s: list(STAT_ES).index(s) if s in STAT_ES else 99)
    chips = '<button class="chip on" data-s="all">Todos</button>' + "".join(
        f'<button class="chip" data-s="{escape(s)}">{escape(STAT_ES.get(s, s))}</button>' for s in stats_present
    )
    rows = "".join(
        f'<tr data-s="{escape(p["stat"])}">'
        f'<td class="num ev">{p["fair_prob"]:.1%}</td>'
        f'<td><b>{escape(p["player"])}</b><small>{escape(p["team"])}</small></td>'
        f'<td>{"Más de" if p["side"] == "Over" else "Menos de"} {p["line"]:g} <small>{escape(STAT_ES.get(p["stat"], p["stat"]))}</small></td>'
        f'<td class="num"><b>{p["stake_odds"]:.2f}</b><small>equilibrio {1 / p["stake_odds"]:.0%}</small></td>'
        f'<td class="num muted">{p["ev"]:+.1%}</td>'
        f'<td class="num muted">{p["fair_odds"]:.2f}</td>'
        f'<td class="num muted">{escape(p["fanduel"])}</td>'
        f'<td class="muted">{escape(p["game"])}<small>{local_time(p["start"])}</small></td></tr>'
        for p in picks
    ) or '<tr><td colspan="8" class="empty">Ninguna apuesta supera el mínimo ahora mismo.</td></tr>'
    best = picks[0] if picks else None
    best_html = (f'<b class="ev">{best["fair_prob"]:.1%}</b><small>{escape(best["player"])} · '
                 f'{escape(STAT_ES.get(best["stat"], best["stat"]))}</small>') if best else '<b>—</b>'
    warn = ('<p class="warn">Datos de hace más de 4 horas: vuelve a lanzar la actualización antes de apostar.</p>'
            if stale else "")
    return f"""<title>NBA</title>
<meta name="robots" content="noindex,nofollow">
<style>
:root {{ --bg:#080808; --surface:#111; --surface-2:#181818; --border:#242424; --text:#ececec; --muted:#8a8a8a;
  --orange:#f97316; --green:#10b981; --amber:#f59e0b; color-scheme: dark; }}
* {{ box-sizing:border-box; }}
body {{ background:var(--bg); color:var(--text); font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif; padding-inline:16px; margin:0; }}
main {{ max-width:1000px; margin:0 auto; padding-block:24px 56px; }}
a.back {{ color:var(--muted); font-size:.85rem; text-decoration:none; }}
h1 {{ font-size:1.5rem; margin:8px 0 0; }}
.sub {{ color:var(--muted); margin:4px 0 20px; }}
.kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:12px; margin-bottom:16px; }}
.kpi {{ background:var(--surface); border:1px solid var(--border); border-radius:8px; padding:14px 16px; }}
.kpi span {{ display:block; font-size:.72rem; text-transform:uppercase; letter-spacing:.06em; color:var(--muted); }}
.kpi b {{ font-size:1.6rem; font-variant-numeric:tabular-nums; }}
.kpi small {{ display:block; color:var(--muted); font-size:.78rem; }}
.warn {{ background:#2a1d08; border:1px solid #5a3d0a; color:var(--amber); border-radius:8px; padding:10px 14px; }}
.chips {{ display:flex; flex-wrap:wrap; gap:8px; margin:0 0 14px; }}
.chip {{ background:var(--surface); color:var(--muted); border:1px solid var(--border); border-radius:6px; padding:6px 12px; font:inherit; cursor:pointer; }}
.chip.on {{ color:var(--text); border-color:var(--orange); }}
.chip:focus-visible {{ outline:2px solid var(--orange); outline-offset:2px; }}
.card {{ background:var(--surface); border:1px solid var(--border); border-radius:8px; padding:6px 16px 10px; overflow-x:auto; }}
table {{ width:100%; border-collapse:collapse; font-variant-numeric:tabular-nums; min-width:720px; }}
th {{ text-align:left; font-size:.72rem; text-transform:uppercase; letter-spacing:.06em; color:var(--muted); font-weight:600; padding:12px 10px 8px 0; }}
td {{ padding:10px 10px 10px 0; border-top:1px solid var(--border); vertical-align:top; }}
td small {{ display:block; color:var(--muted); font-size:.78rem; }}
.num {{ text-align:right; }} th.num {{ text-align:right; }}
.ev {{ color:var(--green); font-weight:700; }}
.muted {{ color:var(--muted); }}
.empty {{ color:var(--muted); text-align:center; padding:28px; }}
.note {{ color:var(--muted); font-size:.8rem; margin-top:18px; }}
</style>
<main>
<h1>NBA · apuestas a jugadores con valor</h1>
<p class="sub">Lados más favorecidos por FanDuel (sin margen) que Stake paga por encima de su cuota justa · actualizado {stamp.astimezone():%d/%m %H:%M}</p>
{warn}
<div class="kpis">
  <div class="kpi"><span>Apuestas</span><b>{len(picks)}</b><small>probabilidad justa de {doc['min_prob']:.1%} o más</small></div>
  <div class="kpi"><span>Más probable</span>{best_html}</div>
</div>
<div class="chips">{chips}</div>
<div class="card"><table>
<tr><th class="num">Prob. justa</th><th>Jugador</th><th>Apuesta</th><th class="num">Stake</th><th class="num">Valor esp.</th><th class="num">Cuota justa</th><th class="num">FanDuel</th><th>Partido</th></tr>
{rows}</table></div>
<p class="note">Se muestran los lados con probabilidad justa de FanDuel igual o superior al 54,34 % (el equilibrio de un flex de 5 o 6, el mínimo del método), de más a menos probable. Valor esperado = probabilidad × cuota de Stake − 1, con la misma línea en las dos casas.
Apuesta cerca del inicio del partido, cuando alineaciones y lesiones ya están confirmadas. Una cuota de Stake por debajo de la "justa" no tiene valor.</p>
</main>
<script>
document.querySelectorAll('.chip').forEach(function(b) {{
  b.onclick = function() {{
    document.querySelectorAll('.chip').forEach(function(x) {{ x.classList.toggle('on', x === b); }});
    document.querySelectorAll('tr[data-s]').forEach(function(r) {{ r.hidden = b.dataset.s !== 'all' && r.dataset.s !== b.dataset.s; }});
  }};
}});
</script>
"""


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(json.loads(PICKS.read_text(encoding="utf-8"))), encoding="utf-8")
    print(f"Written {out}")


if __name__ == "__main__":
    main()
