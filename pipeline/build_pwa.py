#!/usr/bin/env python3
"""Turn the app page (same file as the Claude artifact) into the installable phone app:
adds the manifest, icons and the offline service worker. Usage: python3 build_pwa.py app.html index.html"""
import sys
src, out = sys.argv[1], sys.argv[2]
h = open(src, encoding="utf-8").read()
if "<!doctype" not in h[:200].lower():
    h = '<!doctype html>\n<html lang="he" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><title>דירה בשליטה</title></head><body>\n' + h + "\n</body></html>"
head = """<link rel="manifest" href="manifest.webmanifest">
<meta name="theme-color" content="#1e5a4a">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="דירה בשליטה">
<link rel="apple-touch-icon" href="icons/apple-touch-icon.png">
<link rel="icon" type="image/png" href="icons/icon-192.png">
<script>if ("serviceWorker" in navigator && (location.protocol === "https:" || location.hostname === "localhost")) addEventListener("load", () => navigator.serviceWorker.register("sw.js").catch(() => {}));</script>
"""
if 'rel="manifest"' not in h:
    i = h.lower().index("</head>")
    h = h[:i] + head + h[i:]
open(out, "w", encoding="utf-8").write(h)
print("built", out, len(h))
