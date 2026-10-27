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
    rows = [[date_es(d), str(m["placed"]), str(m["won"]), pct(m["won"] / m["placed"]), units(m["profit"]), pct(m["roi"], True)]
            for d, m in sorted(mine.items(), reverse=True)]
    n = sum(m["placed"] for m in mine.values())
    w = sum(m["won"] for m in mine.values())
    p = sum(m["profit"] for m in mine.values())
    if len(mine) > 1:
        rows.append(["<b>Total</b>", f"<b>{n}</b>", f"<b>{w}</b>", f"<b>{pct(w / n)}</b>", f"<b>{units(p)}</b>", f"<b>{pct(p / n, True)}</b>"])
    detail = "".join(
        f'<details><summary>{date_es(d)}: combinadas ganadas ({len(m["winners"])})</summary>' + "".join(
            f'<p>{w2["odds"]:.2f} · ' + " · ".join(escape(x) for x in w2["legs"]) +
            (f'<br><span class="note">{escape(w2["note"])}</span>' if w2["note"] else "") + "</p>" for w2 in m["winners"]) + "</details>"
        for d, m in sorted(mine.items(), reverse=True))
    return ("<h2>Mis apuestas reales en Stake</h2>" + table(["Día", "Apostadas", "Ganadas", "Acierto", "Resultado (1 u c/u)", "ROI"], rows) + detail +
            '<p class="note">Datos pegados a mano desde «Mis Apuestas» de Stake: solo las combinadas que apostaste, con la cuota que te dio Stake '
            "(suele ser algo más baja que la del panel). Las perdidas se cuentan sin detalle.</p>")


def all_section(doc: dict) -> str:
    """Everything the model recommends, NBA + NFL + mixed, day by day (without the 23/10 old-rules day): combos you can bet,
    paper combos, and every single leg as a flat 1 u bet."""
    days: dict[str, dict] = {}
    for key in ("NBA", "NFL", "Mezcla"):
        for d in (doc.get(key) or {}).get("days", []):
            if d["baseline"]:
                continue
            r = days.setdefault(d["date"], dict(bn=0, bw=0, bp=0.0, tn=0, tw=0, tp=0.0, ln=0, lp=0.0, sn=0, sp=0.0))
            r["bn"] += d["bettable"]["n"]; r["bw"] += d["bettable"]["won"]; r["bp"] += d["bettable"]["profit"]
            r["tn"] += d["tracking"]["n"]; r["tw"] += d["tracking"]["won"]; r["tp"] += d["tracking"]["profit"]
            if d["legs"].get("n"):
                r["ln"] += d["legs"]["n"]; r["lp"] += d["legs"]["n"] * d["legs"]["roi"]
            if d["legs54"].get("n"):
                r["sn"] += d["legs54"]["n"]; r["sp"] += d["legs54"]["n"] * d["legs54"]["roi"]
    if not days:
        return ""
    tot = {k: sum(r[k] for r in days.values()) for k in next(iter(days.values()))}

    def line(label: str, r: dict) -> list[str]:
        return [label, f'{r["bw"]}/{r["bn"]}', units(r["bp"]), f'{r["tw"]}/{r["tn"]}', units(r["tp"]),
                f'{r["sn"]}', units(r["sp"]), f'{r["ln"]}', units(r["lp"])]

    rows = [line(date_es(dt), r) for dt, r in sorted(days.items(), reverse=True)]
    rows.append(line("<b>Total</b>", tot))
    return ("<h2>Todas las apuestas del modelo (NBA + NFL + mezcla)</h2>" + table(
        ["Día", "Combinadas apostables", "Resultado", "Combinadas en papel", "Resultado", "Piernas Win ≥ 54 %", "1 u c/u", "Todas las piernas", "1 u c/u"], rows) +
        '<p class="note">Cada pierna cuenta como una apuesta simple de 1 u con la cuota guardada. Las combinadas de NBA, NFL y mezcla comparten piernas: '
        "no se pueden sumar como si fueran apuestas independientes.</p>")


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
    body = (head + f'<div class="tiles">{"".join(tiles)}</div>' + notes + all_section(doc) + mine_section(mine) + sport_section("NBA", nba) + sport_section("NFL", nfl) +
            sport_section(MIX, mix, "Las mezcladas repiten piernas de las combinadas de NBA y NFL: no suman como resultados independientes."))
    return (f'<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<style>{CSS}</style></head><body><main>{body}</main></body></html>")
