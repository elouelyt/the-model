"""Parse manually pasted Stake odds data and merge into stake_cache.json."""
import sys, json, re
from datetime import datetime, timezone
from pathlib import Path
from difflib import SequenceMatcher

sys.path.insert(0, r"C:\Users\ojiyo\Desktop\tennis\tennis-ai-data-platform-main\tennis-ai-data-platform-main")

CACHE_PATH = Path(r"C:\Users\ojiyo\Desktop\tennis\tennis-ai-data-platform-main\tennis-ai-data-platform-main\data\stake_cache.json")

# ── Raw odds pasted from Stake ──────────────────────────────────────────────
# Format: "Name\nOdd\n\nName\nOdd" or "Name, Surname\nOdd"
RAW_DATA = """
Vukic, Aleksandar
2,80

Brooksby, Jenson
1,43

Mochizuki, Shintaro
1,42

Basing, Max
2,80

Rafael Jodar
1,19

Gill, Felix
4,50

Kovacevic, Aleksandar
2,38

van de Zandschulp, Botic
1,56

Trungelliti, Marco
3,75

Damm Jr, Martin
1,26

Shapovalov, Denis
1,28

Carreño-Busta, Pablo
3,55

Svrcina, Dalibor
6,20

Learner Tien
1,11

van Assche, Luca
2,90

Fucsovics, Marton
1,40

Nava, Emilio
2,18

Buse, Ignacio
1,66

Rublev, Andrey
1,49

Safiullin, Roman
2,55

Muller, Alexandre
15,00

Paul, Tommy
1,01

Zheng, Michael
2,32

Norrie, Cameron
1,59

Rinderknech, Arthur
1,70

Tarvet, Oliver
2,11

Kwon, Soon Woo
2,35

Martin Landaluce
1,58

Ruud, Casper
2,95

Hurkacz, Hubert
1,39

Borges, Nuno
1,31

Boyer, Tristan
3,40

Ugo Carabelli, Camilo
1,84

Mérida, Daniel
1,94

Gastón, Hugo
2,85

Tsitsipas, Stefanos
1,41

Medjedovic, Hamad
1,46

Ofner, Sebastian
2,65

Walton, Adam
2,28

Prizmic, Dino
1,61

Sinner, Jannik
1,01

Kecmanovic, Miomir
15,00

Adolfo Daniel Vallejo
1,62

Mejía, Nicolás
2,25

Auger-Aliassime, Felix
1,02

Shevchenko, Alexander
12,00

Bautista Agut, Roberto
4,50

Joao Fonseca
1,19

Tirante, Thiago Agustín
3,00

Marozsan, Fabian
1,37

Struff, Jan-Lennard
1,36

Báez, Sebastián
3,05

Cilic, Marin
3,10

Medvedev, Daniil
1,35

Quinn, Ethan
1,57

Darderi, Luciano
2,37

Davidovich Fokina, Alejandro
1,23

Cerúndolo, Juan Manuel
4,10

de Jong, Jesper
3,10

Hijikata, Rinky
1,35

Nakashima, Brandon
1,24

Pinnington Jones, Jack
3,95

Wu, Yibing
11,00

Djokovic, Novak
1,03

Mannarino, Adrian
1,59

Droguet, Titouan
2,31

Tiafoe, Francis
1,22

Atmane, Terence
4,10

Royer, Valentin
1,72

Wendelken, Harry
2,09

Kopriva, Vit
1,62

Choinski, Jan
2,25

Majchrzak, Kamil
1,44

Tabilo, Alejandro
2,75

Jacquet, Kyrian
1,39

Gaubas, Vilius
2,95

Sweeny, Dane
4,00

Dimitrov, Grigor
1,23

Mensik, Jakub
1,41

Samuel, Toby
2,85

de Minaur, Alex
1,02

Burruchaga, Román Andrés
12,00

Kypson, Patrick
3,10

McDonald, Mackenzie
1,36

Shimabukuro, Sho
1,82

Faria, Jaime
1,95

Griekspoor, Tallon
1,40

Duckworth, James
2,90

Humbert, Ugo
1,37

Bergs, Zizou
3,00

Molcan, Alex
2,02

Altmaier, Daniel
1,77

Lehecka, Jiri
1,25

Popyrin, Alexei
3,85

Wawrinka, Stan
3,70

Berrettini, Matteo
1,27

Alex Michelsen
1,74

Fearnley, Jacob
2,06

Moutet, Corentin
2,07

Giron, Marcos
1,74

Bellucci, Mattia
1,71

Svajda, Zachary
2,10

Fritz, Taylor
1,67

Draper, Jack
2,16

Khachanov, Karen
1,31

Harris, Billy
3,40

Navone, Mariano
3,80

Cobolli, Flavio
1,26

Arnaldi, Matteo
2,12

Halys, Quentin
1,70

Bonzi, Benjamin
2,05

Diallo, Gabriel
1,75

Hanfmann, Yannick
2,25

Mpetshi Perricard, Giovanni
1,62

Munar, Jaume
3,60

Cerúndolo, Francisco
1,28

Kokkinakis, Thanasi
2,90

Bublik, Alexander
1,39

Virtanen, Otto
3,40

Shelton, Ben
1,30

Collignon, Raphael
2,14

Fils, Arthur
1,68

Alexander Blockx
7,60

Zverev, Alexander
1,08

Lorenzo Sonego
1,78

Etcheverry, Tomás Martín
2,01

Bergs, Zizou
3,35

Humbert, Ugo
1,30
"""

