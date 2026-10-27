"""Build the 'Resultados' tab of the private panel: how the picks and combos are doing, day by day (NBA, NFL, mixed, and the user's own bets).

Input: the dict written by scripts/results_data.py (data/results.json). Plain HTML, same look as the other tabs; the panel encrypts it.
"""

from html import escape

MONTHS = ["", "ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
MIX = "Combinadas mezcla NBA+NFL"
CSS = """
:root{--bg:#080808;--surface:#111;--border:#242424;--text:#ececec;--muted:#8a8a8a;--accent:#f97316;--good:#34d399;--bad:#f87171}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;padding:16px}
main{max-width:980px;margin:0 auto}h1{font-size:22px;margin:0 0 4px}h2{font-size:17px;margin:28px 0 8px}
.sub{color:var(--muted);font-size:13px;margin:0 0 16px}.note{color:var(--muted);font-size:12.5px;margin:6px 0 0}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px}
.tile{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:12px 14px}
.tile .k{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.06em}.tile .v{font-size:24px;font-weight:650;font-variant-numeric:tabular-nums}
.tile .d{color:var(--muted);font-size:12.5px}
.wrap{overflow-x:auto;border:1px solid var(--border);border-radius:8px}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums;font-size:14px}
th,td{padding:7px 10px;text-align:right;border-bottom:1px solid var(--border);white-space:nowrap}th:first-child,td:first-child{text-align:left}
th{color:var(--muted);font-weight:500;font-size:12px;background:var(--surface)}tr:last-child td{border-bottom:0}
.pos{color:var(--good)}.neg{color:var(--bad)}.mut{color:var(--muted)}.tag{font-size:11px;color:var(--accent);border:1px solid var(--accent);border-radius:4px;padding:0 5px;margin-left:6px}
.read{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:4px 16px}.read p{margin:10px 0}h3{font-size:14px;color:var(--muted);margin:16px 0 6px;font-weight:500}
details{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:8px 12px;margin-top:8px}summary{cursor:pointer}
"""


def date_es(iso: str) -> str:
    _, m, d = iso.split("-")
    return f"{int(d)} {MONTHS[int(m)]}"


def pct(x, signed: bool = False) -> str:
    if x is None:
        return "–"
    return f"{x * 100:+.0f} %" if signed else f"{x * 100:.0f} %"


def cls(x) -> str:
    return "mut" if x is None or abs(x) < 1e-9 else ("pos" if x > 0 else "neg")


def units(x) -> str:
    return f'<span class="{cls(x)}">{x:+.1f} u</span>' if x is not None else "–"


def tile(k: str, v: str, d: str = "") -> str:
    return f'<div class="tile"><div class="k">{escape(k)}</div><div class="v">{v}</div><div class="d">{d}</div></div>'


def combos_cell(s: dict) -> str:
    return "–" if not s or not s["n"] else f'{s["won"]}/{s["n"]}'


def table(head: list[str], rows: list[list[str]]) -> str:
    th = "".join(f"<th>{h}</th>" for h in head)
    tr = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<div class="wrap"><table><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table></div>'


def sport_section(name: str, b: dict | None, legs_note: str = "") -> str:
    if not b:
        return ""
    rows = []
    for d in reversed(b["days"]):
        bt, tr, lg, l54 = d["bettable"], d["tracking"], d["legs"], d["legs54"]
        tag = '<span class="tag">reglas antiguas</span>' if d["baseline"] else ""
        row = [date_es(d["date"]) + tag, combos_cell(bt), units(bt["profit"]) if bt["n"] else "–",
               combos_cell(tr), units(tr["profit"]) if tr["n"] else "–"]
        if name != MIX:
            row += [f'{pct(lg["hit"])} <span class="mut">({pct(lg["expected"])})</span>' if lg.get("n") else "–",
                    f'{pct(l54["hit"])} <span class="mut">({pct(l54["expected"])})</span>' if l54.get("n") else "–"]
        rows.append(row)
    head = ["Día", "Apostables", "Resultado", "Seguimiento", "Resultado"] + ([] if name == MIX else ["Piernas: acierto (esperado)", "Piernas ≥ 54 %"])
    out = [f"<h2>{name}</h2>"]
    if rows:
        out.append(table(head, rows))
    if b["families"]:
        out.append("<details><summary>Por familia de combinada (desde el 24/10)</summary>" + table(
            ["Familia", "Combinadas", "Ganadas", "Resultado (1 u c/u)"],
            [[f["name"], str(f["n"]), str(f["won"]), units(f["profit"])] for f in b["families"]]) + "</details>")
    if b["by_stat"]:
        out.append("<details><summary>Piernas por mercado y lado (desde el 24/10)</summary>" + table(
            ["Mercado / lado", "Piernas", "Acierto", "Esperado", "ROI plano"],
            [[r["name"], str(r["n"]), pct(r["hit"]), pct(r["expected"]), f'<span class="{cls(r["roi"])}">{pct(r["roi"], True)}</span>']
             for r in b["by_stat"] + b["by_side"]]) + "</details>")
    if legs_note:
        out.append(f'<p class="note">{legs_note}</p>')
    return "".join(out)


def mine_section(mine: dict) -> str:
    if not mine:
        return ""
    rows = [[date_es(d), str(m["placed"]), str(m["won"]), pct(m["won"] / m["placed"]) if m["placed"] else "–", units(m["profit"]),
             pct(m["roi"], True) if m["placed"] else "–"] + ([str(m["pending"])] if any(x.get("pending") for x in mine.values()) else [])
            for d, m in sorted(mine.items(), reverse=True)]
    n = sum(m["placed"] for m in mine.values())
    w = sum(m["won"] for m in mine.values())
    p = sum(m["profit"] for m in mine.values())
    show_pending = any(x.get("pending") for x in mine.values())
    if len(mine) > 1 and n:
        rows.append(["<b>Total</b>", f"<b>{n}</b>", f"<b>{w}</b>", f"<b>{pct(w / n)}</b>", f"<b>{units(p)}</b>", f"<b>{pct(p / n, True)}</b>"] + (["" ] if show_pending else []))

    def bet_line(b: dict) -> str:
        mark = {"won": "✓", "lost": "✗", "void": "·"}.get(b.get("status"), "…")
        return f'<p>{mark} {b["odds"]:.2f} · ' + " · ".join(escape(x) for x in b["legs"]) + "</p>"

    detail = ""
    for d, m in sorted(mine.items(), reverse=True):
        if m.get("all"):
            detail += f'<details><summary>{date_es(d)}: todas las apuestas registradas ({len(m["all"])})</summary>' + "".join(bet_line(b) for b in m["all"]) + "</details>"
        else:
            detail += f'<details><summary>{date_es(d)}: combinadas ganadas ({len(m["winners"])})</summary>' + "".join(
                f'<p>{w2["odds"]:.2f} · ' + " · ".join(escape(x) for x in w2["legs"]) +
                (f'<br><span class="note">{escape(w2["note"])}</span>' if w2["note"] else "") + "</p>" for w2 in m["winners"]) + "</details>"
    head = ["Día", "Apostadas", "Ganadas", "Acierto", "Resultado (1 u c/u)", "ROI"] + (["Pendientes"] if show_pending else [])
    return ("<h2>Mis apuestas reales en Stake</h2>" + table(head, rows) + detail +
            '<p class="note">Las apuestas que haces en Stake: las registradas por la extensión llevan la cuota que te dio Stake y todas las piernas; '
            "las anteriores (25/10) se pegaron a mano y las perdidas no tienen detalle.</p>")


STAT_ES = {"assists": "asistencias", "rebounds": "rebotes", "points": "puntos", "receptions": "recepciones", "assists+rebounds": "asist.+rebotes",
           "passing touchdowns": "TD de pase", "interceptions": "intercepciones", "rushing yards": "yardas de carrera",
           "receiving yards": "yardas de recepción", "passing yards": "yardas de pase", "passing attempts": "pases intentados",
           "passing completions": "pases completados", "rushing attempts": "acarreos"}


def current_days(doc: dict) -> dict[str, dict]:
    """Per day, summed over NBA + NFL + mixed (the 23/10 old-rules day is left out)."""
    days: dict[str, dict] = {}
    for key in ("NBA", "NFL", "Mezcla"):
        for d in (doc.get(key) or {}).get("days", []):
            if d["baseline"]:
                continue
            r = days.setdefault(d["date"], dict(bn=0, bw=0, bp=0.0, tn=0, tw=0, tp=0.0, ln=0, lp=0.0, sn=0, sp=0.0, sh=0.0, se=0.0))
            r["bn"] += d["bettable"]["n"]; r["bw"] += d["bettable"]["won"]; r["bp"] += d["bettable"]["profit"]
            r["tn"] += d["tracking"]["n"]; r["tw"] += d["tracking"]["won"]; r["tp"] += d["tracking"]["profit"]
            if d["legs"].get("n"):
                r["ln"] += d["legs"]["n"]; r["lp"] += d["legs"]["n"] * d["legs"]["roi"]
            if d["legs54"].get("n"):
                n = d["legs54"]["n"]
                r["sn"] += n; r["sp"] += n * d["legs54"]["roi"]; r["sh"] += n * d["legs54"]["hit"]; r["se"] += n * d["legs54"]["expected"]
    return days


def totals(days: dict) -> dict:
    return {k: sum(r[k] for r in days.values()) for k in next(iter(days.values()))} if days else {}


def conclusions(doc: dict) -> str:
    days = current_days(doc)
    if not days:
        return ""
    t = totals(days)
    nd = len(days)
    out = []
    if t["bn"]:
        out.append(f'<b>Combinadas que se apuestan:</b> {t["bw"]} de {t["bn"]} ganadas ({t["bw"] / t["bn"] * 100:.0f} %), {units(t["bp"])}. '
                   "Con cuotas de 5 a 7 basta acertar entre 1 de cada 5 y 1 de cada 7 para no perder, así que el resultado es "
                   + ("bueno por ahora." if t["bp"] > 0 else "malo por ahora."))
    if t["sn"]:
        hit, exp = t["sh"] / t["sn"], t["se"] / t["sn"]
        out.append(f'<b>Piernas elegidas (Win ≥ 54 %):</b> aciertan {hit * 100:.0f} % frente a {exp * 100:.0f} % esperado y dan {units(t["sp"])} como apuestas sueltas. '
                   f'Por deporte: ' + ", ".join(f'{k} {units(doc[k]["legs54_total"]["n"] * doc[k]["legs54_total"]["roi"])}' for k in ("NBA", "NFL") if doc.get(k) and doc[k]["legs54_total"].get("n")) +
                   f'. Sin ese filtro (todas las piernas) el resultado es {units(t["lp"])}: el filtro hace su trabajo.')
    watch, good = [], []
    for sp in ("NBA", "NFL"):
        b = doc.get(sp) or {}
        for r in b.get("by_stat54", []) + b.get("by_side54", []):
            if r["n"] < 30:
                continue
            diff = r["hit"] - r["expected"]
            label = f'{sp} {STAT_ES.get(r["name"], r["name"])} ({r["n"]} piernas, {pct(r["hit"])} frente a {pct(r["expected"])})'
            if diff <= -0.04:
                watch.append(label)
            elif diff >= 0.05:
                good.append(label)
    if watch:
        out.append("<b>A vigilar (acierto por debajo de lo esperado):</b> " + "; ".join(watch) + ". Todavía no son suficientes piernas para descartarlos.")
    if good:
        out.append("<b>Funcionando bien por ahora:</b> " + "; ".join(good) + ". El NFL sale de pocos días: no me fío de él todavía.")
    out.append(f'<b>Qué haría:</b> hay solo {nd} día{"s" if nd != 1 else ""} de datos' +
               (" y pocas combinadas, " if t["bn"] < 60 else ", ") +
               ("así que no cambiaría ninguna regla todavía: " if nd < 7 else "") +
               "seguir apostando con las reglas actuales y revisar en una semana mercado por mercado. Cualquier cambio se prueba antes en papel durante 5-7 días.")
    return '<h2>Mi lectura</h2><div class="read">' + "".join(f"<p>{x}</p>" for x in out) + "</div>"


def combos_section(doc: dict) -> str:
    days = current_days(doc)
    if not days:
        return ""
    rows = []
    for dt, r in sorted(days.items(), reverse=True):
        rows.append([date_es(dt), f'{r["bw"]}/{r["bn"]}', units(r["bp"]) if r["bn"] else "–", f'{r["tw"]}/{r["tn"]}', units(r["tp"]) if r["tn"] else "–"])
    t = totals(days)
    rows.append(["<b>Total</b>", f'<b>{t["bw"]}/{t["bn"]}</b>', units(t["bp"]), f'<b>{t["tw"]}/{t["tn"]}</b>', units(t["tp"])])
    by_sport = []
    for key in ("NBA", "NFL", "Mezcla"):
        b = doc.get(key)
        if b:
            bt, tr = b["bettable_total"], b.get("tracking_total") or {"n": 0, "won": 0, "profit": 0}
            by_sport.append([key, combos_cell(bt), units(bt["profit"]) if bt["n"] else "–", combos_cell(tr), units(tr["profit"]) if tr["n"] else "–"])
    head = ["Apostables (ganadas)", "Resultado", "En papel (ganadas)", "Resultado"]
    return ("<h2>Combinadas</h2>" + table(["Día"] + head, rows) + "<h3>Por deporte, desde el 24/10</h3>" + table(["Deporte"] + head, by_sport) +
            '<p class="note">1 u por combinada, cuota guardada al publicarla. «Apostables» son las del panel con partidos sin empezar; «en papel» incluyen partidos ya '
            "empezados o reglas alternativas y no se apuestan. Las combinadas de NBA, NFL y mezcla comparten piernas: no son independientes.</p>")


def singles_section(doc: dict) -> str:
    days = current_days(doc)
    if not days:
        return ""
    rows = []
    for dt, r in sorted(days.items(), reverse=True):
        rows.append([date_es(dt), str(r["sn"]), pct(r["sh"] / r["sn"]) if r["sn"] else "–", units(r["sp"]) if r["sn"] else "–", str(r["ln"]), units(r["lp"]) if r["ln"] else "–"])
    t = totals(days)
    rows.append(["<b>Total</b>", f'<b>{t["sn"]}</b>', f'<b>{pct(t["sh"] / t["sn"])}</b>', units(t["sp"]), f'<b>{t["ln"]}</b>', units(t["lp"])])
    out = ["<h2>Apuestas sueltas (piernas una a una)</h2>",
           table(["Día", "Piernas Win ≥ 54 %", "Acierto", "1 u c/u", "Todas las piernas", "1 u c/u"], rows)]
    for sp in ("NBA", "NFL"):
        b = doc.get(sp) or {}
        mk = b.get("by_stat54", []) + b.get("by_side54", [])
        if mk:
            out.append(f"<details><summary>{sp}: por mercado y lado (solo piernas Win ≥ 54 %)</summary>" + table(
                ["Mercado / lado", "Piernas", "Acierto", "Esperado", "ROI plano"],
                [[escape(STAT_ES.get(r["name"], r["name"])), str(r["n"]), pct(r["hit"]), pct(r["expected"]),
                  f'<span class="{cls(r["roi"])}">{pct(r["roi"], True)}</span>'] for r in mk]) + "</details>")
    out.append('<p class="note">Cada pierna cuenta como una apuesta simple de 1 u con la cuota guardada. «Win ≥ 54 %» son las piernas que el modelo usa para armar combinadas.</p>')
    return "".join(out)


def build(doc: dict) -> str:
    nba, nfl, mix = doc.get("NBA"), doc.get("NFL"), doc.get("Mezcla")
    tiles = []
    for label, b in (("NBA", nba), ("NFL", nfl), ("Mezcla", mix)):
        if b and b["bettable_total"]["n"]:
            t = b["bettable_total"]
            tiles.append(tile(f"{label}: combinadas apostables", f'{t["won"]}/{t["n"]}', f'{units(t["profit"])} · ROI {pct(t["roi"], True)} (1 u c/u)'))
    mine = doc.get("mine", {})
    if mine:
        n = sum(m["placed"] for m in mine.values())
        w = sum(m["won"] for m in mine.values())
        p = sum(m["profit"] for m in mine.values())
        tiles.append(tile("Mis apuestas reales", f"{w}/{n}", f"{units(p)} · ROI {pct(p / n, True)}"))
    for label, b in (("NBA", nba), ("NFL", nfl)):
        if b and b["legs54_total"].get("n"):
            t = b["legs54_total"]
            tiles.append(tile(f"{label}: piernas con Win ≥ 54 %", pct(t["hit"]), f'esperado {pct(t["expected"])} · {t["n"]} piernas'))
    head = ('<h1>Resultados</h1><p class="sub">Qué tal van las recomendaciones, liquidadas con los marcadores reales de ESPN. '
            f'Actualizado {escape(doc["timestamp"][:16].replace("T", " "))} UTC.</p>')
    notes = ('<p class="note">«Apostables» son las combinadas que el panel marca como apostables (partidos sin empezar); «Seguimiento» son pruebas en papel '
             "(incluyen partidos ya empezados o reglas alternativas) y no se apuestan. Resultado en unidades, con 1 u por combinada y la cuota guardada al "
             "publicarla; una pierna anulada se quita de la combinada. El 23/10 se jugó con las reglas antiguas: se muestra aparte y no entra en los totales. "
             "Son pocos días: una racha buena o mala no demuestra nada todavía.</p>")
    body = (head + f'<div class="tiles">{"".join(tiles)}</div>' + notes + conclusions(doc) + combos_section(doc) + singles_section(doc) + mine_section(mine) +
            "<h2>Detalle por deporte</h2>" + sport_section("NBA", nba) + sport_section("NFL", nfl) +
            sport_section(MIX, mix, "Las mezcladas repiten piernas de las combinadas de NBA y NFL: no suman como resultados independientes."))
    return (f'<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<style>{CSS}</style></head><body><main>{body}</main></body></html>")
