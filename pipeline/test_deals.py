"""Several saved deals: migration, isolation (A/B), switching, refresh, reset, delete. Runs against the local mock (python3 mock.py <repo> 8765)."""
import json, sys
from playwright.sync_api import sync_playwright
URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8765/"
R = []
def check(name, exp, act, ok): R.append((name, exp, act, "PASS" if ok else "FAIL"))
with sync_playwright() as p:
    b = p.chromium.launch(); ctx = b.new_context(viewport={"width": 360, "height": 780}); pg = ctx.new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("dialog", lambda d: d.accept())
    E = lambda js: pg.evaluate("()=>{" + js + "}") if js.strip().endswith(";") else pg.evaluate("()=>(" + js + ")")
    def wait(): pg.wait_for_load_state("load"); pg.wait_for_timeout(700)
    METRICS = """(()=>{const c=cashflow(),d=drawSteps();return {city:S.profile.city,price:S.profile.price,eq:chosenEquity(),pays:S.payments.length,paid:S.payments.filter(x=>x.paid).map(x=>x.id),mix:JSON.stringify(S.mix),low:c?Math.round(c.low.close):null,costs:Math.round(costsTotal()),drawn:d?Math.round(d.drawn):null}})()"""
    pg.goto(URL); wait()
    # 1. migration of an existing single-purchase user (old format, no registry)
    E("localStorage.clear(); const s=exampleState(); s.example=false; s.profile.city='פתח תקווה'; s.profile.price=1600000; s.payments.forEach(x=>{}); s.fin.equity=250000; s.fin.eqCustom=true; localStorage.setItem('maftech.state.v1', JSON.stringify(s));")
    pg.reload(); wait()
    reg = E("dealsReg()"); A = E(METRICS); aid = reg["active"] if reg else None
    check("M1 מיגרציה: עסקה אחת נוצרה, הנתונים נשמרו", "1 · 1,600,000 · 250,000", f"{len(reg['list']) if reg else 0} · {A['price']} · {A['eq']}", reg and len(reg["list"]) == 1 and A["price"] == 1600000 and A["eq"] == 250000 and not E("S.example"))
    check("M1b שם אוטומטי מהנתונים", "פתח תקווה · מחיר למשתכן", E("dealName(dealsReg().list[0])"), "פתח תקווה" in E("dealName(dealsReg().list[0])"))
    # 2. second deal through the wizard
    E("newDeal();"); pg.wait_for_timeout(200)
    check("M2a עסקה חדשה מתחילה באשף, הקודמת לא נמחקה", "אשף + עסקה אחת שמורה", f"wiz={E('!!wiz')} newDeal={E('!!(wiz&&wiz.newDeal)')}", E("!!(wiz && wiz.newDeal)") and len(E("dealsReg().list")) == 1)
    E("wiz.d.type='new'; wiz.d.buyer='first'; wiz.d.city='רמת גן'; wiz.d.price='2400000'; wiz.d.sign='2026-12-01'; wiz.d.delivery='2029-12-01'; wiz.d.savings='900000'; wiz.d.income='30000'; wiz.d.expenses='15000'; wizFinish();")
    wait()
    reg = E("dealsReg()"); bid = reg["active"]
    E("S.fin.equity=600000; S.fin.eqCustom=true; S.payments.sort((a,b)=>a.date.localeCompare(b.date))[0].paid=true; persist();"); pg.wait_for_timeout(200)
    Bm = E(METRICS)
    check("M2 שתי עסקאות, B פעילה", "2 · רמת גן · 2,400,000 · 600,000", f"{len(reg['list'])} · {Bm['city']} · {Bm['price']} · {Bm['eq']}", len(reg["list"]) == 2 and bid != aid and Bm["city"] == "רמת גן" and Bm["price"] == 2400000 and Bm["eq"] == 600000)
    parkedA = E(f"JSON.parse(JSON.parse(localStorage.getItem('maftech.deal.{aid}'))['maftech.state.v1']).profile.price")
    check("M3 A נשמרה בנפרד", 1600000, parkedA, parkedA == 1600000)
    # 3. switch B -> A through the UI
    pg.click(".dealpick"); pg.wait_for_timeout(150); pg.click(f"[data-deal='{aid}']"); wait()
    A2 = E(METRICS)
    for k in ["city", "price", "eq", "pays", "paid", "mix", "low", "costs", "drawn"]:
        check(f"M4 מעבר B→A: {k} חזר בדיוק", A[k], A2[k], A[k] == A2[k])
    check("M5 תשלום ששולם ב-B לא עבר ל-A", "[]", A2["paid"], A2["paid"] == [])
    # 4. switch A -> B
    pg.click(".dealpick"); pg.wait_for_timeout(150); pg.click(f"[data-deal='{bid}']"); wait()
    B2 = E(METRICS)
    for k in ["city", "price", "eq", "pays", "paid", "mix", "low", "costs", "drawn"]:
        check(f"M6 מעבר A→B: {k} חזר בדיוק", Bm[k], B2[k], Bm[k] == B2[k])
    check("M6b המשכנתא, התזרים והחודש הצפוף שונים בין העסקאות", "שונים", f"{A['drawn']}/{B2['drawn']} · {A['low']}/{B2['low']}", A["drawn"] != B2["drawn"] and A["low"] != B2["low"])
    # 5. refresh keeps the active deal
    pg.reload(); wait()
    check("M7 רענון: B נשארת פעילה עם הנתונים שלה", "רמת גן · 2,400,000", f"{E('S.profile.city')} · {E('S.profile.price')}", E("dealsReg().active") == bid and E("S.profile.price") == 2400000)
    # 6. a change in B does not touch A
    E("S.profile.price=2500000; persist();"); pg.wait_for_timeout(150)
    pg.click(".dealpick"); pg.wait_for_timeout(150); pg.click(f"[data-deal='{aid}']"); wait()
    check("M8 שינוי מחיר ב-B לא שינה את A", 1600000, E("S.profile.price"), E("S.profile.price") == 1600000)
    pg.click(".dealpick"); pg.wait_for_timeout(150); pg.click(f"[data-deal='{bid}']"); wait()
    check("M8b המחיר החדש נשמר ב-B", 2500000, E("S.profile.price"), E("S.profile.price") == 2500000)
    # 7. share binding stays with its deal
    E("localStorage.setItem('maftech.priv', JSON.stringify({household:'testcode1'}));")
    pg.click(".dealpick"); pg.wait_for_timeout(150); pg.click(f"[data-deal='{aid}']"); wait()
    check("M9 שיוך שיתוף של B לא עובר ל-A", "אין", E("localStorage.getItem('maftech.priv')") or "אין", "testcode1" not in (E("localStorage.getItem('maftech.priv')") or ""))
    E(f"const s=JSON.parse(localStorage.getItem('maftech.deal.{bid}')); s['maftech.priv']=null; localStorage.setItem('maftech.deal.{bid}', JSON.stringify(s));")
    # 8. reset only the active deal (A), B untouched
    pg.evaluate("()=>{confirmReset=true; setupOpen=true; render();}"); pg.wait_for_timeout(100)
    pg.click("[data-act=resetyes]"); pg.wait_for_timeout(300)
    parkedB = E(f"JSON.parse(JSON.parse(localStorage.getItem('maftech.deal.{bid}'))['maftech.state.v1']).profile.price")
    check("M10 איפוס A לא פגע ב-B", 2500000, parkedB, parkedB == 2500000 and len(E("dealsReg().list")) == 2)
    E("wiz=null; render();")
    # 9. delete the active deal (A): B becomes active, intact
    E(f"deleteDeal('{aid}')"); wait()
    check("M11 מחיקת A: נשארה רק B, פעילה ושלמה", "1 · רמת גן · 2,500,000", f"{len(E('dealsReg().list'))} · {E('S.profile.city')} · {E('S.profile.price')}", len(E("dealsReg().list")) == 1 and E("dealsReg().active") == bid and E("S.profile.price") == 2500000)
    check("M12 בלי שאריות של A בטלפון", "אין", E(f"localStorage.getItem('maftech.deal.{aid}')") or "אין", not E(f"localStorage.getItem('maftech.deal.{aid}')"))
    # 10. global data stays global: first name
    E("localStorage.setItem('maftech.name','אלי');"); E("newDeal();"); E("wiz.d.type='resale'; wiz.d.buyer='first'; wiz.d.city='חיפה'; wiz.d.price='1500000'; wiz.d.sign='2026-12-15'; wiz.d.savings='500000'; wiz.d.income='20000'; wiz.d.expenses='12000'; wizFinish();"); wait()
    check("M13 השם הפרטי גלובלי, נשאר בכל העסקאות", "אלי", E("myName()"), E("myName()") == "אלי" and len(E("dealsReg().list")) == 2)
    pg.evaluate("()=>{dealsOpen=true; render();}"); pg.wait_for_timeout(100); sw = pg.evaluate("()=>document.documentElement.scrollWidth")
    check("M14 360px: בלי גלילה לרוחב עם רשימת העסקאות פתוחה", 360, sw, sw <= 360)
    # S: full sequence A -> B -> change B -> refresh -> delete B -> back to A; migration runs once
    E("localStorage.clear(); const s=exampleState(); s.example=false; s.profile.city='פתח תקווה'; s.profile.price=1600000; s.fin.equity=250000; s.fin.eqCustom=true; localStorage.setItem('maftech.state.v1', JSON.stringify(s));")
    pg.reload(); wait(); pg.reload(); wait(); pg.reload(); wait()
    check("S1 מיגרציה פעם אחת: אחרי 3 רענונים יש עסקה אחת", 1, len(E("dealsReg().list")), len(E("dealsReg().list")) == 1)
    A0 = E(METRICS); aid = E("dealsReg().active")
    E("newDeal();"); E("wiz.d.type='resale'; wiz.d.buyer='first'; wiz.d.city='רמת גן'; wiz.d.price='2400000'; wiz.d.sign='2026-12-01'; wiz.d.delivery='2027-03-01'; wiz.d.savings='900000'; wiz.d.income='30000'; wiz.d.expenses='15000'; wizFinish();"); wait()
    bid = E("dealsReg().active")
    E("S.profile.price=2450000; S.payments.sort((a,b)=>a.date.localeCompare(b.date))[0].paid=true; S.fin.savings=800000; persist();"); pg.wait_for_timeout(150)
    pg.reload(); wait()
    check("S2 אחרי רענון B פעילה עם השינוי", "רמת גן · 2,450,000", f"{E('S.profile.city')} · {E('S.profile.price')}", E("dealsReg().active") == bid and E("S.profile.price") == 2450000)
    pg.reload(); wait()
    check("S3 רענון נוסף לא יוצר עסקה נוספת", 2, len(E("dealsReg().list")), len(E("dealsReg().list")) == 2)
    E(f"deleteDeal('{bid}')"); wait()
    A1 = E(METRICS)
    for k in ["city", "price", "eq", "pays", "paid", "mix", "low", "costs", "drawn"]:
        check(f"S4 אחרי מחיקת B, A זהה: {k}", A0[k], A1[k], A0[k] == A1[k])
    leftovers = E(f"Object.keys(localStorage).filter(k=>k.includes('{bid}'))")
    check("S5 אין שאריות של B ואין עסקה כפולה", "1 עסקה, 0 שאריות", f"{len(E('dealsReg().list'))} / {leftovers}", len(E("dealsReg().list")) == 1 and not leftovers and E("dealsReg().active") == aid and E("S.fin.savings") != 800000)
    pg.reload(); wait()
    check("S6 רענון אחרי מחיקה: עדיין A בלבד, בלי מיגרציה חוזרת", "1 · פתח תקווה", f"{len(E('dealsReg().list'))} · {E('S.profile.city')}", len(E("dealsReg().list")) == 1 and E("S.profile.city") == "פתח תקווה")
    check("שגיאות JavaScript", "אין", errs or "אין", not errs)
    b.close()
for r in R: print(f"{r[3]} | {r[0]} | צפוי: {r[1]} | בפועל: {r[2]}")
print("FAILED" if any(r[3] == "FAIL" for r in R) else "ALL PASS", sum(r[3] == "PASS" for r in R), "/", len(R))
