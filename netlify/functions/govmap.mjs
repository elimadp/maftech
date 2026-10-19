// Fallback relay for GovMap's public real-estate deals API, used only if the phone cannot call GovMap directly.
// Only the two read-only deal lists are allowed, so this is not an open proxy.
// GET /api/govmap?p=real-estate/street-deals/6383-123?limit=1000&dealType=2&startDate=2025-01
const OK = /^real-estate\/(street|neighborhood)-deals\/\d{1,6}-\d{1,6}(\?[A-Za-z0-9=&\-]*)?$/;

export default async (req) => {
  const p = new URL(req.url).searchParams.get("p") || "";
  if (!OK.test(p)) return new Response(JSON.stringify({ error: "bad path" }), { status: 400, headers: { "content-type": "application/json" } });
  try {
    const r = await fetch("https://www.govmap.gov.il/api/" + p, { headers: { accept: "application/json, text/plain, */*", "accept-language": "he-IL,he;q=0.9", referer: "https://www.govmap.gov.il/", origin: "https://www.govmap.gov.il", "user-agent": "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Mobile Safari/537.36" } });
    const body = await r.text();
    if (!r.ok) return new Response(JSON.stringify({ error: "upstream", status: r.status, body: body.slice(0, 200) }), { status: 502, headers: { "content-type": "application/json" } });
    return new Response(body, { status: 200, headers: { "content-type": "application/json; charset=utf-8", "cache-control": "public, max-age=3600" } });
  } catch (e) {
    return new Response(JSON.stringify({ error: "upstream", status: 0, body: String(e && e.message || e).slice(0, 200) }), { status: 502, headers: { "content-type": "application/json" } });
  }
};

export const config = { path: "/api/govmap" };
