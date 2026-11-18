#!/usr/bin/env python3
"""Diario de picks de tenis: para cada día guarda si hubo pick y, si no, por qué.

Escribe data/tennis_diagnostico.json  {"days": {"2026-11-14": {...}}}  y genera el bloque HTML
«Diario de picks de tenis» que se muestra en la pestaña Recomendaciones.

Uso:
  python scripts/tennis_audit.py --backfill          # reconstruye días antiguos desde el historial de data/site.enc
  python scripts/tennis_audit.py --report            # imprime hoy y los últimos días (para la tarea de las 10:00)
"""

import argparse
import html
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from safe_json import load_json, save_json  # noqa: E402
from src.agents.single_bet_agent import _MIN_EDGE, _MIN_MODEL_PROB, _MIN_PRICE  # noqa: E402

DIAG = ROOT / "data" / "tennis_diagnostico.json"
TRACK = ROOT / "data" / "track_record.json"


def load() -> dict:
    return load_json(DIAG, {"days": {}})


def save(diag: dict) -> None:
    save_json(DIAG, diag, ensure_ascii=False, indent=1, sort_keys=True, default=str)


def fails(model_prob, edge, price, signal) -> list[str]:
    """Filtros del pick diario que NO cumple este jugador (mismos umbrales que select_daily_pick)."""
    out = []
    if signal == "no_bet":
        out.append("el modelo marca «no apostar»")
    if model_prob is not None and model_prob < _MIN_MODEL_PROB:
        out.append(f"probabilidad {model_prob * 100:.0f} % < {_MIN_MODEL_PROB * 100:.0f} %")
    if edge is not None and edge < _MIN_EDGE:
        out.append(f"ventaja {edge * 100:+.1f} % < {_MIN_EDGE * 100:.0f} %")
    if price is not None and price < _MIN_PRICE:
        out.append(f"cuota {price:.2f} < {_MIN_PRICE:.2f}")
    return out


def _player_row(name, model_prob, edge, price, signal) -> dict:
    return {"name": name, "model_prob": model_prob, "edge": edge, "price": price, "signal": signal,
            "fails": fails(model_prob, edge, price, signal)}


def _summary(matches: list[dict], pick: dict | None, note: str = "") -> str:
    if not matches:
        return note or "La API de cuotas no devolvió ningún partido de ATP ese día (no hay torneo activo o no hay cuotas)."
    rows = [(p, m) for m in matches for p in m["players"]]
    if pick:
        return (f"Pick: {pick['player']} (modelo {pick['model_prob'] * 100:.0f} %, ventaja "
                f"{pick['edge'] * 100:+.1f} %, cuota {pick.get('best_price', 0):.2f}).")
    ok = [p for p, _ in rows if not p["fails"]]
    if ok:  # cumple filtros pero no se eligió (p. ej. partido ya empezado)
        best = max(ok, key=lambda p: p["edge"] or 0)
        return (f"{len(matches)} partidos; {best['name']} cumplía los filtros pero no quedó fijado como pick "
                f"(partido ya jugado o cuota cambiada).")
    best = min((p for p, _ in rows), key=lambda p: (len(p["fails"]), -(p["model_prob"] or 0)))
    prob_ok = sum(1 for p, _ in rows if p["model_prob"] is not None and p["model_prob"] >= _MIN_MODEL_PROB)
    edge_ok = sum(1 for p, _ in rows if p["edge"] is not None and p["edge"] >= _MIN_EDGE)
    plural = lambda n, a, b: a if n == 1 else b  # noqa: E731
    price = f", cuota {best['price']:.2f}" if best.get("price") else ""
    return (f"{len(matches)} {plural(len(matches), 'partido', 'partidos')}: ningún jugador cumple a la vez probabilidad ≥ "
            f"{_MIN_MODEL_PROB * 100:.0f} % y ventaja ≥ {_MIN_EDGE * 100:.0f} % ({prob_ok} cumplen la probabilidad, "
            f"{edge_ok} la ventaja). Más cercano: {best['name']} (modelo {(best['model_prob'] or 0) * 100:.0f} %, ventaja "
            f"{(best['edge'] or 0) * 100:+.1f} %{price}), falla: {', '.join(best['fails'])}.")


