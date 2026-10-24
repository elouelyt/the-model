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

APP_CSS = r'''
.bk { display:flex; flex-wrap:wrap; align-items:center; gap:12px 20px; padding:14px 16px; margin-bottom:14px; }
.bk label { color:var(--muted); font-size:.85rem; }
.bk input { background:var(--surface-2); color:var(--text); border:1px solid var(--border); border-radius:6px; padding:7px 10px; font:inherit; width:130px; }
.bk input:focus-visible, .stk:focus-visible, select:focus-visible { outline:2px solid var(--orange); outline-offset:2px; }
.bk .hint { color:var(--muted); font-size:.82rem; }
.sug { white-space:nowrap; }
.btn { background:var(--surface-2); color:var(--text); border:1px solid var(--border); border-radius:6px; padding:5px 10px; font:inherit; font-size:.82rem; cursor:pointer; }
.btn:hover { border-color:var(--orange); }
.btn[disabled] { color:var(--green); border-color:var(--border); cursor:default; }
.stk { background:var(--surface-2); color:var(--text); border:1px solid var(--border); border-radius:6px; padding:4px 6px; font:inherit; width:78px; text-align:right; }
select { background:var(--surface-2); color:var(--text); border:1px solid var(--border); border-radius:6px; padding:4px 6px; font:inherit; }
h2.sec { font-size:.78rem; text-transform:uppercase; letter-spacing:.08em; color:var(--muted); font-weight:600; margin:28px 0 12px; }
.pos { color:var(--green); } .neg { color:#f87171; }
details.bak { margin-top:14px; color:var(--muted); font-size:.85rem; }
details.bak textarea { width:100%; min-height:90px; background:var(--surface-2); color:var(--text); border:1px solid var(--border); border-radius:6px; padding:8px; font:12px ui-monospace,monospace; margin:8px 0; }
.combos { display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:12px; }
.combo { background:var(--surface); border:1px solid var(--border); border-radius:8px; padding:14px 16px; }
.combo .chead { display:flex; gap:6px; align-items:center; margin-bottom:8px; }
.combo .cn { margin-left:auto; color:var(--muted); font-size:.78rem; }
.fam { background:var(--surface-2); border:1px solid var(--border); border-radius:4px; padding:1px 7px; font-size:.72rem; color:var(--orange); }
.combo ul { list-style:none; margin:0; padding:0; }
.combo li { display:flex; justify-content:space-between; gap:10px; padding:7px 0; border-top:1px solid var(--border); }
.combo li small { display:block; color:var(--muted); font-size:.76rem; }
.combo .cfoot { display:flex; flex-wrap:wrap; gap:8px 16px; align-items:center; border-top:1px solid var(--border); padding-top:10px; margin-top:4px; font-size:.88rem; }
.combo .cfoot button { margin-left:auto; }
.ans { display:grid; grid-template-columns:repeat(auto-fit,minmax(320px,1fr)); gap:12px; margin-bottom:12px; }
.card.an h3 { font-size:.78rem; text-transform:uppercase; letter-spacing:.06em; color:var(--muted); margin:10px 0 0; }
.card.an table { min-width:0; }

tr.ok td:first-child { color:var(--green); font-weight:700; } tr.xx td:first-child { color:#f87171; font-weight:700; }
.combo.hit { border-color:var(--green); } .combo li.ok { color:var(--text); } .combo li.xx { color:var(--muted); }
.combo.miss .cn { color:#f87171; } .combo.hit .cn { color:var(--green); }

.bets-empty { color:var(--muted); text-align:center; padding:22px; }
'''

