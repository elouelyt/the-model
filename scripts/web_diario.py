#!/usr/bin/env python3
"""Diario de estado de la web: cada día, por sección, si funciona y, si no hay picks, por qué.

Escribe data/web_diario.json (solo recuentos, horas y motivos; sin nombres de jugadores ni cuotas) y genera el
bloque «Estado diario de la web» de la pestaña Recomendaciones. Lo ejecuta la tarea de las 10:00.
  python scripts/web_diario.py          # comprueba y guarda HOY
  python scripts/web_diario.py --show   # imprime los últimos días
"""

import html
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
OUT = ROOT / "data" / "web_diario.json"
OK, WARN, FAIL = "ok", "aviso", "fallo"


def _json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _age_h(ts: str | None, now: datetime) -> float | None:
    try:
        return (now - datetime.fromisoformat(ts.replace("Z", "+00:00"))).total_seconds() / 3600
    except Exception:
        return None


def _combos_section(name: str, d: dict | None, now: datetime, max_age: float) -> dict:
    if not d:
        return {"estado": FAIL, "nota": f"{name}: no se pudo leer el fichero de picks."}
    age = _age_h(d.get("timestamp"), now)
    n_bet = len(d.get("combos") or [])
    n_track = len(d.get("combos_tracking") or [])
    n_legs = len(d.get("picks") or [])
    edad = f"actualizado hace {age:.0f} h" if age is not None else "sin hora"
    if age is None or age > max_age:
        return {"estado": FAIL, "nota": f"{name}: datos caducados ({edad}); las tandas deberían refrescarlos."}
    if n_bet:
        return {"estado": OK, "nota": f"{name}: {n_bet} combinada(s) apostable(s), {n_track} en seguimiento, {n_legs} piernas con valor ({edad})."}
    why = ("no hay piernas con valor positivo" if n_legs == 0 else
           f"hay {n_legs} piernas con valor pero ninguna combinación supera los filtros de probabilidad y EV")
    return {"estado": WARN, "nota": f"{name}: 0 combinadas apostables — {why}; {n_track} en seguimiento ({edad})."}


def _tenis(now: datetime) -> dict:
    import tennis_audit
    diag = tennis_audit.load()["days"].get(now.strftime("%Y-%m-%d"))
    if not diag:
        return {"estado": FAIL, "nota": "Tenis: el pipeline diario no ha registrado hoy (no se ejecutó o falló)."}
    return {"estado": OK if diag.get("pick") else WARN, "nota": "Tenis: " + diag["summary"]}


def _github() -> dict:
    try:
        out = subprocess.run(["gh", "run", "list", "--workflow=daily.yml", "--limit", "5", "--json", "conclusion,createdAt"],
                             cwd=ROOT, capture_output=True, text=True, timeout=60).stdout
        runs = json.loads(out)
        bad = [r for r in runs if r["conclusion"] not in ("success", "cancelled", "")]
        if bad:
            return {"estado": WARN, "nota": f"GitHub: {len(bad)} de los últimos 5 workflows diarios fallaron."}
        return {"estado": OK, "nota": f"GitHub: últimos {len(runs)} workflows diarios correctos."}
    except Exception as exc:
        return {"estado": WARN, "nota": f"GitHub: no se pudo consultar ({exc})."}


