/* מפתח – service worker: the page comes from the network when online (so the daily data update arrives),
   and from the cache when offline. Static files (icons, manifest) are cache-first. */
const CACHE = "maftech-v4";
const SHELL = ["./", "./index.html", "./manifest.webmanifest", "./icons/icon-192.png", "./icons/icon-512.png", "./icons/apple-touch-icon.png"];
self.addEventListener("install", e => { e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting())); });
self.addEventListener("activate", e => { e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim())); });
self.addEventListener("fetch", e => {
  const req = e.request, u = new URL(req.url); if (req.method !== "GET" || u.origin !== location.origin || u.pathname.startsWith("/api/")) return;
  const isPage = req.mode === "navigate" || req.url.endsWith("/index.html");
  if (isPage) {
    e.respondWith(fetch(req).then(r => { const copy = r.clone(); caches.open(CACHE).then(c => c.put("./index.html", copy)); return r; })
      .catch(() => caches.match("./index.html")));
  } else {
    e.respondWith(caches.match(req).then(hit => hit || fetch(req).then(r => { const copy = r.clone(); caches.open(CACHE).then(c => c.put(req, copy)); return r; })));
  }
});

/* reminders: the server only wakes the phone; the messages are fetched here and shown */
self.addEventListener("push", e => {
  e.waitUntil((async () => {
    let msgs = [];
    try {
      const sub = await self.registration.pushManager.getSubscription();
      const r = await fetch("/api/push", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ action: "pending", endpoint: sub && sub.endpoint }) });
      msgs = (await r.json()).messages || [];
    } catch (err) {}
    if (!msgs.length) msgs = [{ title: "מפתח", body: "יש לכם תזכורת חדשה באפליקציה" }];
    for (const m of msgs.slice(-3)) await self.registration.showNotification(m.title || "מפתח", { body: m.body || "", icon: "./icons/icon-192.png", badge: "./icons/badge-96.png", tag: m.id || "maftech", dir: "rtl", lang: "he", data: { url: "./" } });
  })());
});
self.addEventListener("notificationclick", e => {
  e.notification.close();
  e.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then(ws => { for (const w of ws) if ("focus" in w) return w.focus(); return self.clients.openWindow("./"); }));
});
