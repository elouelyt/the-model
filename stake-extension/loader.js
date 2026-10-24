// Stake Combo Loader. Runs before Stake's own scripts. If the URL carries "#oj=<payload>", it writes the
// selections into the tab's betslip store (sessionStorage "betPrePlacementStore") so the slip is already
// filled when the page boots. It never clicks, never places a bet and makes no network request.
(() => {
  const m = location.hash.match(/(?:^|[#&])oj=([A-Za-z0-9_-]+)/);
  if (!m) return;

  const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  let picks;
  try {
    const b64 = m[1].replace(/-/g, "+").replace(/_/g, "/");
    picks = JSON.parse(atob(b64 + "=".repeat((4 - (b64.length % 4)) % 4)));
  } catch (e) {
    return;
  }
  if (!Array.isArray(picks)) return;

  const KEY = "betPrePlacementStore";
  let slip = [];
  try { slip = JSON.parse(sessionStorage.getItem(KEY) || "[]"); } catch (e) { slip = []; }
  if (!Array.isArray(slip)) slip = [];
  const have = new Set(slip.map((s) => s.id));

  for (const p of picks.slice(0, 20)) {
    const side = p.t === "under" ? "under" : p.t === "over" ? "over" : null;
    const odds = Number(p.p);
    if (!side || !UUID.test(p.o) || !UUID.test(p.e) || !(odds > 1)) continue;
    const id = `${p.o}_${side}`;
    if (have.has(id)) continue;
    have.add(id);
    slip.push({
      id, type: "swish", outcomeId: p.o, stake: 0, odds, acceptedOdds: odds, eventId: p.e, betType: side, atBat: false,
      sportInfo: { __typename: "Sport", id: "285d2c11-61ff-4d65-97e8-1bad9fdfa2c0", name: "Baloncesto", slug: "basketball", contentNotes: [] },
      analyticsProperties: { isPromotionBet: false }, fetching: false, fixtureStatus: "active",
    });
  }
  try { sessionStorage.setItem(KEY, JSON.stringify(slip)); } catch (e) { return; }

  // drop the hash so a refresh does not re-add selections the user removed
  try { history.replaceState(null, "", location.pathname + location.search); } catch (e) { /* ignore */ }
})();
