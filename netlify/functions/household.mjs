// Shared purchase for a household (live sharing between two phones).
// GET  /api/household?code=XXXX  -> { state, updatedAt }   (404 if the code does not exist)
// PUT  /api/household?code=XXXX  body { state }            -> { state, updatedAt }
// GET  /api/household?ping=1     -> { ok: true }           (lets the app know sharing is available)
// The code is a random 9-character key that only the two of you know; there are no accounts.
import { getStore } from "@netlify/blobs";

const CODE = /^[a-z0-9]{6,20}$/;
const json = (body, status = 200) => new Response(JSON.stringify(body), {
  status, headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" }
});

export default async (req) => {
  const url = new URL(req.url);
  if (url.searchParams.get("ping")) return json({ ok: true });
  const code = (url.searchParams.get("code") || "").toLowerCase();
  if (!CODE.test(code)) return json({ error: "bad code" }, 400);
  const store = getStore("households");
  if (req.method === "GET") {
    const v = await store.get(code, { type: "json" });
    return v ? json(v) : json({ error: "not found" }, 404);
  }
  if (req.method === "PUT") {
    let body;
    try { body = await req.json(); } catch { return json({ error: "bad body" }, 400); }
    if (!body || typeof body.state !== "string" || body.state.length > 1_500_000) return json({ error: "bad body" }, 400);
    try { JSON.parse(body.state); } catch { return json({ error: "bad state" }, 400); }
    // refuse a save made on top of an older version; the phone then re-reads, merges and saves again
    if (body.ifMatch !== undefined) {
      const cur = await store.get(code, { type: "json" });
      if (cur && body.ifMatch !== cur.updatedAt) return json({ error: "conflict", updatedAt: cur.updatedAt }, 409);
    }
    const v = { state: body.state, updatedAt: new Date().toISOString() };
    await store.setJSON(code, v);
    return json(v);
  }
  return json({ error: "method not allowed" }, 405);
};

export const config = { path: "/api/household" };
