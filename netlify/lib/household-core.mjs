// Shared purchase for a household: the request handling, separate from the storage so it can be tested.
// Writes are compare-and-swap: a save is stored only if the record is still the version the phone last read
// (the blob's ETag, checked by the storage itself), so two phones saving at the same moment cannot overwrite
// each other silently: one is stored, the other gets 409 and the phone re-reads, merges and saves again.
import { createHash } from "node:crypto";

const CODE = /^[a-z0-9]{6,40}$/;
const hash = s => createHash("sha256").update(String(s)).digest("hex");
const pub = v => ({ state: v.state, updatedAt: v.updatedAt });
const json = (body, status = 200) => new Response(JSON.stringify(body), {
  status, headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" }
});
const conflict = async (store, code) => { const now = await store.get(code, { type: "json", consistency: "strong" }); return json({ error: "conflict", updatedAt: now && now.updatedAt }, 409); };

/* store: { get(key, opts), getWithMetadata(key, opts) -> { data, etag } | null, setJSON(key, value, { onlyIfMatch | onlyIfNew }) -> { modified } } */
export async function handle(req, store) {
  const url = new URL(req.url);
  if (url.searchParams.get("ping")) return json({ ok: true });
  const code = (url.searchParams.get("code") || "").toLowerCase();
  if (!CODE.test(code)) return json({ error: "bad code" }, 400);
  if (req.method === "GET") {
    const v = await store.get(code, { type: "json", consistency: "strong" });
    if (v && v.deleted) return json({ error: "deleted" }, 410);
    return v ? json(pub(v)) : json({ error: "not found" }, 404);
  }
  const w = req.headers.get("x-maftech-w") || "";
  if (req.method === "PUT") {
    let body;
    try { body = await req.json(); } catch { return json({ error: "bad body" }, 400); }
    if (!body || typeof body.state !== "string" || body.state.length > 1_500_000) return json({ error: "bad body" }, 400);
    // the app encrypts the purchase with the share code before sending ("enc1:..."); older versions sent plain JSON
    if (!/^enc[12]:[A-Za-z0-9+/=]{16,}:[A-Za-z0-9+/=]{16,}$/.test(body.state) && body.state !== "moved:v2") return json({ error: "bad state" }, 400);
    const got = await store.getWithMetadata(code, { type: "json", consistency: "strong" }), cur = got ? got.data : null;
    if (cur && cur.deleted) return json({ error: "deleted" }, 410);   // the purchase was deleted from the server: never bring it back
    if (cur && cur.wh && hash(w) !== cur.wh) return json({ error: "forbidden" }, 403);
    // refuse a save made on top of an older version; the phone then re-reads, merges and saves again
    if (cur && body.ifMatch !== cur.updatedAt) return json({ error: "conflict", updatedAt: cur.updatedAt }, 409);
    const v = { state: body.state, updatedAt: new Date().toISOString() + "~" + Math.random().toString(36).slice(2, 8) };   // unique per version
    const wh = cur && cur.wh ? cur.wh : (/^[a-f0-9]{64}$/.test(w) ? hash(w) : undefined);
    const res = await store.setJSON(code, wh ? { ...v, wh } : v, got ? { onlyIfMatch: got.etag } : { onlyIfNew: true });
    if (res && res.modified === false) return conflict(store, code);   // someone saved in between: never a silent overwrite
    if (!res) console.warn("household: storage library without conditional writes; save was not compare-and-swap");   // only with @netlify/blobs < 10
    return json(v);
  }
  if (req.method === "DELETE") {
    const got = await store.getWithMetadata(code, { type: "json", consistency: "strong" }), cur = got ? got.data : null;
    if (cur && cur.wh && hash(w) !== cur.wh) return json({ error: "forbidden" }, 403);
    await store.setJSON(code, { deleted: true, at: new Date().toISOString() });   // keep a marker so the other phone cannot recreate it
    return json({ ok: true });
  }
  return json({ error: "method not allowed" }, 405);
}