APP_JS = r'''
(function () {
  var KEY = 'nba_tracker_v1', mem = null;
  function load() {
    try { var s = localStorage.getItem(KEY); if (s) return JSON.parse(s); } catch (e) {}
    return mem || { bankroll: null, bets: [] };
  }
  function save() { mem = st; try { localStorage.setItem(KEY, JSON.stringify(st)); } catch (e) {} }
  var st = load(); if (!st.bets) st.bets = [];
  function fmt(x) { return x.toLocaleString('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }
  function units(ev) { return ev >= 0.03 ? 0.5 : 0.25; }
  function suggest(ev) { return st.bankroll ? Math.round(st.bankroll * 0.01 * units(ev) * 2) / 2 : null; }
  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }
  function profit(b) {
    if (b.status === 'won') return b.stake * (b.odds - 1);
    if (b.status === 'lost') return -b.stake;
    return 0;
  }

  var bk = document.getElementById('bk'), unitInfo = document.getElementById('unit');
  if (st.bankroll) bk.value = st.bankroll;

  function renderSuggestions() {
    unitInfo.textContent = st.bankroll
      ? '1 unidad = ' + fmt(st.bankroll * 0.01) + ' € (1 % del bankroll) · sugerencia: 0,25 u, o 0,5 u si el EV es del 3 % o más'
      : 'Escribe tu bankroll y te sugiero cuánto apostar en cada jugada (1 unidad = 1 %).';
    document.querySelectorAll('.combo .csug').forEach(function (c) {
      var s = st.bankroll ? Math.round(st.bankroll * 0.01 * 0.25 * 2) / 2 : null;
      c.textContent = s ? 'Sugerido ' + fmt(s) + ' € (0,25 u)' : '0,25 u';
    });
    document.querySelectorAll('tr[data-key]').forEach(function (r) {
      var ev = parseFloat(r.getAttribute('data-ev')), cell = r.querySelector('.sug'), s = suggest(ev);
      cell.textContent = '';
      cell.appendChild(document.createTextNode(s ? fmt(s) + ' €' : ''));
      cell.appendChild(el('small', null, units(ev).toString().replace('.', ',') + ' u'));
    });
  }

  function markPlaced() {
    var placed = {}; st.bets.forEach(function (b) { placed[b.key] = true; });
    document.querySelectorAll('tr[data-key] .btn, .combo .btn').forEach(function (btn) {
      var done = !!placed[btn.closest('[data-key]').getAttribute('data-key')];
      btn.disabled = done; btn.textContent = done ? '✓ Apostada' : 'Apostada';
    });
  }

  function renderBets() {
    var body = document.getElementById('betsbody'); body.textContent = '';
    var resolved = st.bets.filter(function (b) { return b.status === 'won' || b.status === 'lost'; });
    var wins = resolved.filter(function (b) { return b.status === 'won'; }).length;
    var total = st.bets.reduce(function (a, b) { return a + profit(b); }, 0);
    var staked = resolved.reduce(function (a, b) { return a + b.stake; }, 0);
    var pending = st.bets.filter(function (b) { return b.status === 'pending'; });
    function kpi(id, v, sub, cls) { var k = document.getElementById(id); k.textContent = ''; k.appendChild(el('b', cls, v)); k.appendChild(el('small', null, sub)); }
    var cls = total > 0 ? 'pos' : total < 0 ? 'neg' : '';
    kpi('k-profit', (total >= 0 ? '+' : '') + fmt(total) + ' €', resolved.length + ' resueltas', cls);
    kpi('k-roi', staked ? (total >= 0 ? '+' : '') + (total / staked * 100).toFixed(1).replace('.', ',') + ' %' : '—', 'beneficio por euro apostado', cls);
    kpi('k-hit', resolved.length ? Math.round(wins / resolved.length * 100) + ' %' : '—', wins + ' ganadas · ' + (resolved.length - wins) + ' perdidas', '');
    kpi('k-pend', String(pending.length), fmt(pending.reduce(function (a, b) { return a + b.stake; }, 0)) + ' € en juego', '');
    if (!st.bets.length) {
      var tr0 = el('tr'); var td0 = el('td', 'bets-empty', 'Aún no has anotado ninguna apuesta. Pulsa "Apostada" en una jugada cuando la hagas en Stake.'); td0.colSpan = 7; tr0.appendChild(td0); body.appendChild(tr0); return;
    }
    st.bets.slice().sort(function (a, b) { return b.date - a.date; }).forEach(function (b) {
      var tr = el('tr'), d = new Date(b.date);
      tr.appendChild(el('td', 'muted', ('0' + d.getDate()).slice(-2) + '/' + ('0' + (d.getMonth() + 1)).slice(-2)));
      var t = el('td'); t.appendChild(el('b', null, b.desc)); t.appendChild(el('small', null, b.game)); tr.appendChild(t);
      tr.appendChild(el('td', 'num', b.odds.toFixed(2)));
      var ts = el('td', 'num'), inp = el('input', 'stk'); inp.type = 'number'; inp.min = '0'; inp.step = '0.5'; inp.value = b.stake;
      inp.setAttribute('aria-label', 'Importe apostado');
      inp.onchange = function () { b.stake = parseFloat(inp.value) || 0; save(); renderBets(); };
      ts.appendChild(inp); tr.appendChild(ts);
      var ss = el('td'), sel = el('select');
      [['pending', 'Pendiente'], ['won', 'Ganada'], ['lost', 'Perdida'], ['void', 'Nula']].forEach(function (o) {
        var op = el('option', null, o[1]); op.value = o[0]; if (b.status === o[0]) op.selected = true; sel.appendChild(op);
      });
      sel.setAttribute('aria-label', 'Resultado');
      sel.onchange = function () { b.status = sel.value; save(); renderBets(); };
      ss.appendChild(sel); tr.appendChild(ss);
      var p = profit(b); tr.appendChild(el('td', 'num ' + (p > 0 ? 'pos' : p < 0 ? 'neg' : 'muted'), b.status === 'pending' ? '—' : (p >= 0 ? '+' : '') + fmt(p) + ' €'));
      var del = el('td'), x = el('button', 'btn', '✕'); x.setAttribute('aria-label', 'Borrar apuesta');
      x.onclick = function () { st.bets = st.bets.filter(function (o) { return o !== b; }); save(); renderBets(); markPlaced(); };
      del.appendChild(x); tr.appendChild(del);
      body.appendChild(tr);
    });
  }

  bk.oninput = function () { var v = parseFloat(bk.value); st.bankroll = v > 0 ? v : null; save(); renderSuggestions(); };
  document.querySelectorAll('tr[data-key] .btn, .combo .btn').forEach(function (btn) {
    btn.onclick = function () {
      var r = btn.closest('[data-key]'), ev = parseFloat(r.getAttribute('data-ev'));
      st.bets.push({ key: r.getAttribute('data-key'), date: Date.now(), desc: r.getAttribute('data-desc'), game: r.getAttribute('data-game'),
        odds: parseFloat(r.getAttribute('data-odds')), ev: ev, stake: (r.classList.contains('combo') ? (st.bankroll ? Math.round(st.bankroll * 0.01 * 0.25 * 2) / 2 : 0) : suggest(ev)) || 0, status: 'pending' });
      save(); markPlaced(); renderBets();
    };
  });
  var box = document.getElementById('backup');
  document.getElementById('exp').onclick = function () { box.value = JSON.stringify(st); box.select(); };
  document.getElementById('imp').onclick = function () {
    try {
      var n = JSON.parse(box.value);
      if (!n || !Array.isArray(n.bets)) throw new Error('formato');
      st = n; save(); bk.value = st.bankroll || ''; renderSuggestions(); markPlaced(); renderBets(); box.value = '';
    } catch (e) { box.value = 'Texto no válido: pega aquí el que exportaste.'; }
  };
  renderSuggestions(); markPlaced(); renderBets();
})();
'''


