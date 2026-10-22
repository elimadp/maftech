"""Regression tests for red-team round 4 on version 22 (RT22-01..04, N15, same-field sync conflict).
Backups go through the real restore button; expected numbers are computed here. Usage: python3 test_round4.py http://localhost:PORT/"""
import sys, json, os, tempfile, datetime
from playwright.sync_api import sync_playwright
B = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8765/"
R = []
def check(name, expected, actual, ok): R.append((name, expected, str(actual), "PASS" if ok else "FAIL"))
def add_m(d, k): y, m = d.year + (d.month - 1 + k) // 12, (d.month - 1 + k) % 12 + 1; return datetime.date(y, m, d.day)
T0 = datetime.date.today(); SIGN = add_m(T0.replace(day=1), 1); P2, P3, DELIV = add_m(SIGN, 2), add_m(SIGN, 4), add_m(SIGN, 26); LOAN_D = add_m(SIGN, 2).replace(day=15)
B0 = f"""S=newState({{type:'resale',buyer:'first',city:'חיפה',price:1000000,sign:'{SIGN}',delivery:'{DELIV}',linkedShare:0}},false);
 const P=S.payments.sort((a,b)=>a.date.localeCompare(b.date)); P[0].date='{SIGN}'; P[0].pct=15; P[1].date='{P2}'; P[1].pct=35; P[2].date='{P3}'; P[2].pct=50;
 S.fin.savings=1100000; S.fin.savTouched=true; S.fin.income=200000; S.fin.expenses=200000; S.fin.expTouched=true; S.fin.equity=250000;
 Object.assign(S.mix,{{years:1,pPrime:0,pFixed:100,pLinked:0,pVar:0,rFixed:0,infl:0}}); S.costs={{lawyer:39000,advisor:0,broker:0,appraiser:0,bankfees:0,moving:35000,renovation:0,other:0}}; persist();"""
