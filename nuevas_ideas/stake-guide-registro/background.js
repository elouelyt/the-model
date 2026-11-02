// Clicking the toolbar icon opens the side panel next to the current tab.
chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });

// Bet recorder: bets.js (on the Stake tab) sends one record per bet Stake confirmed. They are queued here and written, one file each,
// to the PRIVATE repo below through GitHub's API with a fine-grained token that can only write that repo (set in the side panel).
const REPO = "elouelyt/the-model-bets";
const get = (k) => new Promise((r) => chrome.storage.local.get(k, (v) => r(v[k])));
const set = (o) => new Promise((r) => chrome.storage.local.set(o, r));
const b64 = (s) => btoa(String.fromCharCode(...new TextEncoder().encode(s)));
let flushing = false;
let again = false;

// Every read-modify-write of betQueue goes through this chain: two bets arriving seconds apart (or one arriving while the queue is being
// sent) used to overwrite each other's copy of the queue and the later bet was lost.
let chain = Promise.resolve();
const locked = (fn) => { const p = chain.then(fn); chain = p.catch(() => {}); return p; };
const enqueue = (bet) => locked(async () => {
  const q = (await get("betQueue")) || [];
  if (!q.some((b) => b.id === bet.id)) await set({ betQueue: [...q, bet] });
});
const dequeue = (id) => locked(async () => {
  const q = (await get("betQueue")) || [];
  await set({ betQueue: q.filter((b) => b.id !== id) });
  return q.length - 1;
});

async function flush() {
  if (flushing) { again = true; return; }       // a bet queued while sending: the running loop sends it next
  flushing = true;
  try {
    do { again = false; await sendQueue(); } while (again);
  } finally {
    flushing = false;
  }
}

async function sendQueue() {
  try {
    const token = await get("ghToken");
    let st = (await get("betStats")) || { sent: 0 };
    if (!token) { const n = ((await get("betQueue")) || []).length; await set({ betStats: { ...st, pending: n, error: n ? "Falta el token de GitHub (ajustes del panel)" : "" } }); return; }
    for (;;) {
      const queue = (await get("betQueue")) || [];
      const bet = queue[0];
      if (!bet) break;
      const month = bet.placed_at.slice(0, 7);
      const res = await fetch(`https://api.github.com/repos/${REPO}/contents/bets/${month}/${bet.id}.json`, {
        method: "PUT",
        headers: { Authorization: `Bearer ${token}`, Accept: "application/vnd.github+json", "Content-Type": "application/json" },
        body: JSON.stringify({ message: `bet ${bet.id}`, content: b64(JSON.stringify(bet, null, 1)) }),
      });
      if (res.ok || res.status === 422) {          // 422 = that file already exists (sent before)
        const left = await dequeue(bet.id);
        st = { sent: (st.sent || 0) + 1, last: bet.id, error: "" };
        await set({ betStats: { ...st, pending: left } });
      } else {
        await set({ betStats: { ...st, pending: queue.length, error: `GitHub respondió ${res.status}${res.status === 401 || res.status === 403 ? " (revisa el token)" : ""}` } });
        break;
      }
    }
  } catch (e) {
    const st = (await get("betStats")) || {};
    await set({ betStats: { ...st, error: "Sin conexión con GitHub; se reintentará" } });
  }
}

chrome.runtime.onMessage.addListener((msg) => {
  if (msg && msg.type === "bet" && msg.bet) {
    enqueue(msg.bet).then(flush);
  }
  if (msg && msg.type === "flush") flush();
});
chrome.alarms.create("flush", { periodInMinutes: 5 });
chrome.alarms.onAlarm.addListener((a) => { if (a.name === "flush") flush(); });
chrome.runtime.onStartup.addListener(flush);
