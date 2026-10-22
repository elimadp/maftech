// Concurrent saves to a shared purchase: exactly one is stored, the other gets 409 (round-3 RT3-06).
// A fake store with the same conditional-write contract as Netlify Blobs (ETag compare-and-swap), and a barrier
// that makes both requests read the record before either writes. Usage: node pipeline/test_household.mjs
import { handle } from "../netlify/lib/household-core.mjs";
const R = []; const check = (name, exp, act, ok) => R.push([name, exp, JSON.stringify(act), ok ? "PASS" : "FAIL"]);
function fakeStore() {
  const m = new Map(); let n = 0; let gate = null;
  return {
    m, setGate(g) { gate = g; },
    async get(k) { const e = m.get(k); return e ? structuredClone(e.v) : null; },
    async getWithMetadata(k) { const e = m.get(k); const r = e ? { data: structuredClone(e.v), etag: e.etag } : null; if (gate) await gate(); return r; },
    async setJSON(k, v, o = {}) { const e = m.get(k);
      if (o.onlyIfNew && e) return { modified: false }; if (o.onlyIfMatch && (!e || e.etag !== o.onlyIfMatch)) return { modified: false };
      const etag = `"e${++n}"`; m.set(k, { v: structuredClone(v), etag }); return { modified: true, etag }; }
  };
}
const W = "a".repeat(64), H = { "x-maftech-w": W, "content-type": "application/json" };
const put = (st, state, ifMatch) => handle(new Request("https://x/api/household?code=testcode1", { method: "PUT", headers: H, body: JSON.stringify({ state, ifMatch }) }), st);
const S1 = "enc2:" + "A".repeat(20) + ":" + "B".repeat(20), S2 = "enc2:" + "C".repeat(20) + ":" + "D".repeat(20), S3 = "enc2:" + "E".repeat(20) + ":" + "F".repeat(20);
const barrier = k => { let waiting = 0, release; const p = new Promise(r => release = r); return async () => { if (++waiting >= k) release(); await p; }; };

const st = fakeStore();
const r0 = await put(st, S1); const v0 = await r0.json();
check("first save creates the record", 200, r0.status, r0.status === 200);
// both phones read version v0, then both try to write
st.setGate(barrier(2));
const [a, b] = await Promise.all([put(st, S2, v0.updatedAt), put(st, S3, v0.updatedAt)]); st.setGate(null);
const codes = [a.status, b.status].sort();
check("two saves on the same version: one 200, one 409", "[200,409]", codes, codes[0] === 200 && codes[1] === 409);
const win = a.status === 200 ? S2 : S3, stored = (await st.get("testcode1")).state;
check("the stored state is the one that got 200", win.slice(0, 7), stored.slice(0, 7), stored === win);
const lose = a.status === 409 ? a : b, lj = await lose.json();
check("409 carries the current version, so the phone can re-read and merge", "updatedAt", lj, !!lj.updatedAt && lj.updatedAt === (await st.get("testcode1")).updatedAt);
const r3 = await put(st, a.status === 409 ? S2 : S3, lj.updatedAt);
check("after re-reading, the second save goes in", 200, r3.status, r3.status === 200);
// two first saves at once (no record yet): only one creates it
const st2 = fakeStore(); st2.setGate(barrier(2));
const [c, d] = await Promise.all([put(st2, S1), put(st2, S2)]);
const c2 = [c.status, d.status].sort();
check("two first saves at once: one 200, one 409", "[200,409]", c2, c2[0] === 200 && c2[1] === 409);
// a storage that cannot confirm the conditional write never reports success
const st3 = fakeStore(); await put(st3, S1); const cur = await st3.get("testcode1");
st3.setGate(async () => { st3.m.get("testcode1").etag = '"changed-by-someone"'; }); const e = await put(st3, S2, cur.updatedAt); st3.setGate(null);
check("a write rejected by the storage condition is a 409, not a silent overwrite", 409, e.status, e.status === 409 && (await st3.get("testcode1")).state === S1);
const f = await handle(new Request("https://x/api/household?code=testcode1", { method: "PUT", headers: { ...H, "x-maftech-w": "b".repeat(64) }, body: JSON.stringify({ state: S2, ifMatch: cur.updatedAt }) }), st3);
check("wrong write token still refused", 403, f.status, f.status === 403);
for (const r of R) console.log(`${r[3]} | ${r[0]} | expected: ${r[1]} | actual: ${r[2]}`);
console.log(R.some(r => r[3] === "FAIL") ? "FAILED" : "ALL PASS", R.filter(r => r[3] === "PASS").length, "/", R.length);