def _row(p: dict) -> str:
    side = "Más de" if p["side"] == "Over" else "Menos de"
    stat = STAT_ES.get(p["stat"], p["stat"])
    desc = f'{p["player"]} {side} {p["line"]:g} {stat}'
    key = f'{p["start"][:16]}|{p["player"]}|{p["stat"]}|{p["side"]}|{p["line"]}'
    books = p.get("books", 1)
    return (
        f'<tr data-s="{escape(p["stat"])}" data-ev="{p["ev"]}" data-win="{p["fair_prob"]}" '
        f'data-odds="{p["stake_odds"]}" data-key="{escape(key)}" data-desc="{escape(desc)}" '
        f'data-game="{escape(p["game"])}">'
        f'<td class="muted">{escape(p["game"])}<small>{local_time(p["start"])}</small></td>'
        f'<td><span class="tag">{escape(stat)}</span><b>{escape(p["player"])} {side} {p["line"]:g}</b></td>'
        f'<td class="num"><span class="pill">{p["fair_prob"]:.1%}</span></td>'
        f'<td class="num ev">{p["ev"]:+.2%}<i class="meter"><u style="width:{min(p["ev"] / 0.12, 1) * 100:.0f}%"></u></i></td>'
        f'<td class="num"><b>{p["stake_odds"]:.2f}</b><small>justa {p["fair_odds"]:.2f}</small></td>'
        f'<td class="num muted">{escape(p["fanduel"])}<small>{books} {"casa" if books == 1 else "casas"}</small></td>'
        f'<td class="num sug"></td>'
        f'<td><button class="btn" type="button">Apostada</button></td></tr>'
    )


