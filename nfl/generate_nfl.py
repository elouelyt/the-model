"""Build the private NFL value-bets tab: the NBA generator (generate_nba.py) with the sport-specific parts swapped.

generate_nba.py is not modified: its source is loaded, a few constants/labels are replaced (stat names, tracker key,
Stake URL, titles) and it is executed as a separate module, so improvements to the NBA tab reach NFL automatically.
The extension link ('Rellenar talón') is disabled for NFL (the loader writes basketball slips).

Usage: python nfl/generate_nfl.py [output]   (reads nfl/data/nfl_picks.json)   or   import generate_nfl; generate_nfl.build(doc)
"""

import json
import re
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PICKS = ROOT / "nfl" / "data" / "nfl_picks.json"

NFL_STAT_ES = '''STAT_ES = {
    "passing yards": "Yardas de pase", "passing attempts": "Pases intentados", "passing completions": "Pases completados",
    "passing touchdowns": "TD de pase", "interceptions": "Intercepciones", "rushing yards": "Yardas de carrera",
    "rushing attempts": "Acarreos", "receiving yards": "Yardas de recepción", "receptions": "Recepciones",
}'''


def load() -> types.ModuleType:
    src = (ROOT / "generate_nba.py").read_text(encoding="utf-8")
    src, n = re.subn(r"STAT_ES = \{.*?\n\}", NFL_STAT_ES, src, count=1, flags=re.S)
    assert n == 1, "STAT_ES block not found in generate_nba.py"
    for old, new in (
        ("nba_tracker_v1", "nfl_tracker_v1"),
        ('"https://stake.com/es/sports/basketball"', '"https://stake.com/es/sports/american-football"'),
        ("/usa/nba/", "/usa/nfl/"),
        ("<title>NBA</title>", "<title>NFL</title>"),
        ("<h1>NBA · apuestas a jugadores con valor</h1>", "<h1>NFL · apuestas a jugadores con valor</h1>"),
        ("(FanDuel y Pinnacle, sin margen)", "(Pinnacle, sin margen)"),
        ("{warn}\n{combos_html}",
         "{warn}\n<p class=\"warn\">NFL en fase de prueba (desde el 25/10): solo Pinnacle como casa de referencia. Las jugadas con EV muy alto suelen ser ruido "
         "(en NBA las Under de valor con probabilidad &lt; 54 % fallaron mucho): fíate más de las combinadas con piernas de Win% de 54 % o más.</p>\n{combos_html}"),
    ):
        assert old in src, f"expected text not found in generate_nba.py: {old}"
        src = src.replace(old, new)
    mod = types.ModuleType("generate_nfl_impl")
    mod.__file__ = str(ROOT / "generate_nba.py")
    exec(compile(src, "generate_nfl_impl", "exec"), mod.__dict__)
    mod.stake_url = lambda legs: None  # the Stake Combo Loader extension fills basketball slips only
    return mod


def build(doc: dict) -> str:
    return load().build(doc)


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "build" / "nfl_src.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(json.loads(PICKS.read_text(encoding="utf-8"))), encoding="utf-8")
    print(f"Written {out}")


if __name__ == "__main__":
    main()