def check(now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    s: dict[str, dict] = {}
    s["Tenis"] = _tenis(now)
    s["NBA"] = _combos_section("NBA", _json(ROOT / "data" / "nba_picks.json"), now, 20)
    nfl = _combos_section("NFL", _json(ROOT / "nfl" / "data" / "nfl_picks.json"), now, 20)
    if nfl["estado"] == WARN and now.weekday() in (1, 2, 4, 5):  # mar, mié, vie, sáb
        nfl["nota"] += " Hoy no es día habitual de partidos NFL (jue/dom/lun)."
    s["NFL"] = nfl

    mix = _json(ROOT / "data" / "mix_picks.json")
    if mix:
        age = _age_h(mix.get("timestamp"), now)
        n = len(mix.get("mixed") or []) + len(mix.get("nba") or []) + len(mix.get("nfl") or [])
        if age is None or age > 20:
            s["Mezcla"] = {"estado": FAIL, "nota": "Mezcla: datos caducados."}
        else:
            s["Mezcla"] = {"estado": OK if n else WARN,
                           "nota": f"Mezcla: {n} combinadas ({age:.0f} h)." + ("" if n else " Ninguna supera los filtros hoy.")}
    else:
        s["Mezcla"] = {"estado": FAIL, "nota": "Mezcla: no se pudo leer mix_picks.json."}

    jev = _json(ROOT / "data" / "jev_picks.json")
    if jev:
        n = sum(len(jev.get(k) or []) for k in ("nba", "nfl", "total"))
        age = _age_h(jev.get("timestamp"), now)
        s["Jev"] = {"estado": FAIL if age is None or age > 20 else (OK if n else WARN),
                    "nota": f"Jev: {n} combinadas ({age:.0f} h)." if age is not None else "Jev: sin hora."}

    mma = _json(ROOT / "data" / "mma_picks.json")
    if mma:
        age = _age_h(mma.get("timestamp"), now)
        s["MMA"] = {"estado": FAIL if age is None or age > 20 else OK,
                    "nota": f"MMA: datos de hace {age:.0f} h." if age is not None else "MMA: sin hora."}

    res = _json(ROOT / "data" / "results.json")
    if res:
        age = _age_h(res.get("timestamp"), now)
        s["Resultados"] = {"estado": FAIL if age is None or age > 30 else OK,
                           "nota": f"Resultados: liquidados hace {age:.0f} h." if age is not None else "Resultados: sin hora."}

    bets = _json(ROOT / "nuevas_ideas" / "data" / "real_bets.json") or []
    if bets:
        last = max(b["day"] for b in bets)
        s["Apuestas reales"] = {"estado": OK, "nota": f"Tus apuestas registradas: {len(bets)}; la última fue el {last}."}

    s["GitHub"] = _github()
    return s


def load() -> dict:
    return _json(OUT) or {"days": {}}


def save_today() -> dict:
    now = datetime.now(timezone.utc)
    data = load()
    data["days"][now.strftime("%Y-%m-%d")] = {"hora": now.strftime("%H:%M UTC"), "secciones": check(now)}
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    return data


def diary_html(max_days: int = 14) -> str:
    days = load().get("days", {})
    if not days:
        return ""
    color = {OK: "#10b981", WARN: "#f59e0b", FAIL: "#ef4444"}
    rows = ""
    for d in sorted(days, reverse=True)[:max_days]:
        cells = "".join(
            f'<div style="margin:2px 0"><span style="color:{color[v["estado"]]}">●</span> {html.escape(v["nota"])}</div>'
            for v in days[d]["secciones"].values())
        rows += (f'<tr><td style="white-space:nowrap;vertical-align:top;padding:4px 8px 4px 0">{d[8:]}/{d[5:7]}<br>'
                 f'<span style="color:var(--muted)">{days[d]["hora"]}</span></td><td>{cells}</td></tr>')
    return ('<section style="margin:16px 0;padding:12px 14px;border:1px solid var(--border,#2a2f3a);border-radius:10px;">'
            '<h2 style="font-size:15px;margin:0 0 4px">Estado diario de la web</h2>'
            '<p style="font-size:12px;color:var(--muted);margin:0 0 8px">Revisión a las 10:00, 16:00 y 22:00 (se muestra la última): qué funciona, qué no y por qué no hay picks. '
            'Verde = bien · ámbar = sin picks o aviso · rojo = fallo.</p>'
            f'<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;font-size:12px"><tbody>{rows}</tbody></table></div></section>')


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if "--show" in sys.argv:
        for d, v in sorted(load()["days"].items(), reverse=True)[:5]:
            print(d, v["hora"])
            for k, x in v["secciones"].items():
                print("  ", x["estado"].upper(), "|", x["nota"][:230])
    else:
        save_today()
        for k, x in load()["days"][datetime.now(timezone.utc).strftime("%Y-%m-%d")]["secciones"].items():
            print(x["estado"].upper(), "|", x["nota"][:260])