with sync_playwright() as p:
    b = p.chromium.launch(); ctx = b.new_context(viewport={"width": 360, "height": 800}); pg = ctx.new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("dialog", lambda d: d.accept())
    E = lambda js: pg.evaluate("()=>{" + js + "}") if js.strip().endswith(";") else pg.evaluate("()=>(" + js + ")")
    def restore(state):
        fd, path = tempfile.mkstemp(suffix=".json"); os.write(fd, json.dumps({"app": "maftech", "v": 1, "state": state}, ensure_ascii=False).encode()); os.close(fd)
        pg.set_input_files("#restorefile", path); pg.wait_for_timeout(600); os.unlink(path); E("go('home')"); pg.wait_for_timeout(150)
        return pg.inner_text("#view")
    blocked = lambda t: "מספיק," not in t and "מספיק." not in t and "לא ניתן לחשב" in t
    pg.goto(B); pg.wait_for_timeout(800); E("localStorage.clear();"); pg.reload(); pg.wait_for_timeout(700)
    E(B0); GOOD = E("JSON.parse(JSON.stringify(S))")
    def variant(mut): s = json.loads(json.dumps(GOOD)); mut(s); return s

    # RT22-01: a required value that is missing from the backup stays missing (asked for), never filled with a default
    t = restore(variant(lambda s: s["fin"].pop("expenses")))
    check("RT22-01a גיבוי בלי הוצאות (expTouched=true): חסום, ההוצאות חסרות", "חסום · null", E("S.fin.expenses"), blocked(t) and E("S.fin.expenses") is None and E("dealBlockers('cash').length") > 0)
    t = restore(variant(lambda s: s["mix"].pop("years")))
    check("RT22-01b גיבוי בלי תקופת משכנתא: חסום, לא 25 שנה", "חסום · null", E("S.mix.years"), blocked(t) and E("S.mix.years") is None and E("dealBlockers('mortgage').length") > 0)
    t = restore(variant(lambda s: s["costs"].pop("renovation")))
    check("RT22-01c גיבוי בלי עלות שיפוץ: חסום", "חסום", E("dealBlockers('costs').length"), blocked(t) and E("dealBlockers('costs').length") > 0)
    t = restore(variant(lambda s: s["costs"].pop("other")))
    check("RT22-01d עלות 'אחר' חסרה (גרסה ישנה): ממולאת 0 במפורש, לא חוסמת", "26,000", round(E("cashflow().end.close")), not blocked(t) and abs(E("cashflow().end.close") - 26000) <= 12)
    restore(GOOD)
    check("RT22-01e שחזור תקין אחרי זה: 26,000", 26000, round(E("cashflow().end.close")), E("dealBlockers('cash').length") == 0 and abs(E("cashflow().end.close") - 26000) <= 12)

    # RT22-02: a counted loan without its repayment is blocked; 0 entered explicitly means no repayment
    loan = lambda **kw: [dict({"id": "l1", "name": "גישור", "kind": "loan", "amount": 100000, "date": str(LOAN_D), "inc": True, "bank": False}, **kw)]
    t = restore(variant(lambda s: s["fin"].__setitem__("sources", loan())))
    check("RT22-02a הלוואה כלולה בלי החזר חודשי: חסום", "חסום", E("dealBlockers('cash').map(b=>b.msg)")[:1], blocked(t) and any("החזר חודשי של הלוואה חסר" in m for m in E("dealBlockers('cash').map(b=>b.msg)")))
    t = restore(variant(lambda s: s["fin"].__setitem__("sources", loan(monthly=None))))
    check("RT22-02b החזר null: חסום", "חסום", blocked(t), blocked(t))
    restore(variant(lambda s: s["fin"].__setitem__("sources", loan(monthly=50000))))
    check("RT22-02c עם החזר 50,000: 100,000 נכנסים ויוצאים, יתרה 26,000", 26000, round(E("cashflow().end.close")), abs(E("cashflow().end.close") - 26000) <= 12)

    # RT22-03: flags are booleans; "false" is false, "true" is true, anything else is blocked
    gift = lambda inc: [{"id": "g1", "name": "מתנה", "kind": "asset", "amount": 100000, "date": str(LOAN_D), "now": 0, "inc": inc, "bank": False}]
    restore(variant(lambda s: s["fin"].__setitem__("sources", gift("false"))))
    E("editOpen.eqmoney=true; go('calc','equity');"); pg.wait_for_timeout(200)
    box = pg.query_selector("[data-srcchk='g1:inc']")
    check("RT22-03a inc='false': לא נכלל, התיבה לא מסומנת, יתרה 26,000", "false · 26,000", f"{E('S.fin.sources[0].inc')} · {round(E('cashflow().end.close'))}", E("S.fin.sources[0].inc") is False and box is not None and not box.is_checked() and abs(E("cashflow().end.close") - 26000) <= 12)
    restore(variant(lambda s: s["fin"].__setitem__("sources", gift("true"))))
    check("RT22-03b inc='true': נכלל, יתרה 126,000", 126000, round(E("cashflow().end.close")), E("S.fin.sources[0].inc") is True and abs(E("cashflow().end.close") - 126000) <= 12)
    t = restore(variant(lambda s: s["fin"].__setitem__("sources", gift({"x": 1}))))
    check("RT22-03c inc=אובייקט: חסום", "חסום", blocked(t), blocked(t))
    restore(variant(lambda s: s["payments"][0].__setitem__("paid", "false")))
    check("RT22-03d paid='false': לא שולם", False, E("S.payments.find(x=>x.date==='" + str(SIGN) + "').paid"), E("S.payments.find(x=>x.date==='" + str(SIGN) + "').paid") is False)

    # RT22-04: an unbalanced schedule replaces the next-payment card with a request to fix it
    for diff in (1, -1, 100, -101):
        restore(variant(lambda s, d=diff: s["payments"][2].__setitem__("pct", 50 + d / 10000)))
        t = pg.inner_text("#view")
        check(f"RT22-04 לוח שסוטה ב-{diff} ₪: כרטיס הבית מבקש תיקון", "לוח התשלומים צריך תיקון", "תקין" if "לוח התשלומים צריך תיקון" in t and "הדבר הבא" not in t else t[:160], "לוח התשלומים צריך תיקון" in t and "הדבר הבא" not in t)

    # N15: old data, "paid" and savings updated on the same day without times: ask, then compute by the answer
    def legacy(s):
        s["fin"]["savings"] = 950000; s["fin"]["savingsAt"] = str(T0); s["fin"].pop("savingsTs", None)
        x = [y for y in s["payments"] if y["date"] == str(SIGN)][0]; x.update({"paid": True, "paidOn": str(T0), "paidAmt": 150000, "paidLink": 0}); x.pop("paidTs", None)
    restore(variant(legacy)); E("go('calc','cash')"); pg.wait_for_timeout(200); t = pg.inner_text("#view")
    check("N15a סדר לא ידוע: התזרים חסום ומוצגת שאלה", "שאלה + חסום", "תקין" if "שאלה אחת לפני החישוב" in t and "לא ניתן לחשב" in t else t[:160], "שאלה אחת לפני החישוב" in t and "לא ניתן לחשב" in t)
    pg.click("[data-act=savorder][data-v=after]"); pg.wait_for_timeout(300)
    r = E("(()=>{const c=cashflow();return [Math.round(c.rows[0].close),Math.round(c.end.close)]})()")
    check("N15b 'אחרי התשלום': מתחילים ב-950,000, מסיימים ב-26,000", "[950000, 26000]", r, r[0] == 950000 and abs(r[1] - 26000) <= 12)
    pg.reload(); pg.wait_for_timeout(800); r2 = E("(()=>{const c=cashflow();return [Math.round(c.rows[0].close),Math.round(c.end.close)]})()")
    check("N15c התשובה נשמרת אחרי רענון", r, r2, r2 == r and E("savOrderOpen().length") == 0)
    restore(variant(legacy)); E("go('calc','cash')"); pg.wait_for_timeout(200); pg.click("[data-act=savorder][data-v=before]"); pg.wait_for_timeout(300)
    r = E("(()=>{const c=cashflow();return [Math.round(c.rows[0].close),Math.round(c.end.close)]})()")
    check("N15d 'לפני התשלום': מתחילים ב-800,000, מסיימים ב-‎−124,000", "[800000, -124000]", r, r[0] == 800000 and abs(r[1] + 124000) <= 12)

    # same field changed on both phones: this phone's value is kept and the person is told what the other phone had
    res = E("(()=>{mergeConflicts=[]; const m=mergeState({fin:{income:20000,expenses:1}},{fin:{income:25000,expenses:1}},{fin:{income:30000,expenses:2}}); const n=mergeConflicts.length; conflictNote(); return {inc:m.fin.income,exp:m.fin.expenses,n,toast:document.getElementById('toast').textContent}})()")
    pg.wait_for_timeout(50); res["toast"] = pg.evaluate("document.getElementById('toast').textContent")
    check("SYNC שני הטלפונים שינו הכנסה: נשמר המקומי, מודיעים מה היה בשני; שדה שהשתנה רק בצד אחד נלקח ממנו", "25,000 · הוצאות 2 · הודעה עם 30,000", res, res["inc"] == 25000 and res["exp"] == 2 and res["n"] == 1 and "30,000" in res["toast"] and "הכנסה" in res["toast"])

    check("שגיאות JavaScript", "אין", errs or "אין", not errs)
    b.close()
for r in R: print(f"{r[3]} | {r[0]} | צפוי: {r[1]} | בפועל: {r[2]}")
print("FAILED" if any(r[3] == "FAIL" for r in R) else "ALL PASS", sum(r[3] == "PASS" for r in R), "/", len(R))