FAMILY_ES = {"probabilidad": "Probabilidad", "valor": "Valor", "mixta": "Mixta", "pura": "Prob. pura"}


def _combos_html(doc: dict, tracking: bool = False) -> str:
    combos = doc.get("combos_tracking" if tracking else "combos") or []
    if not combos:
        return ""
    cards = []
    for i, c in enumerate(combos):
        legs = "".join(
            f'<li><span><b>{escape(l["player"])}</b> {"Más de" if l["side"] == "Over" else "Menos de"} {l["line"]:g} '
            f'<span class="tag">{escape(STAT_ES.get(l["stat"], l["stat"]))}</span>'
            f'<small>{escape(l["game"])} · {local_time(l["start"])}</small></span>'
            f'<span class="num"><b>{l["stake_odds"]:.2f}</b><small>{l["fair_prob"]:.0%}</small></span></li>'
            for l in c["legs"]
        )
        fams = " ".join(f'<span class="fam">{escape(FAMILY_ES.get(f, f))}</span>' for f in c["families"])
        desc = " + ".join(f'{l["player"]} {"+" if l["side"] == "Over" else "-"}{l["line"]:g} {STAT_ES.get(l["stat"], l["stat"])}'
                          for l in c["legs"])
        key = "combo|" + "|".join(l["key"] for l in c["legs"])
        cards.append(
            f'<div class="combo" data-key="{escape(key)}" data-desc="{escape("Combinada: " + desc)}" '
            f'data-odds="{c["odds"]}" data-ev="{c["ev"]}" data-game="3 partidos">'
            f'<div class="chead">{fams}<span class="cn">Combinada {i + 1}</span></div>'
            f'<ul>{legs}</ul>'
            f'<div class="cfoot"><span>Cuota <b>{c["odds"]:.2f}</b></span><span>Prob. <b>{c["prob"]:.1%}</b></span>'
            f'<span class="ev">EV {c["ev"]:+.0%}</span>'
            + ('' if tracking else '<span class="csug"></span><button class="btn cbtn" type="button">Apostada</button>')
            + '</div></div>'
        )
    if tracking:
        return (
            '<details class="bak" style="margin-top:18px"><summary>Seguimiento · combinadas con partidos que ya han empezado (solo para comprobar resultados)</summary>'
            '<p class="note" style="margin-top:8px">No se pueden apostar ya: usan las cuotas de antes del inicio guardadas hoy. '
            'Se liquidan solas con el marcador real para medir qué criterio funciona mejor.</p>'
            f'<div class="combos" style="margin-top:12px">{"".join(cards)}</div></details>'
        )
    return (
        '<h2 class="sec">Combinadas de 3 · recomendadas</h2>'
        '<p class="note" style="margin-top:0">Tres piernas de partidos distintos y jugadores distintos, solo de partidos que no han empezado. '
        'Cuota = producto de las cuotas de Stake; probabilidad = producto de las probabilidades justas. '
        'Tres familias para comparar resultados: Probabilidad (más acierto), Valor (más EV) y Mixta (EV ≥ 20 % con más acierto). '
        'Importe sugerido: 0,25 u, como en el método.</p>'
        f'<div class="combos">{"".join(cards)}</div>'
    )


def _tbl(title: str, rows: list[dict]) -> str:
    if not rows:
        return ""
    body = "".join(
        f'<tr><td>{escape(r["name"])}</td><td class="num">{r["n"]}</td><td class="num">{r["hit"]:.0%}</td>'
        f'<td class="num muted">{r["expected"]:.0%}</td>'
        f'<td class="num {"pos" if r["roi"] > 0 else "neg"}">{r["roi"]:+.0%}</td></tr>' for r in rows)
    return (f'<div class="card an"><h3>{escape(title)}</h3><table><tr><th></th><th class="num">N</th>'
            f'<th class="num">Acierto</th><th class="num">Esperado</th><th class="num">ROI</th></tr>{body}</table></div>')



