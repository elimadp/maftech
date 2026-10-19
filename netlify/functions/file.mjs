// Attached documents (contract, floor plan, ...). A file is stored in parts of up to 3.5MB, because one
// request to a function is limited to about 6MB. The id is a random 24-character key kept in the purchase data,
// so only people who have the purchase (you, or the household you share it with) can reach the file.
// PUT    /api/file?id=X&part=N&of=M   body = the bytes of part N (0-based); part 0 also saves name and type
// GET    /api/file?id=X&meta=1        -> { name, type, size, parts }
// GET    /api/file?id=X&part=N        -> the bytes of part N
// DELETE /api/file?id=X               -> removes the file
import { getStore } from "@netlify/blobs";

const ID = /^[a-z0-9]{20,40}$/;
const MAX_PARTS = 9, PART = 3_700_000;
const json = (body, status = 200) => new Response(JSON.stringify(body), {
  status, headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" }
});

export default async (req) => {
  const url = new URL(req.url), q = k => url.searchParams.get(k);
  const id = (q("id") || "").toLowerCase();
  if (!ID.test(id)) return json({ error: "bad id" }, 400);
  const store = getStore("files");
  if (req.method === "PUT") {
    const part = Number(q("part")), of = Number(q("of"));
    if (!Number.isInteger(part) || !Number.isInteger(of) || of < 1 || of > MAX_PARTS || part < 0 || part >= of) return json({ error: "bad part" }, 400);
    const buf = await req.arrayBuffer();
    if (!buf.byteLength || buf.byteLength > PART) return json({ error: "bad size" }, 413);
    await store.set(`${id}/${part}`, buf);
    if (part === 0) {
      const name = (q("name") || "file").slice(0, 120), type = (q("type") || "application/octet-stream").slice(0, 80);
      await store.setJSON(`${id}/meta`, { name, type, size: Number(q("size")) || 0, parts: of });
    }
    return json({ ok: true });
  }
  if (req.method === "GET") {
    if (q("meta")) { const m = await store.get(`${id}/meta`, { type: "json" }); return m ? json(m) : json({ error: "not found" }, 404); }
    const part = Number(q("part"));
    if (!Number.isInteger(part) || part < 0 || part >= MAX_PARTS) return json({ error: "bad part" }, 400);
    const b = await store.get(`${id}/${part}`, { type: "arrayBuffer" });
    if (!b) return json({ error: "not found" }, 404);
    return new Response(b, { headers: { "content-type": "application/octet-stream", "cache-control": "private, max-age=31536000, immutable" } });
  }
  if (req.method === "DELETE") {
    const m = await store.get(`${id}/meta`, { type: "json" });
    const n = m && m.parts ? m.parts : MAX_PARTS;
    await Promise.all([store.delete(`${id}/meta`), ...Array.from({ length: n }, (_, i) => store.delete(`${id}/${i}`))]);
    return json({ ok: true });
  }
  return json({ error: "method not allowed" }, 405);
};

export const config = { path: "/api/file" };
