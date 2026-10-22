// Every morning: queue today's reminders for each phone and wake it up to show them.
import { getStore } from "@netlify/blobs";
import { getKeys, tickle, todayIL } from "../lib/push.mjs";

export default async () => {
  const subs = getStore("push"), keys = await getKeys(getStore("push-config")), today = todayIL();
  const from = new Date(Date.parse(today + "T12:00:00Z") - 3 * 864e5).toISOString().slice(0, 10);   // catch up if a morning run was missed
  const { blobs } = await subs.list();
  let sent = 0, gone = 0;
  for (const { key } of blobs) {
    const r = await subs.get(key, { type: "json" }); if (!r || !r.sub) continue;
    const due = (r.events || []).filter(e => e.at <= today && e.at >= from && !e.id.startsWith("boires:") && !(r.sent || []).includes(e.id + "@" + e.at));   // rate results go out in the evening (push-boi)
    if (!due.length) continue;
    const st = await tickle(r.sub, keys);
    if (st === 404 || st === 410) { await subs.delete(key); gone++; continue; }
    await subs.setJSON(key, { ...r, pending: [...(r.pending || []), ...due].slice(-10), sent: [...(r.sent || []), ...due.map(e => e.id + "@" + e.at)].slice(-300) });
    sent++;
  }
  console.log(JSON.stringify({ today, phones: blobs.length, sent, gone }));
  return new Response("ok");
};

export const config = { schedule: "0 5 * * *" };