# ── Parse raw data ──────────────────────────────────────────────────────────
def parse_raw(text: str) -> dict[str, float]:
    """Parse alternating name/odds lines into dict."""
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    parsed = {}
    i = 0
    while i < len(lines) - 1:
        name_line = lines[i]
        odds_line = lines[i + 1]
        # odds line: "1,35" or "1.35"
        odds_clean = odds_line.replace(",", ".")
        try:
            odds = float(odds_clean)
            parsed[name_line] = odds
            i += 2
        except ValueError:
            i += 1
    return parsed

# ── Normalize Stake names (same logic as stake_agent) ──────────────────────
def normalize_name(name: str) -> list[str]:
    name = name.strip()
    # Remove accents for matching
    import unicodedata
    name = unicodedata.normalize('NFD', name)
    name = ''.join(c for c in name if unicodedata.category(c) != 'Mn')
    candidates = []
    if "," in name:
        parts = [p.strip() for p in name.split(",", 1)]
        last, first = parts[0], parts[1] if len(parts) > 1 else ""
        first_clean = " ".join(t for t in first.split() if len(t.rstrip(".")) > 1)
        if first_clean:
            candidates.append(f"{first_clean} {last}")
        candidates.append(last)
    else:
        tokens = name.split()
        real = [t for t in tokens if len(t.rstrip(".")) > 1]
        clean = " ".join(real)
        if clean:
            candidates.append(clean)
            if len(real) == 2:
                candidates.append(f"{real[1]} {real[0]}")
            candidates.append(real[-1])
        else:
            candidates.append(name)
    return list(dict.fromkeys(candidates))

def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

def match_name(stake_name: str, pipeline_names: list[str], cutoff=0.65) -> tuple[str | None, float]:
    candidates = normalize_name(stake_name)
    best, score = None, 0.0
    for pn in pipeline_names:
        pl = pn.lower()
        pl_last = pl.split()[-1]
        for c in candidates:
            cl = c.lower()
            s = max(
                similarity(cl, pl),
                similarity(cl.split()[-1], pl_last) * 0.9,
            )
            if s > score:
                score, best = s, pn
    return (best, score) if score >= cutoff else (None, score)

# ── Load pipeline player names ──────────────────────────────────────────────
from src.ingestion.extract_odds import fetch_odds
from src.processing.transform import flatten_odds, filter_upcoming
from dotenv import load_dotenv
load_dotenv(Path(r"C:\Users\ojiyo\Desktop\tennis\tennis-ai-data-platform-main\tennis-ai-data-platform-main\.env"))

raw = fetch_odds()
df = filter_upcoming(flatten_odds(raw))
pipeline_names = sorted(df["outcome_name"].unique().tolist())
print(f"Pipeline players: {len(pipeline_names)}")

# ── Parse and match ─────────────────────────────────────────────────────────
raw_odds = parse_raw(RAW_DATA)
print(f"Parsed {len(raw_odds)} entries from raw data")

result = {}
unmatched = []
for stake_name, odds in raw_odds.items():
    pn, score = match_name(stake_name, pipeline_names)
    if pn:
        result[pn] = odds
        # print(f"  ✓ {stake_name!r} → {pn!r} ({score:.2f}) @ {odds}")
    else:
        unmatched.append((stake_name, odds))

print(f"\nMatched: {len(result)} / {len(raw_odds)}")
if unmatched:
    print(f"Unmatched ({len(unmatched)}):")
    for n, o in unmatched:
        print(f"  ✗ {n!r} @ {o}")

# ── Save cache ───────────────────────────────────────────────────────────────
payload = {
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "player_count": len(result),
    "odds": result,
}
CACHE_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"\n✓ Saved {len(result)} players to stake_cache.json")
