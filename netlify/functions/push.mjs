// Reminders on the phone.
// GET  /api/push?key=1                         -> { key }  (public key the phone subscribes with)
// POST { action: "save", sub, events }         -> stores the subscription and the upcoming reminders
// POST { action: "pending", endpoint }         -> messages waiting for this phone (called by the service worker)
// POST { action: "test", endpoint }            -> sends a test notification now
// POST { action: "remove", endpoint }
import { getStore } from "@netlify/blobs";
import { getKeys, subKey, tickle } from "../lib/push.mjs";

const json = (body, status = 200) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" } });
const clean = s => String(s || "").slice(0, 200);

export default async (req) => {
  const subs = getStore("push"), cfg = getStore("push-config");
  if (req.method === "GET") return json({ key: (await getKeys(cfg)).pub });
  if (req.method !== "POST") return json({ error: "method" }, 405);
  let b; try { b = await req.json(); } catch { return json({ error: "bad body" }, 400); }
  if (!b || typeof b !== "object") return json({ error: "bad body" }, 400);
  const endpoint = b.sub ? b.sub.endpoint : b.endpoint;
  if (!endpoint || !/^https:\/\/(fcm\.googleapis\.com|[a-z0-9.-]+\.push\.apple\.com|updates\.push\.services\.mozilla\.com|[a-z0-9.-]+\.notify\.windows\.com)\//.test(endpoint) || endpoint.length > 1000) return json({ error: "bad endpoint" }, 400);
  const id = subKey(endpoint), cur = (await subs.get(id, { type: "json" })) || null;
  if (b.action === "save") {
    if (!b.sub || !b.sub.keys) return json({ error: "bad sub" }, 400);
    const events = (Array.isArray(b.events) ? b.events : []).slice(0, 80)
      .filter(e => e && /^\d{4}-\d{2}-\d{2}$/.test(e.at)).map(e => ({ id: clean(e.id), at: e.at, title: clean(e.title), body: clean(e.body) }));
    await subs.setJSON(id, { sub: b.sub, events, sent: cur ? cur.sent || [] : [], pending: cur ? cur.pending || [] : [], saved: new Date().toISOString() });
    return json({ ok: true, events: events.length });
  }
  if (b.action === "pending") {
    if (!cur) return json({ messages: [] });
    const messages = cur.pending || [];
    if (messages.length) await subs.setJSON(id, { ...cur, pending: [] });
    return json({ messages });
  }
  if (b.action === "test") {
    if (!cur) return json({ error: "not subscribed" }, 404);
    await subs.setJSON(id, { ...cur, pending: [...(cur.pending || []), { id: "test", title: "דירה בשליטה", body: "התזכורות פועלות ✓ נזכיר לכם לפני כל תשלום וכל החלטת ריבית." }] });
    const st = await tickle(cur.sub, await getKeys(cfg));
    return json({ ok: st >= 200 && st < 300, status: st });
  }
  if (b.action === "remove") { await subs.delete(id); return json({ ok: true }); }
  return json({ error: "action" }, 400);
};

export const config = { path: "/api/push" };
