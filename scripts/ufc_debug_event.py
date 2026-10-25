"""Debug: print structure of one ESPN UFC event to understand competitions format."""
import json
import requests

s = requests.Session()
s.headers["User-Agent"] = "Mozilla/5.0"

BASE = "https://sports.core.api.espn.com/v2/sports/mma/leagues/ufc"

# try all season types
data = None
for t in [2, 3, 1]:
    r = s.get(f"{BASE}/seasons/2024/types/{t}/events", params={"limit": 1})
    d = r.json()
    if d.get("items"):
        print(f"Found items with type={t}")
        data = d
        break
if not data:
    print("No items found in any type for 2024")
    raise SystemExit(1)
print("=== EVENTS LIST ITEM ===")
print(json.dumps(data.get("items", [{}])[0], indent=2))

event_ref = data["items"][0]["$ref"]
print("\n=== EVENT DETAIL ===")
ev = s.get(event_ref).json()
# print top-level keys
print("Keys:", list(ev.keys()))
print("name:", ev.get("name"))
print("competitions type:", type(ev.get("competitions")))
comps = ev.get("competitions") or []
print("competitions count:", len(comps))
if comps:
    print("\n=== FIRST COMPETITION (raw) ===")
    first = comps[0]
    print(json.dumps(first, indent=2)[:3000])

    if isinstance(first, dict) and "$ref" in first:
        print("\n=== FETCHING COMPETITION REF ===")
        comp = s.get(first["$ref"]).json()
        print("Keys:", list(comp.keys()))
        print(json.dumps(comp, indent=2)[:4000])
