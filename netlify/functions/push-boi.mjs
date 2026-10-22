// Evening of a Bank of Israel rate decision: tell each phone what was decided.
// The decision comes from the bot's check record (status branch), and only once the site already has it,
// so the notification and the app say the same thing. Each phone gets it once.
import { getStore } from "@netlify/blobs";
import { getKeys, tickle, todayIL } from "../lib/push.mjs";

const CHECK = "https://raw.githubusercontent.com/elimadp/maftech/status/check.json";

export default async () => {
  const today = todayIL();
  let c; try { const r = await fetch(CHECK + "?t=" + Date.now(), { headers: { "user-agent": "maftech-push" } }); c = await r.json(); } catch (e) { console.log("no check"); return new Response("no check"); }
  const b = c && c.boi;
  if (!b || b.dateISO !== today || b.prev == null || c.marketUpdatedISO !== today) { console.log("no decision on the site today"); return new Response("nothing"); }
  const rate = +b.rate, prev = +b.prev, d = Math.round((rate - prev) * 100) / 100;
  const title = d === 0 ? "החלטת הריבית: ללא שינוי" : `החלטת הריבית: ${d < 0 ? "הורדה" : "העלאה"} ל-${rate}%`;
  const head = d === 0 ? `בנק ישראל השאיר את הריבית ${rate}%. ההחזר שלכם לא משתנה.` : `בנק ישראל ${d < 0 ? "הוריד" : "העלה"} את הריבית ל-${rate}% (מ-${prev}%).`;
  const subs = getStore("push"), keys = await getKeys(getStore("push-config")), sentId = "boires@" + today;
  const { blobs } = await subs.list();
  let sent = 0, gone = 0;
  for (const { key } of blobs) {
    const r = await subs.get(key, { type: "json" }); if (!r || !r.sub || (r.sent || []).includes(sentId)) continue;
    const ev = (r.events || []).find(e => e.id === "boires:" + today) || (r.events || []).find(e => e.id === "boi:" + today);
    if (!ev) continue;   // this phone has no reminders for this decision
    const body = d === 0 ? head : `${head} ${ev.id.startsWith("boires:") && ev.body ? ev.body + " " : ""}פתחו את האפליקציה לפרטים.`;
    const st = await tickle(r.sub, keys);
    if (st === 404 || st === 410) { await subs.delete(key); gone++; continue; }
    await subs.setJSON(key, { ...r, pending: [...(r.pending || []), { id: "boires:" + today, title, body }].slice(-10), sent: [...(r.sent || []), sentId].slice(-300) });
    sent++;
  }
  console.log(JSON.stringify({ today, rate, prev, phones: blobs.length, sent, gone }));
  return new Response("ok");
};

// every hour through the evening (UTC): 18:15–22:15 in summer, 17:15–21:15 in winter, Israel time
export const config = { schedule: "15 15-19 * * *" };