def _detail_html(a: dict) -> str:
    """Every settled leg (sortable) and every settled combo with the outcome of each leg."""
    legs = a.get("legs") or []
    out = ""
    if legs:
        rows = "".join(
            f'<tr class="{"ok" if l["ok"] else "xx"}" data-ev="{l["ev"]}" data-win="{l["win"]}">'
            f'<td>{"✓" if l["ok"] else "✗"}</td>'
            f'<td><b>{escape(l["player"])}</b><small>{escape(l["game"])}</small></td>'
            f'<td>{"Más de" if l["side"] == "Over" else "Menos de"} {l["line"]:g} <span class="tag">{escape(STAT_ES.get(l["stat"], l["stat"]))}</span></td>'
            f'<td class="num">{l["win"]:.1%}</td><td class="num">{l["ev"]:+.1%}</td><td class="num">{l["odds"]:.2f}</td>'
            f'<td class="num"><b>{l["actual"]}</b><small>{l["min"]} min</small></td>'
            f'<td class="num muted">{l["margin"]}</td><td class="num muted">{l["books"]}</td></tr>' for l in legs)
        out += (
            '<details class="bak" open><summary>Todas las apuestas simples liquidadas (' + str(len(legs)) + ')</summary>'
            '<div class="chips" style="margin-top:10px"><button class="chip lsort on" data-k="ev" type="button">Ordenar por EV%</button>'
            '<button class="chip lsort" data-k="win" type="button">Ordenar por Win%</button></div>'
            '<div class="card"><table id="legtbl"><tr><th></th><th>Jugador</th><th>Apuesta</th><th class="num">Win%</th>'
            '<th class="num">EV%</th><th class="num">Cuota</th><th class="num">Real</th><th class="num">Margen</th><th class="num">Casas</th></tr>'
            + rows + '</table></div></details>'
            '<script>(function(){var t=document.getElementById("legtbl");if(!t)return;'
            'document.querySelectorAll(".chip.lsort").forEach(function(b){b.onclick=function(){'
            'document.querySelectorAll(".chip.lsort").forEach(function(x){x.classList.toggle("on",x===b)});'
            'var k="data-"+b.dataset.k,r=Array.prototype.slice.call(t.querySelectorAll("tr[data-ev]"));'
            'r.sort(function(p,q){return parseFloat(q.getAttribute(k))-parseFloat(p.getAttribute(k))});'
            'r.forEach(function(x){x.parentNode.appendChild(x)})}})})();</script>'
        )
    combos = a.get("combos") or []
    if combos:
        cards = []
        for c in reversed(combos):
            lines = "".join(
                f'<li class="{"ok" if o["status"] == "won" else "xx" if o["status"] == "lost" else ""}">'
                f'<span>{"✓" if o["status"] == "won" else "✗" if o["status"] == "lost" else "—"} <b>{escape(l["player"])}</b> '
                f'{"Más de" if l["side"] == "Over" else "Menos de"} {l["line"]:g} {escape(STAT_ES.get(l["stat"], l["stat"]))}</span>'
                f'<span class="num">real <b>{o["actual"]}</b> · {o["min"]} min</span></li>'
                for l, o in zip(c["legs"], c["outcomes"]))
            fams = " ".join(f'<span class="fam">{escape(FAMILY_ES.get(f, f))}</span>' for f in c["families"])
            seg = '<span class="tag">seguimiento</span>' if c.get("tracking") else ""
            cards.append(
                f'<div class="combo {"hit" if c["hit"] else "miss"}"><div class="chead">{fams}{seg}'
                f'<span class="cn">{"ACERTADA" if c["hit"] else "fallada"} · cuota {c["odds"]:.2f}</span></div>'
                f'<ul>{lines}</ul></div>')
        out += ('<details class="bak"><summary>Todas las combinadas liquidadas (' + str(len(combos)) + ')</summary>'
                '<div class="combos" style="margin-top:12px">' + "".join(cards) + '</div></details>')
    return out


