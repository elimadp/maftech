#!/usr/bin/env python3
"""Smoke test for the app before publishing. Usage: python3 test_app.py index.new.html  (exit 1 on failure)"""
import sys, pathlib
from playwright.sync_api import sync_playwright
path = pathlib.Path(sys.argv[1]).resolve()
fails = []
with sync_playwright() as p:
    b = p.chromium.launch()
    for w in (360, 1024):
        pg = b.new_page(viewport={"width": w, "height": 800}); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(path.as_uri()); pg.wait_for_timeout(700)
        pg.evaluate("()=>{[...document.querySelectorAll('button')].find(x=>/דוגמה/.test(x.textContent))?.click()}"); pg.wait_for_timeout(300)
        tabs = pg.evaluate("[...document.querySelectorAll('[data-tab]')].map(x=>x.dataset.tab)")
        if len(tabs) < 4: fails.append(f"only {len(tabs)} tabs")
        for t in dict.fromkeys(tabs):
            pg.evaluate(f"()=>document.querySelector('[data-tab=\"{t}\"]').click()"); pg.wait_for_timeout(250)
            if not pg.locator(".screen").count(): fails.append(f"tab {t} rendered nothing")
        pg.evaluate("()=>{[...document.querySelectorAll('[data-tab]')].find(x=>/אזורים/.test(x.textContent))?.click()}"); pg.wait_for_timeout(250)
        pg.select_option("#wcity", label="פתח תקווה"); pg.wait_for_timeout(300)
        for tb in ("#areatb", "#pxtb"):
            if not pg.evaluate(f"[...document.querySelectorAll('{tb} tr')].some(r=>r.innerText.includes('עין גנים'))"): fails.append(f"{tb}: Ein Ganim missing")
        pg.click("[data-pxper='2']"); pg.select_option("#pxage", "3"); pg.select_option("#pxrooms", "2"); pg.wait_for_timeout(200)
        if not pg.locator("#pxtb tr").count(): fails.append("price table empty for age+rooms filter")
        pg.fill("#areasearch", "עין"); pg.wait_for_timeout(150)
        if not any("עין גנים" in t for t in pg.locator("#areasug .sug").all_inner_texts()): fails.append("search suggestions missing Ein Ganim")
        pg.fill("#areasearch", "")
        # onboarding wizard opens and the first step renders
        pg.evaluate("()=>{ if (typeof startWizard === 'function') startWizard(); }"); pg.wait_for_timeout(200)
        if not pg.locator("[data-wz='type:ml']").count(): fails.append("onboarding wizard did not open")
        pg.evaluate("()=>{ wiz = null; render(); }")
        if pg.evaluate("document.documentElement.scrollWidth") > w + 1: fails.append(f"horizontal scroll at {w}px")
        if errs: fails.append(f"page errors at {w}px: {errs[:3]}")
    b.close()
print("FAIL:\n" + "\n".join(fails) if fails else "OK")
sys.exit(1 if fails else 0)