def build_entry(matches: list[dict], pick: dict | None, source: str, note: str = "") -> dict:
    return {"source": source, "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "n_matches": len(matches), "pick": ({k: pick.get(k) for k in
                                                 ("player", "opponent", "model_prob", "edge", "best_price")} if pick else None),
            "matches": matches, "summary": _summary(matches, pick, note)}


def record(results: list[dict] | None, daily_pick: dict | None, error: str | None = None) -> None:
    """Llamado por generate_html.main() en cada pasada del pipeline: guarda el diagnóstico de HOY."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    diag = load()
    prev = diag["days"].get(today)
    if error:
        entry = build_entry([], None, "pipeline", note=f"El pipeline falló: {error[:200]}")
    else:
        matches = []
        for m in results or []:
            if "error" in m or not m.get("players"):
                continue
            players = [_player_row(p["player"], p.get("model_prob"), p.get("edge"),
                                   p.get("stake_price") or max((b["price"] for b in p.get("bookmakers", [])), default=None),
                                   p.get("signal")) for p in m["players"]]
            matches.append({"teams": f"{m['home']} vs {m['away']}", "time": m.get("commence_time"),
                            "players": players})
        entry = build_entry(matches, daily_pick, "pipeline")
    # No machacar un pick ya fijado antes hoy con una pasada posterior sin partidos (partidos ya empezados)
    if prev and prev.get("pick") and not entry["pick"]:
        entry["pick"], entry["summary"] = prev["pick"], prev["summary"]
        entry["matches"] = prev.get("matches", entry["matches"])
    diag["days"][today] = entry
    save(diag)


def parse_cards(page_html: str) -> list[dict]:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(page_html, "html.parser")
    matches = []
    for card in soup.select("div.match-card"):
        teams = card.select_one(".match-teams")
        if not teams:
            continue
        players = []
        for pc in card.select(".player-card"):
            name_el = pc.select_one(".player-name")
            name = name_el.get_text(" ", strip=True).split(" · ")[0].strip() if name_el else ""
            vals = [v.get_text(strip=True) for v in pc.select(".prob-val")]
            sp = pc.select_one(".stake-price")
            stats = [s.get_text(strip=True) for s in pc.select(".stat-value")]
            pill = pc.select_one(".signal-pill")

            def pct(s):
                m = re.search(r"-?\d+(?:\.\d+)?", s or "")
                return float(m.group()) / 100 if m else None
            sig = (pill.get_text(" ", strip=True).lower().replace(" ", "_") if pill else "")
            signal = "no_bet" if "no_bet" in sig else ("value_bet" if "value" in sig else "marginal" if "marginal" in sig else sig)
            price = float(sp.get_text(strip=True)) if sp and re.fullmatch(r"\d+(\.\d+)?", sp.get_text(strip=True)) else None
            players.append(_player_row(name, pct(vals[0]) if vals else None, pct(stats[0]) if stats else None, price, signal))
        t = card.select_one(".match-time")
        if len(players) < 2:  # tarjetas de MMA u otras
            continue
        matches.append({"teams": re.sub(r"\s+", " ", teams.get_text(" ", strip=True)),
                        "time": t.get_text(strip=True) if t else None, "players": players})
    return matches


def backfill() -> None:
    """Reconstruye cada día desde la última versión de data/site.enc de ese día en git (la web de entonces)."""
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    import private_crypto
    log = subprocess.run(["git", "log", "--format=%H %ad", "--date=format:%Y-%m-%d", "--", "data/site.enc"],
                         cwd=ROOT, capture_output=True, text=True, check=True).stdout.splitlines()
    last: dict[str, str] = {}
    for line in log:  # más reciente primero: nos quedamos con la primera de cada día
        h, d = line.split()
        last.setdefault(d, h)
    track = json.loads(TRACK.read_text(encoding="utf-8")) if TRACK.exists() else {"months": {}}
    diag = load()
    tmp = Path(tempfile.mkdtemp())
    for day, h in sorted(last.items()):
        if day < "2026-10-25" or (day in diag["days"] and diag["days"][day]["source"] == "pipeline"):
            continue
        enc = tmp / "s.enc"
        enc.write_bytes(subprocess.run(["git", "show", f"{h}:data/site.enc"], cwd=ROOT, capture_output=True, check=True).stdout)
        out = tmp / "s.html"
        private_crypto.decrypt_file(enc, out)
        matches = parse_cards(out.read_text(encoding="utf-8"))
        y, mo, d = day.split("-")
        tr = track.get("months", {}).get(f"{y}-{mo}", {}).get("days", {}).get(str(int(d)))
        pick = None
        if tr and tr.get("parlays") and len(tr["parlays"][0].get("legs", [])) == 1:
            p0 = tr["parlays"][0]
            pick = {"player": p0["legs"][0], "model_prob": p0.get("model_prob") or 0, "edge": p0.get("edge") or 0,
                    "best_price": p0.get("stake_odds") or p0.get("best_odds") or 0}
        e = build_entry(matches, pick, "reconstruido (web de ese día)")
        if pick:
            e["summary"] = f"Pick: {pick['player']} @ {pick['best_price']:.2f}."
        diag["days"][day] = e
        print(day, h[:7], len(matches), "partidos |", e["summary"][:140])
    # Días sin ninguna versión de la web en git: el pipeline no corrió.
    from datetime import date, timedelta
    d0, d1 = date(2026, 10, 25), datetime.now(timezone.utc).date() - timedelta(days=1)
    while d0 <= d1:
        k = d0.isoformat()
        if k not in diag["days"]:
            tr_day = track.get("months", {}).get(k[:7], {}).get("days", {}).get(str(d0.day))
            diag["days"][k] = {"source": "reconstruido", "updated": "", "n_matches": 0, "pick": None, "matches": [],
                               "summary": "El pipeline no se ejecutó este día (GitHub no lanzó el workflow programado); no hay datos de partidos."
                               if not tr_day else "Sin datos de partidos guardados."}
        d0 += timedelta(days=1)
    save(diag)


def _row_html(day: str, e: dict) -> str:
    pick = e.get("pick")
    badge = ('<span class="pill pill-green">PICK</span>' if pick else '<span class="pill pill-amber">SIN PICK</span>')
    return (f'<tr><td style="white-space:nowrap">{day[8:]}/{day[5:7]}</td><td>{badge}</td>'
            f'<td>{html.escape(e.get("summary", ""))}</td></tr>')


def diary_html() -> str:
    days = load().get("days", {})
    if not days:
        return ""
    rows = "".join(_row_html(d, days[d]) for d in sorted(days, reverse=True))
    return ('<section class="tennis-diary" style="margin:16px 0;padding:12px 14px;border:1px solid var(--border,#2a2f3a);'
            'border-radius:10px;"><h2 style="font-size:15px;margin:0 0 4px">Diario de picks de tenis</h2>'
            '<p style="font-size:12px;color:var(--muted);margin:0 0 8px">Cada día: si hubo pick y, si no, por qué. '
            f'Filtros: probabilidad ≥ {_MIN_MODEL_PROB * 100:.0f} %, ventaja ≥ {_MIN_EDGE * 100:.0f} %, cuota ≥ {_MIN_PRICE:.2f}.</p>'
            '<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;font-size:12px"><thead>'
            '<tr style="text-align:left;color:var(--muted)"><th>Día</th><th>Estado</th><th>Explicación</th></tr></thead>'
            f'<tbody>{rows}</tbody></table></div></section>')


def report(n: int = 14) -> None:
    days = load().get("days", {})
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    print("HOY", today, "->", days.get(today, {}).get("summary", "SIN ENTRADA (el pipeline no ha registrado hoy)"))
    for d in sorted(days, reverse=True)[:n]:
        print(d, "PICK" if days[d].get("pick") else "sin pick", "|", days[d].get("summary", "")[:200])


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", action="store_true")
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()
    if a.backfill:
        backfill()
    if a.report or not a.backfill:
        report()