def _analysis_html(doc: dict) -> str:
    a = doc.get("analysis")
    head = '<h2 class="sec">Resultados y análisis · por qué se acierta o se falla</h2>'
    if not a or not a.get("legs_settled"):
        return head + ('<p class="note" style="margin-top:0">Aún sin resultados. Las piernas y combinadas se liquidan solas '
                       'con los marcadores reales cuando terminan los partidos, y aquí aparecerá cómo calibra cada mercado.</p>')
    ctx = a["context"]

    def pct(x):
        return "—" if x is None else f"{x:.0%}"
    fam = "".join(
        f'<tr><td>{escape(FAMILY_ES.get(f["name"], f["name"]))}</td><td class="num">{f["n"]}</td>'
        f'<td class="num">{f["hits"]}</td><td class="num muted">{f["expected_hit"]:.0%}</td>'
        f'<td class="num {"pos" if f["roi"] > 0 else "neg"}">{f["roi"]:+.0%}</td></tr>' for f in a["combo_families"])
    fam_html = (f'<div class="card an"><h3>Combinadas por familia</h3><table><tr><th></th><th class="num">N</th>'
                f'<th class="num">Acertadas</th><th class="num">Esperado</th><th class="num">ROI</th></tr>{fam}</table></div>'
                if fam else "")
    return (head
            + f'<p class="note" style="margin-top:0">{a["legs_settled"]} piernas liquidadas ({a["legs_void"]} anuladas por no jugar) '
              f'y {a["combos_settled"]} combinadas. "Esperado" es la probabilidad justa media; si el acierto real queda por debajo, '
              f'el mercado o la casa de referencia están sobrevalorando esa clase de apuesta. ROI con 1 unidad por apuesta a cuota de Stake.</p>'
            + '<div class="ans">'
            + _tbl("Calibración (por probabilidad)", a["calibration"]) + _tbl("Por mercado", a["by_stat"])
            + _tbl("Over / Under", a["by_side"]) + _tbl("Por nivel de EV", a["by_ev"]) + _tbl("Por casas de referencia", a["by_books"])
            + fam_html + '</div>'
            + _detail_html(a)
            + f'<div class="card an"><h3>Contexto del partido</h3><p class="note" style="margin:6px 0">Partidos con diferencia final de '
              f'{ctx["blowout_threshold"]}+ puntos ({ctx["n_blowout"]} piernas) frente a ajustados ({ctx["n_close"]}): '
              f'<b>Over</b> {pct(ctx["over_blowout"])} vs {pct(ctx["over_close"])} · <b>Under</b> {pct(ctx["under_blowout"])} vs {pct(ctx["under_close"])}. '
              f'En palizas los titulares descansan: favorece a los Under y perjudica a los Over.</p></div>')


