"""Build the private 'Combinadas' tab: the best combos of NBA and NFL together.

Blocks (from data/mix_picks.json, written by scripts/mix_combos.py):
  1. Mezcla NBA + NFL  - 3-leg combos that mix both sports (different games, so independent), chosen with the NBA engine
  2. Mejores de NBA    - the NBA tab's bettable combos
  3. Mejores de NFL    - the NFL tab's bettable combos
It reuses generate_nba.py (card HTML, CSS, the 'Apostada' tracker) loaded as a module with the labels/links made sport-aware,
so it is never a copy and follows any future change of the NBA tab.  Usage: python generate_combos.py [output]
"""

import json
import re
import sys
import types
from pathlib import Path

ROOT = Path(__file__).parent
MIX = ROOT / "data" / "mix_picks.json"

STAT_ES = '''STAT_ES = {
    "points": "Puntos", "rebounds": "Rebotes", "assists": "Asistencias", "threesmade": "Triples",
    "points+rebounds": "Pts + Reb", "points+assists": "Pts + Ast",
    "assists+rebounds": "Ast + Reb", "points+assists+rebounds": "Pts + Ast + Reb",
    "passing yards": "Yardas de pase", "passing attempts": "Pases intentados", "passing completions": "Pases completados",
    "passing touchdowns": "TD de pase", "interceptions": "Intercepciones", "rushing yards": "Yardas de carrera",
    "rushing attempts": "Acarreos", "receiving yards": "Yardas de recepción", "receptions": "Recepciones",
}'''
BASE_URL = {"nba": "https://stake.com/es/sports/basketball/usa/nba/", "nfl": "https://stake.com/es/sports/american-football/usa/nfl/"}
SPORT_TAG = {"nba": "NBA", "nfl": "NFL"}


def load() -> types.ModuleType:
    src = (ROOT / "generate_nba.py").read_text(encoding="utf-8")
    src, n = re.subn(r"STAT_ES = \{.*?\n\}", STAT_ES, src, count=1, flags=re.S)
    assert n == 1, "STAT_ES block not found in generate_nba.py"
    assert "nba_tracker_v1" in src
    src = src.replace("nba_tracker_v1", "mix_tracker_v1")
    mod = types.ModuleType("generate_combos_impl")
    mod.__file__ = str(ROOT / "generate_nba.py")
    exec(compile(src, "generate_combos_impl", "exec"), mod.__dict__)
    mod.stake_url = lambda legs: None  # the Combo Loader extension is basketball only
    mod.game_url = lambda leg: BASE_URL.get(leg.get("sport", "nba"), BASE_URL["nba"]) + leg["fixture"] if leg.get("fixture") else BASE_URL["nba"]
    return mod


def _section(mod: types.ModuleType, combos: list[dict], title: str, sub: str) -> str:
    cards = mod._combos_html({"combos": combos}, tracking=False)
    if not combos:
        return f'<h2 class="sec">{title}</h2><p class="note">{sub} Ahora mismo no hay ninguna que cumpla las reglas (se ocultan las que tienen algún partido ya empezado).</p>'
    cards = re.sub(r'<h2 class="sec">.*?</h2>', f'<h2 class="sec">{title}</h2>', cards, count=1, flags=re.S)
    cards = re.sub(r'<p class="note" style="margin-top:0">.*?</p>', f'<p class="note" style="margin-top:0">{sub}</p>', cards, count=1, flags=re.S)
    return cards


def build(doc: dict) -> str:
    mod = load()
    dummy = {"picks": [], "combos": [], "combos_tracking": [], "timestamp": doc["timestamp"], "analysis": None}
    base = mod.build(dummy)
    css = re.search(r"<style>(.*?)</style>", base, re.S).group(1)
    js = "</script>\n<script>".join(re.findall(r"<script>(.*?)</script>", base, re.S)[-2:])   # tracker + "ya empezó" marker, as separate scripts
    bankroll = re.search(r'<div class="card bk">.*?</div>', base, re.S).group(0)   # the tracker script needs these fields
    track = base[base.index('<h2 class="sec">Mis apuestas'):base.index("</main>")]
    from datetime import datetime
    stamp = datetime.fromisoformat(doc["timestamp"]).astimezone()
    mixed = _section(mod, doc.get("mixed", []), "Mezcla NBA + NFL · 3 piernas",
                     "Tres piernas de partidos distintos, mezclando las dos ligas, elegidas con las mismas reglas que las de NBA (Win% de 54 % o más, EV positivo, un jugador una vez, "
                     "máximo 2 piernas por partido): al ser partidos distintos son independientes. Las piernas de NFL usan solo Pinnacle como casa de referencia (fase de prueba).")
    nba = _section(mod, doc.get("nba", []), "Mejores de NBA", "Las combinadas apostables de la pestaña NBA.")
    nfl = _section(mod, doc.get("nfl", []), "Mejores de NFL", "Las combinadas apostables de la pestaña NFL (fase de prueba).")
    return f"""<title>Combinadas</title>
<meta name="robots" content="noindex,nofollow">
<style>{css}</style>
<main>
<h1>Combinadas · NBA + NFL</h1>
<p class="sub">Las mejores combinadas de las dos ligas · mismo método que la pestaña NBA · actualizado {stamp:%d/%m %H:%M}</p>
{bankroll}
{mixed}
{nba}
{nfl}
{track}
</main>
<script>{js}</script>
"""


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "build" / "combos_src.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(json.loads(MIX.read_text(encoding="utf-8"))), encoding="utf-8")
    print(f"Written {out}")


if __name__ == "__main__":
    main()
