// Shared purchase for a household (live sharing between two phones).
// GET  /api/household?code=XXXX  -> { state, updatedAt }   (404 if the code does not exist)
// PUT  /api/household?code=XXXX  body { state }            -> { state, updatedAt }   (state is encrypted by the phones)
// DELETE /api/household?code=XXXX                         -> removes the shared purchase from the server
// GET  /api/household?ping=1     -> { ok: true }           (lets the app know sharing is available)
// The code is a random 9-character key that only the two of you know; there are no accounts.
// v2: the phones send a record id derived from the share code (never the code itself) and a write token
// (header x-maftech-w); the server keeps only a hash of the token and refuses changes without it.
import { getStore } from "@netlify/blobs";
import { createHash } from "node:crypto";

const CODE = /^[a-z0-9]{6,40}$/;
const hash = s => createHash("sha256").update(String(s)).digest("hex");
const pub = v => ({ state: v.state, updatedAt: v.updatedAt });
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
    if (v && v.deleted) return json({ error: "deleted" }, 410);
    return v ? json(pub(v)) : json({ error: "not found" }, 404);
  }
  if (req.method === "PUT") {
    let body;
    try { body = await req.json(); } catch { return json({ error: "bad body" }, 400); }
    if (!body || typeof body.state !== "string" || body.state.length > 1_500_000) return json({ error: "bad body" }, 400);
    // the app encrypts the purchase with the share code before sending ("enc1:..."); older versions sent plain JSON
    if (!/^enc[12]:[A-Za-z0-9+/=]{16,}:[A-Za-z0-9+/=]{16,}$/.test(body.state) && body.state !== "moved:v2") return json({ error: "bad state" }, 400);
    // refuse a save made on top of an older version; the phone then re-reads, merges and saves again
    const cur = await store.get(code, { type: "json" });
    if (cur && cur.deleted) return json({ error: "deleted" }, 410);   // the purchase was deleted from the server: never bring it back
    const w = req.headers.get("x-maftech-w") || "";
    if (cur && cur.wh && hash(w) !== cur.wh) return json({ error: "forbidden" }, 403);
    if (cur && body.ifMatch !== cur.updatedAt) return json({ error: "conflict", updatedAt: cur.updatedAt }, 409);
    const v = { state: body.state, updatedAt: new Date().toISOString() };
    const wh = cur && cur.wh ? cur.wh : (/^[a-f0-9]{64}$/.test(w) ? hash(w) : undefined);
    await store.setJSON(code, wh ? { ...v, wh } : v);
    return json(v);
  }
  if (req.method === "DELETE") { const cur = await store.get(code, { type: "json" }); if (cur && cur.wh && hash(req.headers.get("x-maftech-w") || "") !== cur.wh) return json({ error: "forbidden" }, 403); await store.setJSON(code, { deleted: true, at: new Date().toISOString() }); return json({ ok: true }); }   // keep a marker so the other phone cannot recreate it
  return json({ error: "method not allowed" }, 405);
};

export const config = { path: "/api/household" };