def build(doc: dict) -> str:
    picks = doc["picks"]
    stamp = datetime.fromisoformat(doc["timestamp"])
    stale = datetime.now(timezone.utc) - stamp > STALE_AFTER
    stats_present = sorted({p["stat"] for p in picks}, key=lambda s: list(STAT_ES).index(s) if s in STAT_ES else 99)
    chips = '<button class="chip on" data-s="all">Todos</button>' + "".join(
        f'<button class="chip" data-s="{escape(s)}">{escape(STAT_ES.get(s, s))}</button>' for s in stats_present
    )
    rows = "".join(_row(p) for p in picks) or '<tr><td colspan="8" class="empty">Ninguna apuesta con valor ahora mismo.</td></tr>'
    combos_html = _combos_html(doc) + _combos_html(doc, tracking=True)
    analysis_html = _analysis_html(doc)
    best = picks[0] if picks else None
    best_html = (f'<b class="ev">{best["ev"]:+.1%}</b><small>{escape(best["player"])} · '
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
.sep {{ flex:1; }}
.chip.on {{ color:var(--text); border-color:var(--orange); }}
.chip:focus-visible {{ outline:2px solid var(--orange); outline-offset:2px; }}
.card {{ background:var(--surface); border:1px solid var(--border); border-radius:8px; padding:6px 16px 10px; overflow-x:auto; }}
table {{ width:100%; border-collapse:collapse; font-variant-numeric:tabular-nums; min-width:680px; }}
th {{ text-align:left; font-size:.72rem; text-transform:uppercase; letter-spacing:.06em; color:var(--muted); font-weight:600; padding:12px 10px 8px 0; }}
td {{ padding:10px 10px 10px 0; border-top:1px solid var(--border); vertical-align:top; }}
td small {{ display:block; color:var(--muted); font-size:.78rem; }}
.num {{ text-align:right; }} th.num {{ text-align:right; }}
.ev {{ color:var(--green); font-weight:700; }}
.muted {{ color:var(--muted); }}
.tag {{ display:inline-block; background:var(--surface-2); border:1px solid var(--border); border-radius:4px; padding:1px 7px; font-size:.72rem; color:var(--muted); margin-right:8px; }}
.pill {{ background:var(--surface-2); border-radius:5px; padding:3px 8px; }}
.meter {{ display:block; height:4px; background:var(--surface-2); border-radius:2px; margin:4px 0 0 auto; width:80px; overflow:hidden; }}
.meter u {{ display:block; height:100%; background:var(--green); }}
.empty {{ color:var(--muted); text-align:center; padding:28px; }}
.note {{ color:var(--muted); font-size:.8rem; margin-top:18px; }}
{APP_CSS}</style>
<main>
<h1>NBA · apuestas a jugadores con valor</h1>
<p class="sub">Cuota justa de las casas serias (FanDuel y Pinnacle, sin margen) frente a la cuota de Stake · mismo método de Beat the Sportsbooks · actualizado {stamp.astimezone():%d/%m %H:%M}</p>
{warn}
<div class="kpis">
  <div class="kpi"><span>Apuestas</span><b>{len(picks)}</b><small>con EV positivo, de mayor a menor</small></div>
  <div class="kpi"><span>Mejor EV</span>{best_html}</div>
</div>
<div class="card bk"><label for="bk">Bankroll actual (€)</label><input id="bk" type="number" min="0" step="1" inputmode="decimal" placeholder="p. ej. 1500"><span class="hint" id="unit"></span></div>
<div class="chips">{chips}<span class="sep"></span><button class="chip sort on" data-k="ev">Ordenar por EV%</button><button class="chip sort" data-k="win">Ordenar por Win%</button></div>
<div class="card"><table>
<tr><th>Partido</th><th>Apuesta</th><th class="num">Win%</th><th class="num">EV%</th><th class="num">Stake</th><th class="num">Casas serias</th><th class="num">Apostar</th><th></th></tr>
{rows}</table></div>
{combos_html}
<p class="note">Win% = probabilidad justa sin margen, promedio de las casas serias disponibles para esa línea (FD = FanDuel, PIN = Pinnacle). EV% = Win% × cuota de Stake − 1, con la misma línea en las dos casas, de mayor a menor. Apuesta en cuanto salga la jugada (las líneas cambian rápido) y cerca del inicio del partido, cuando alineaciones y lesiones ya están confirmadas.</p>
<h2 class="sec">Mis apuestas · track record</h2>
<div class="kpis"><div class="kpi"><span>Beneficio</span><div id="k-profit"></div></div><div class="kpi"><span>ROI</span><div id="k-roi"></div></div><div class="kpi"><span>Aciertos</span><div id="k-hit"></div></div><div class="kpi"><span>Pendientes</span><div id="k-pend"></div></div></div>
<div class="card"><table><tr><th>Fecha</th><th>Apuesta</th><th class="num">Cuota</th><th class="num">Importe €</th><th>Resultado</th><th class="num">Beneficio</th><th></th></tr><tbody id="betsbody"></tbody></table></div>
{analysis_html}
<details class="bak"><summary>Copia de seguridad (para pasar tus apuestas a otro dispositivo)</summary>
<textarea id="backup" aria-label="Copia de seguridad" placeholder="Pulsa Exportar y copia este texto. Para restaurar, pégalo aquí y pulsa Importar."></textarea>
<button class="btn" id="exp" type="button">Exportar</button> <button class="btn" id="imp" type="button">Importar</button></details>
<p class="note">Tus apuestas se guardan solo en este navegador y este dispositivo; si borras los datos del navegador se pierden, así que exporta de vez en cuando.</p>
</main>
<script>
document.querySelectorAll('.chip.sort').forEach(function(b) {{
  b.onclick = function() {{
    document.querySelectorAll('.chip.sort').forEach(function(x) {{ x.classList.toggle('on', x === b); }});
    var key = 'data-' + b.dataset.k, rows = Array.prototype.slice.call(document.querySelectorAll('tr[data-ev]'));
    rows.sort(function(a, c) {{ return parseFloat(c.getAttribute(key)) - parseFloat(a.getAttribute(key)); }});
    rows.forEach(function(r) {{ r.parentNode.appendChild(r); }});
  }};
}});
document.querySelectorAll('.chip[data-s]').forEach(function(b) {{
  b.onclick = function() {{
    document.querySelectorAll('.chip[data-s]').forEach(function(x) {{ x.classList.toggle('on', x === b); }});
    document.querySelectorAll('tr[data-s]').forEach(function(r) {{ r.hidden = b.dataset.s !== 'all' && r.dataset.s !== b.dataset.s; }});
  }};
}});
</script>
<script>{APP_JS}</script>
"""


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(json.loads(PICKS.read_text(encoding="utf-8"))), encoding="utf-8")
    print(f"Written {out}")


if __name__ == "__main__":
    main()
