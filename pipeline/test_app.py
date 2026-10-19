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
        # wizard price step: live commas and the weighted-size price calculator
        pg.click("[data-wz='type:ml']"); pg.fill("[data-wzf='city']", "פתח"); pg.wait_for_timeout(100); pg.locator("[data-wzcity]", has_text="פתח תקווה").first.click(); pg.wait_for_timeout(100)
        if pg.locator("[data-wzsel='proj']").count():
            pg.select_option("[data-wzsel='proj']", "0"); pg.click("[data-act='wznext']"); pg.wait_for_timeout(150)
            pg.locator("[data-wzf='price']").press_sequentially("1567000")
            if pg.input_value("[data-wzf='price']") != "1,567,000": fails.append("price field has no thousands commas")
            if pg.locator("[data-wzf='size']").count():
                pg.fill("[data-wzf='size']", "100"); pg.fill("[data-wzf='balc']", "10"); pg.fill("[data-wzf='stor']", "5"); pg.fill("[data-wzf='park']", "1"); pg.wait_for_timeout(100)
                exp = pg.evaluate("()=>{const g=Math.round(Math.round(107*wiz.d.ppsqm)*(1+VAT));return g-Math.min(Math.round(g*.2),300000)}")
                if "107" not in pg.inner_text("#wzcalc"): fails.append("weighted size wrong (expected 107)")
                pg.click("#wzcalc [data-wz^='price:']"); pg.wait_for_timeout(100)
                if pg.input_value("[data-wzf='price']") != f"{exp:,}": fails.append("calculated price not applied")
        else: fails.append("no official projects for Petah Tikva in wizard")
        pg.evaluate("()=>{ wiz = null; render(); }")
        # regressions found by the persona testers
        chk = pg.evaluate("""()=>{ const keep = JSON.stringify(S); S = exampleState(); S.example = false;
          S.payments = scheduleFromPcts([20, 80], S.profile.sign || "2026-11-01", S.profile.delivery || "2029-11-01"); const link = linkTotal();
          const pay1 = Math.round(mortgageCalc().first), pay2 = Math.round(equityScenarios().res[0].pay);
          S.mix.pPrime += 20; const bad = outMortgage().includes("100%"); S.mix.pPrime -= 20; S = migrate(JSON.parse(keep)); render(); return [link, pay1, pay2, bad]; }""")
        if not chk[0] > 0: fails.append("20/80 schedule lost its linkage")
        if abs(chk[1] - chk[2]) > 1: fails.append(f"two different monthly payments: {chk[1]} vs {chk[2]}")
        if not chk[3]: fails.append("mortgage results shown although the mix is not 100%")
        # app lock: set a code, reopen, wrong code stays locked, right code opens
        pg.evaluate("()=>{ setupOpen = true; render(); }"); pg.click("[data-lk='set']")
        for _ in range(2):
            for k in "2580": pg.click(f"[data-lk='d{k}']")
            pg.wait_for_timeout(150)
        pg.reload(); pg.wait_for_timeout(500)
        if pg.is_hidden("#lock"): fails.append("lock screen not shown after setting a code")
        for k in "1111": pg.click(f"[data-lk='d{k}']")
        pg.wait_for_timeout(150)
        if pg.is_hidden("#lock"): fails.append("wrong code opened the app")
        for k in "2580": pg.click(f"[data-lk='d{k}']")
        pg.wait_for_timeout(150)
        if not pg.is_hidden("#lock"): fails.append("right code did not open the app")
        pg.evaluate("()=>{ lockCfg = null; saveLock(); setupOpen = false; render(); }")
        if pg.evaluate("document.documentElement.scrollWidth") > w + 1: fails.append(f"horizontal scroll at {w}px")
        if errs: fails.append(f"page errors at {w}px: {errs[:3]}")
    b.close()
print("FAIL:\n" + "\n".join(fails) if fails else "OK")
sys.exit(1 if fails else 0)
