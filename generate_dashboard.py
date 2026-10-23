"""Build the private track-record dashboard (plain HTML, to be encrypted with staticrypt).

Flat 15 EUR stake per parlay, always priced at the Stake odds.
Usage: python generate_dashboard.py [output_path]
"""

import json
import sys
from datetime import date
from html import escape
from pathlib import Path

ROOT = Path(__file__).parent
TRACK = ROOT / "data" / "track_record.json"
DEFAULT_OUT = ROOT / "build" / "panel_src.html"

STAKE = 15.0
BUCKETS = [("< 1.50", 0, 1.5), ("1.50 – 1.99", 1.5, 2.0), ("≥ 2.00", 2.0, 99)]
MONTHS_ES = ["", "Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]


def load_bets() -> list[dict]:
    """Flatten track_record.json into one dict per parlay, sorted by date."""
    data = json.loads(TRACK.read_text(encoding="utf-8"))
    bets = []
    for month, mdata in data["months"].items():
        year, mon = (int(x) for x in month.split("-"))
        for day, d in mdata["days"].items():
            for p in d["parlays"]:
                bets.append({
                    "date": date(year, mon, int(day)),
                    "legs": p["legs"],
                    "odds": p.get("stake_odds") or p.get("best_odds"),
                    "won": p.get("won"),
                    "opponent": p.get("opponent", ""),
                })
    bets.sort(key=lambda b: b["date"])
    return bets


def profit(b: dict) -> float:
    return STAKE * (b["odds"] - 1) if b["won"] else -STAKE


def summarize(bets: list[dict]) -> dict:
    n = len(bets)
    wins = sum(1 for b in bets if b["won"])
    total = sum(profit(b) for b in bets)
    return {
        "n": n,
        "wins": wins,
        "hit": wins / n if n else 0.0,
        "profit": total,
        "roi": total / (n * STAKE) if n else 0.0,
        "avg_odds": sum(b["odds"] for b in bets) / n if n else 0.0,
    }


def fmt(x: float, signed: bool = True) -> str:
    return f"{x:+,.2f}" if signed else f"{x:,.2f}"


def cls(x: float) -> str:
    return "pos" if x > 0 else "neg" if x < 0 else ""


def curve_svg(bets: list[dict]) -> str:
    """Cumulative profit line with area fill, zero line and endpoint marker."""
    w, h, pl, pr, pt, pb = 720, 260, 44, 16, 16, 28
    pts, acc = [(0, 0.0)], 0.0
    for i, b in enumerate(bets, 1):
        acc += profit(b)
        pts.append((i, acc))
    lo, hi = min(0, min(p[1] for p in pts)), max(0, max(p[1] for p in pts))
    span = (hi - lo) or 1
    lo -= span * 0.08
    hi += span * 0.08
    span = hi - lo
    n = max(len(pts) - 1, 1)

    def X(i: float) -> float:
        return pl + (w - pl - pr) * i / n

    def Y(v: float) -> float:
        return pt + (h - pt - pb) * (hi - v) / span

    line = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in pts)
    area = f"{X(0):.1f},{Y(0):.1f} {line} {X(n):.1f},{Y(0):.1f}"
    step = next(c for c in (10, 20, 50, 100, 200, 500) if span / c <= 7)
    ticks = ""
    t = int(lo // step) * step
    while t <= hi:
        if lo <= t <= hi:
            ticks += (f'<line x1="{pl}" x2="{w - pr}" y1="{Y(t):.1f}" y2="{Y(t):.1f}" class="grid{" zero" if t == 0 else ""}"/>'
                      f'<text x="{pl - 8}" y="{Y(t) + 4:.1f}" class="axis" text-anchor="end">{t:+d} €</text>')
        t += step
    end_i, end_v = pts[-1]
    color = "var(--green)" if end_v >= 0 else "var(--red)"
    dots = "".join(
        f'<circle cx="{X(i):.1f}" cy="{Y(v):.1f}" r="9" fill="transparent"><title>Apuesta {i}: {v:+.2f} €</title></circle>'
        for i, v in pts[1:]
    )
    return (
        f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Beneficio acumulado en euros">{ticks}'
        f'<polygon points="{area}" fill="{color}" opacity="0.10"/>'
        f'<polyline points="{line}" fill="none" stroke="{color}" stroke-width="2" stroke-linejoin="round"/>'
        f'<circle cx="{X(end_i):.1f}" cy="{Y(end_v):.1f}" r="4.5" fill="{color}" stroke="var(--surface)" stroke-width="2"/>'
        f'<text x="{X(end_i) - 8:.1f}" y="{Y(end_v) - 10:.1f}" class="axis end" text-anchor="end">{end_v:+.0f} €</text>'
        f'<text x="{pl}" y="{h - 8}" class="axis">Apuesta 1</text>'
        f'<text x="{w - pr}" y="{h - 8}" class="axis" text-anchor="end">Apuesta {n}</text>{dots}</svg>'
    )


def monthly_svg(rows: list[tuple[str, float]]) -> str:
    """Zero-based bars of monthly profit, anchored to the baseline."""
    w, h, pt, pb = 360, 230, 28, 44
    m = max(abs(v) for _, v in rows) or 1
    base = pt + (h - pt - pb) * (m / (2 * m))
    half = (h - pt - pb) / 2
    bw = min(56, (w - 20) / len(rows) - 12)
    out = f'<line x1="10" x2="{w - 10}" y1="{base:.1f}" y2="{base:.1f}" class="grid zero"/>'
    for i, (label, v) in enumerate(rows):
        cx = 10 + (w - 20) * (i + 0.5) / len(rows)
        bh = abs(v) / m * half
        y = base - bh if v >= 0 else base
        color = "var(--green)" if v >= 0 else "var(--red)"
        ty = y - 6 if v >= 0 else y + bh + 14
        out += (f'<rect x="{cx - bw / 2:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{max(bh, 1):.1f}" rx="3" fill="{color}"><title>{label}: {v:+.2f} €</title></rect>'
                f'<text x="{cx:.1f}" y="{ty:.1f}" class="axis val" text-anchor="middle">{v:+.0f}</text>'
                f'<text x="{cx:.1f}" y="{h - 8}" class="axis" text-anchor="middle">{label}</text>')
    return f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Beneficio por mes">{out}</svg>'


def build(bets: list[dict]) -> str:
    resolved = [b for b in bets if b["won"] is not None]
    pending = [b for b in bets if b["won"] is None]
    s = summarize(resolved)

    months: dict[str, list[dict]] = {}
    for b in resolved:
        months.setdefault(f"{b['date'].year}-{b['date'].month:02d}", []).append(b)
    month_rows = [(MONTHS_ES[int(k[5:])], sum(profit(b) for b in v)) for k, v in sorted(months.items())]

    bucket_html = ""
    for label, lo, hi in BUCKETS:
        sub = [b for b in resolved if lo <= b["odds"] < hi]
        if not sub:
            continue
        bs = summarize(sub)
        bucket_html += (
            f'<tr><td>{label}</td><td class="num">{bs["n"]}</td>'
            f'<td class="num">{bs["hit"]:.0%}</td>'
            f'<td class="num"><span class="bar"><i style="width:{bs["hit"] * 100:.0f}%"></i></span></td>'
            f'<td class="num {cls(bs["profit"])}">{fmt(bs["profit"])} €</td>'
            f'<td class="num {cls(bs["roi"])}">{bs["roi"]:+.0%}</td></tr>'
        )

    pend_html = "".join(
        f'<li><span>{escape(" + ".join(b["legs"]))}'
        f'{" <small>vs " + escape(b["opponent"]) + "</small>" if b["opponent"] else ""}</span>'
        f'<b>{b["odds"]:.2f}</b></li>' for b in pending
    ) or '<li class="empty">Ninguna apuesta pendiente</li>'

    recent = "".join(
        f'<tr><td>{b["date"]:%d/%m}</td><td>{escape(" + ".join(b["legs"]))}</td>'
        f'<td class="num">{b["odds"]:.2f}</td>'
        f'<td class="num {"pos" if b["won"] else "neg"}">{"Ganada" if b["won"] else "Perdida"}</td></tr>'
        for b in reversed(resolved[-15:])
    )

    first, last = resolved[0]["date"], resolved[-1]["date"]
    return f"""<title>Panel del modelo</title>
<meta name="robots" content="noindex,nofollow">
<style>
:root {{ --bg:#080808; --surface:#111; --surface-2:#181818; --border:#242424; --text:#ececec; --muted:#8a8a8a;
  --orange:#f97316; --green:#10b981; --red:#f87171; color-scheme: dark; }}
* {{ box-sizing:border-box; }}
body {{ background:var(--bg); color:var(--text); font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif; padding-inline:16px; }}
main {{ max-width:880px; margin:0 auto; padding-block:28px 56px; }}
h1 {{ font-size:1.5rem; margin:0; }}
h2 {{ font-size:.78rem; text-transform:uppercase; letter-spacing:.08em; color:var(--muted); font-weight:600; margin:0 0 14px; }}
.sub {{ color:var(--muted); margin:4px 0 24px; }}
.kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; margin-bottom:16px; }}
.kpi {{ background:var(--surface); border:1px solid var(--border); border-radius:8px; padding:14px 16px; }}
.kpi span {{ display:block; font-size:.72rem; text-transform:uppercase; letter-spacing:.06em; color:var(--muted); }}
.kpi b {{ font-size:1.7rem; font-variant-numeric:tabular-nums; }}
.kpi small {{ display:block; color:var(--muted); font-size:.78rem; }}
.card {{ background:var(--surface); border:1px solid var(--border); border-radius:8px; padding:18px; margin-bottom:16px; }}
.two {{ display:grid; grid-template-columns:3fr 2fr; gap:16px; }}
@media (max-width:700px) {{ .two {{ grid-template-columns:1fr; }} }}
.two .card {{ margin-bottom:0; }}
svg {{ width:100%; height:auto; display:block; }}
.grid {{ stroke:#1d1d1d; stroke-width:1; }} .grid.zero {{ stroke:#3a3a3a; }}
.axis {{ fill:var(--muted); font-size:11px; font-variant-numeric:tabular-nums; }}
.axis.end,.axis.val {{ fill:var(--text); font-weight:600; }}
.pos {{ color:var(--green); }} .neg {{ color:var(--red); }}
.scroll {{ overflow-x:auto; }}
table {{ width:100%; border-collapse:collapse; font-variant-numeric:tabular-nums; }}
th {{ text-align:left; font-size:.72rem; text-transform:uppercase; letter-spacing:.06em; color:var(--muted); font-weight:600; padding:0 8px 8px 0; }}
td {{ padding:8px 8px 8px 0; border-top:1px solid var(--border); }}
.num {{ text-align:right; }} th.num {{ text-align:right; }}
.bar {{ display:inline-block; width:80px; height:6px; background:var(--surface-2); border-radius:3px; overflow:hidden; vertical-align:middle; }}
.bar i {{ display:block; height:100%; background:var(--orange); }}
ul {{ list-style:none; margin:0; padding:0; }}
li {{ display:flex; justify-content:space-between; gap:12px; padding:8px 0; border-top:1px solid var(--border); }}
li:first-child {{ border-top:0; }} li small {{ color:var(--muted); }} li.empty {{ color:var(--muted); }}
.note {{ color:var(--muted); font-size:.8rem; margin-top:20px; }}
</style>
<main>
<h1>Panel del modelo</h1>
<p class="sub">{first:%d/%m/%Y} – {last:%d/%m/%Y} · 15 € por apuesta · cuotas de Stake</p>
<div class="kpis">
  <div class="kpi"><span>Beneficio</span><b class="{cls(s['profit'])}">{fmt(s['profit'])} €</b><small>{s['n']} apuestas resueltas</small></div>
  <div class="kpi"><span>ROI</span><b class="{cls(s['roi'])}">{s['roi']:+.1%}</b><small>beneficio por euro apostado</small></div>
  <div class="kpi"><span>Aciertos</span><b>{s['hit']:.0%}</b><small>{s['wins']} ganadas · {s['n'] - s['wins']} perdidas</small></div>
  <div class="kpi"><span>Cuota media</span><b>{s['avg_odds']:.2f}</b><small>acierto mínimo para cubrir: {1 / s['avg_odds']:.0%}</small></div>
</div>
<section class="card"><h2>Beneficio acumulado (€)</h2>{curve_svg(resolved)}</section>
<div class="two">
  <section class="card"><h2>Acierto por rango de cuota</h2><div class="scroll"><table>
    <tr><th>Cuota</th><th class="num">Apuestas</th><th class="num">Acierto</th><th></th><th class="num">Beneficio</th><th class="num">ROI</th></tr>{bucket_html}</table></div></section>
  <section class="card"><h2>Beneficio por mes</h2>{monthly_svg(month_rows)}</section>
</div>
<section class="card" style="margin-top:16px"><h2>Pendientes</h2><ul>{pend_html}</ul></section>
<section class="card"><h2>Últimas apuestas resueltas</h2><div class="scroll"><table>
  <tr><th>Fecha</th><th>Apuesta</th><th class="num">Cuota</th><th class="num">Resultado</th></tr>{recent}</table></div></section>
<p class="note">Un parlay se gana solo si aciertan todas sus selecciones. Las pendientes no cuentan en ninguna métrica.</p>
</main>
"""


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(load_bets()), encoding="utf-8")
    print(f"Written {out}")


if __name__ == "__main__":
    main()
