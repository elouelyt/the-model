import requests

BASE = "https://odds-data.stake.com"
HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (compatible; tennis-ai-test/1.0)",
    "Origin": "https://stake.com",
    "Referer": "https://stake.com/"
}

session = requests.Session()
session.headers.update(HEADERS)

# Obtener torneos ATP singles
r = session.get(f"{BASE}/sport/tennis/category/atp/tournament", timeout=15)
tournaments = r.json().get("tournament", [])

all_fixtures = []
for t in tournaments:
    slug = t["slug"]
    name = t.get("name", slug).lower()
    if "double" in slug or "double" in name:
        continue
    r2 = session.get(f"{BASE}/sport/tennis/category/atp/tournament/{slug}/fixture", timeout=15)
    fixtures = r2.json().get("fixture", [])
    all_fixtures.extend(fixtures)

print(f"Total singles fixtures: {len(all_fixtures)}\n")

# Verificar odds de cada fixture
for f in all_fixtures:
    slug = f["slug"]
    name = f["name"]
    r3 = session.get(f"{BASE}/odds/{slug}", timeout=15)
    data = r3.json()
    winner = None
    for g in data.get("groups", []):
        for ml in g.get("markets", []):
            if not isinstance(ml, list):
                ml = [ml]
            for m in ml:
                if m.get("name") == "Winner" and m.get("specifiers") == "":
                    winner = [(o["name"], o["odds"]) for o in m["outcomes"]]
    if winner:
        print(f"✅ {name}")
        for p, o in winner:
            print(f"   {p}: {o}")
    else:
        print(f"❌ {name}")