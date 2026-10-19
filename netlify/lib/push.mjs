// Web push "tickles" without a payload: the phone wakes up, asks /api/push for its messages and shows them.
// Without a payload nothing needs encrypting, so this needs only the VAPID signature (built in node:crypto).
import { createHash, createPrivateKey, generateKeyPairSync, sign } from "node:crypto";

const b64u = b => Buffer.from(b).toString("base64url");
export const subKey = endpoint => createHash("sha256").update(String(endpoint)).digest("hex").slice(0, 40);

export async function getKeys(cfg) {
  let k = await cfg.get("vapid", { type: "json" });
  if (k && k.pub && k.jwk) return k;
  const { privateKey, publicKey } = generateKeyPairSync("ec", { namedCurve: "prime256v1" });
  const pj = publicKey.export({ format: "jwk" });
  k = { jwk: privateKey.export({ format: "jwk" }), pub: b64u(Buffer.concat([Buffer.from([4]), Buffer.from(pj.x, "base64url"), Buffer.from(pj.y, "base64url")])) };
  await cfg.setJSON("vapid", k);
  return (await cfg.get("vapid", { type: "json" })) || k;   // if two calls raced, both use what was stored
}

export function vapidAuth(endpoint, keys) {
  const aud = new URL(endpoint).origin;
  const h = b64u(JSON.stringify({ typ: "JWT", alg: "ES256" }));
  const p = b64u(JSON.stringify({ aud, exp: Math.floor(Date.now() / 1000) + 12 * 3600, sub: "https://maftech-eli.netlify.app" }));
  const sig = sign("sha256", Buffer.from(h + "." + p), { key: createPrivateKey({ key: keys.jwk, format: "jwk" }), dsaEncoding: "ieee-p1363" });
  return `vapid t=${h}.${p}.${b64u(sig)}, k=${keys.pub}`;
}

export async function tickle(sub, keys) {
  try {
    const r = await fetch(sub.endpoint, { method: "POST", headers: { TTL: "86400", Urgency: "normal", Authorization: vapidAuth(sub.endpoint, keys), "Content-Length": "0" } });
    return r.status;
  } catch (e) { return 0; }
}

// today's date in Israel, YYYY-MM-DD
export const todayIL = () => new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Jerusalem" }).format(new Date());
