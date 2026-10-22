"""Regression tests for the red-team round on version 19 (RT01-RT10). Expected numbers are computed here, independently of the app.
Dates are relative to today, so the tests keep working. Usage: python3 test_redteam.py http://localhost:PORT/"""
import sys, datetime
from playwright.sync_api import sync_playwright
B = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8765/"
R = []
def check(name, expected, actual, ok): R.append((name, expected, str(actual), "PASS" if ok else "FAIL"))
def ann(P, r, n): r = r / 1200; return P / n if r == 0 else P * r / (1 - (1 + r) ** -n)
def add_m(d, k): y, m = d.year + (d.month - 1 + k) // 12, (d.month - 1 + k) % 12 + 1; return datetime.date(y, m, d.day)
def ym(d): return d.strftime("%Y-%m")
T0 = datetime.date.today(); SIGN = add_m(T0.replace(day=1), 1); P2, P3 = add_m(SIGN, 2), add_m(SIGN, 4)
ils = lambda v: "₪" + f"{round(v):,}"
# a second-hand deal like the red team's "C": 1,000,000, 15% at signing, 35% two months later, 50% four months later
RESALE = f"""S=newState({{type:'resale',buyer:'first',city:'חיפה',price:1000000,sign:'{SIGN}',delivery:'',linkedShare:0}},false);
 const P=S.payments.sort((a,b)=>a.date.localeCompare(b.date)); P[0].date='{SIGN}'; P[0].pct=15; P[1].date='{P2}'; P[1].pct=35; P[2].date='{P3}'; P[2].pct=50;
 S.fin.savings=300000; S.fin.savTouched=true; S.fin.income=20000; S.fin.expenses=20000; S.fin.expTouched=true; S.fin.rent=0; S.fin.equity=250000; persist();"""
with sync_playwright() as p:
    b = p.chromium.launch(); ctx = b.new_context(viewport={"width": 360, "height": 800}); pg = ctx.new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("dialog", lambda d: d.accept())
    E = lambda js: pg.evaluate("()=>{" + js + "}") if js.strip().endswith(";") else pg.evaluate("()=>(" + js + ")")
    pg.goto(B); pg.wait_for_timeout(800); E("localStorage.clear();"); pg.reload(); pg.wait_for_timeout(800)

    # RT01: a loan source's repayment leaves the cash flow, the same with or without "the bank counts it"
    LOAN_D = SIGN.replace(day=1); LOAN_D = add_m(LOAN_D, 2).replace(day=15)
    def rows(monthly, bank):
        E(RESALE + f"S.fin.sources=[{{id:'l1',name:'גישור',kind:'loan',amount:100000,date:'{LOAN_D}',monthly:{monthly},bank:{str(bank).lower()},inc:true}}]; persist();")
        return E("cashflow().rows.map(r=>({m:r.m,close:r.close,loan:r.loan}))")
    base, r50, r5 = rows(0, False), rows(50000, False), rows(5000, False)
    def exp_diff(m, pay):
        k = sum(1 for x in base if ym(LOAN_D) < x["m"] <= m)
        return min(100000, pay * k)
    ok50 = all(abs((b0["close"] - x["close"]) - exp_diff(x["m"], 50000)) < 1 for b0, x in zip(base, r50))
    m1, m2 = ym(add_m(LOAN_D, 1)), ym(add_m(LOAN_D, 2))
    check("RT01a הלוואה 100,000 בשני החזרים של 50,000: שני חיובים, ואז מפסיק", "‎−50,000 ואז ‎−100,000 מול בלי החזר", [(x["m"], round(b0["close"] - x["close"])) for b0, x in zip(base, r50) if x["m"] in (m1, m2)], ok50 and sum(x["loan"] for x in r50) == 100000)
    ok5 = all(abs((b0["close"] - x["close"]) - exp_diff(x["m"], 5000)) < 1 for b0, x in zip(base, r5))
    check("RT01b החזר 5,000 שונה מ-50,000 ומצטבר חודש בחודש", "5,000 לחודש", round(base[-1]["close"] - r5[-1]["close"]), ok5 and r5[-1]["close"] != r50[-1]["close"])
    rb = rows(50000, True)
    check("RT01c גם כשהבנק סופר את ההלוואה, ההחזר יוצא מהתזרים", "אותם החזרים", [x["loan"] for x in rb if x["loan"]], [x["loan"] for x in rb] == [x["loan"] for x in r50])
    E("go('calc','cash')"); pg.wait_for_timeout(150); E(RESALE + f"S.fin.sources=[{{id:'l1',name:'גישור',kind:'loan',amount:100000,date:'{LOAN_D}',monthly:50000,bank:false,inc:true}}]; persist(); render();"); pg.wait_for_timeout(150)
    E("document.querySelectorAll('details').forEach(d=>d.open=true)"); t = pg.inner_text("#view")
    check("RT01d התזרים מראה את החזר ההלוואה", "החזר הלוואה ממקור נוסף", "מוצג" if "החזר הלוואה ממקור נוסף" in t and "החזר הלוואות" in t else "חסר", "החזר הלוואה ממקור נוסף" in t and "החזר הלוואות" in t)

    # RT02: each draw is repaid for the loan term only (1 year, 0%): 250,000 + 500,000 in 12 payments each, then 0
    DELIV = add_m(SIGN, 26)
    E(RESALE + f"S.profile.delivery='{DELIV}'; S.fin.savings=1100000; S.fin.income=200000; S.fin.expenses=200000; Object.assign(S.mix,{{years:1,pPrime:0,pFixed:100,pLinked:0,pVar:0,rFixed:0,infl:0}}); S.costs={{lawyer:39000,advisor:0,broker:0,appraiser:0,bankfees:0,moving:35000,renovation:0,other:0}}; persist();")
    c = E("(()=>{const c=cashflow();return {rows:c.rows.map(r=>({m:r.m,mort:r.mort,close:r.close})),end:c.end.m,endClose:c.end.close}})()")
    def exp_mort(m):
        v = 0
        for d, a in ((P2, 250000), (P3, 500000)):
            k = (int(m[:4]) * 12 + int(m[5:])) - (d.year * 12 + d.month)
            if 1 <= k <= 12: v += a / 12
        return v
    okm = all(abs(r["mort"] - exp_mort(r["m"])) <= 1 for r in c["rows"])
    check("RT02a החזר כל משיכה נפסק אחרי 12 תשלומים", "סך 750,000, ואחרי זה 0", round(sum(r["mort"] for r in c["rows"])), okm and abs(sum(r["mort"] for r in c["rows"]) - 750000) <= 12 and c["rows"][-1]["mort"] == 0)
    check("RT02b יתרה במסירה: 1,100,000 − 250,000 − 750,000 − 74,000", "26,000", round(c["endClose"]), abs(c["endClose"] - 26000) <= 12 and c["end"] == ym(DELIV))

    # RT03: the payment schedule is checked in every deal type
    E(RESALE + "S.payments.forEach(x=>x.pct=0); persist(); go('home');"); pg.wait_for_timeout(150); t = pg.inner_text("#view")
    check("RT03a יד שנייה, לוח 0%: התזרים והבית חסומים", "חסום, בלי 'מספיק'", E("dealBlockers('cash').length"), E("dealBlockers('cash').length") > 0 and "לא ניתן לחשב" in t)
    E(RESALE + "S.payments.sort((a,b)=>a.date.localeCompare(b.date))[2].date=''; persist(); render();"); pg.wait_for_timeout(100)
    check("RT03b יד שנייה, תשלום בלי תאריך: חסום", "חסום", [x["msg"][:40] for x in E("dealBlockers('cash')")], any("אין תאריך" in x["msg"] for x in E("dealBlockers('cash')")))

    # RT04: paid, then savings updated the same day (through the screens): the payment is not taken out again
    E(RESALE + "S.fin.savings=1100000; persist(); go('buy','payments');"); pg.wait_for_timeout(200)
    pid = E("S.payments.sort((a,b)=>a.date.localeCompare(b.date))[0].id"); first_amt = E("payAmount(S.payments.find(x=>x.id==='" + pid + "'))")
    pg.click(f"[data-paid='{pid}']"); pg.wait_for_timeout(250)
    E("editOpen.eqmoney=true; go('calc','equity');"); pg.wait_for_timeout(200)
    pg.fill("[data-c='fin.savings']", f"{1100000 - first_amt:.0f}"); pg.wait_for_timeout(900)
    r0 = E("cashflow().rows[0]")
    check("RT04a שולם ואז עודכנו החסכונות באותו יום: יציאה אחת", f"{ils(1100000 - first_amt)} בחודש הנוכחי", ils(r0["close"]), abs(r0["close"] - (1100000 - first_amt)) < 1)
    E("go('buy','payments')"); pg.wait_for_timeout(150); pg.click(f"[data-paid='{pid}']"); pg.wait_for_timeout(200)   # unmark
    E("editOpen.eqmoney=true; go('calc','equity');"); pg.wait_for_timeout(150)
    pg.fill("[data-c='fin.savings']", "1100000"); pg.wait_for_timeout(900)
    E("go('buy','payments')"); pg.wait_for_timeout(150); pg.click(f"[data-paid='{pid}']"); pg.wait_for_timeout(250)
    r0 = E("cashflow().rows[0]")
    check("RT04b החסכונות ואז שולם באותו יום: התשלום יוצא פעם אחת", f"{ils(1100000 - first_amt)}", ils(r0["close"]), abs(r0["close"] - (1100000 - first_amt)) < 1)
    pg.reload(); pg.wait_for_timeout(800); r0 = E("cashflow().rows[0]")
    check("RT04c אחרי רענון אותה תוצאה", f"{ils(1100000 - first_amt)}", ils(r0["close"]), abs(r0["close"] - (1100000 - first_amt)) < 1)

    # RT05: a far delivery is reached (or blocked), never cut and called "delivery"
    FAR = add_m(SIGN, 13 * 12 + 2)
    E(RESALE + f"S.profile.delivery='{FAR}'; persist();"); c = E("(()=>{const c=cashflow();return {end:c.end.m,isD:c.endIsDelivery,last:c.last.m}})()")
    check("RT05a מסירה בעוד 13 שנה: התחזית מגיעה אליה", ym(FAR), c, c["end"] == ym(FAR) and c["isD"])
    TOO = add_m(SIGN, 21 * 12)
    E(RESALE + f"S.profile.delivery='{TOO}'; persist(); go('calc','cash');"); pg.wait_for_timeout(150); t = pg.inner_text("#view")
    check("RT05b מסירה מעבר ל-20 שנה: חסום במפורש", "20 שנה", "חסום" if "20 שנה" in t and "לא ניתן לחשב" in t else t[:120], "20 שנה" in t and "לא ניתן לחשב" in t)

    # RT06: in a second-hand deal "first payment" is the draw-based one, the same on every screen
    E(RESALE + "Object.assign(S.mix,{years:25,pPrime:33,pFixed:34,pLinked:33,pVar:0,rPrime:4.75,rFixed:4.62,rLinked:3.29,infl:1.6}); persist(); go('home');"); pg.wait_for_timeout(150)
    d = E("(()=>{const d=drawSteps(),c=cashflow();return {first:d.first,cf:c.rows.find(r=>r.mort>0).mort,full:mortgageCalc(dealFin().bankFunds).first}})()"); t = pg.inner_text("#view")
    exp1 = 250000 * (0.33 * ann(1, 4.75, 300) + 0.34 * ann(1, 4.62, 300) + 0.33 * ann(1, 3.29, 300))
    check("RT06a החזר ראשון = על המשיכה הראשונה בלבד, כמו בתזרים", ils(exp1), f"{ils(d['first'])} · תזרים {ils(d['cf'])}", abs(d["first"] - exp1) < 2 and abs(d["cf"] - d["first"]) < 1)
    check("RT06b הבית מציג את ההחזר לפי המשיכות, לא על כל ההלוואה", ils(d["first"]), "תקין" if ils(d["first"]) in t and "החזר חודשי ראשון" not in t else t[:200], ils(d["first"]) in t and "החזר חודשי ראשון" not in t)
    E("go('calc','mortgage')"); pg.wait_for_timeout(150); t = pg.inner_text("#view")
    check("RT06c מסך המשכנתא: אותו החזר ראשון", ils(d["first"]), "תקין" if ils(d["first"]) in t else "חסר", ils(d["first"]) in t)

    # RT07: other loans are deducted from income (directive 329, appendix A 1.2)
    E("S=newState({type:'resale',buyer:'first',city:'חיפה',price:3000000,sign:'" + str(SIGN) + "',delivery:'',linkedShare:0},false); S.fin.income=20000; S.fin.otherLoans=5000; S.fin.equity=800000; Object.assign(S.mix,{years:25,pPrime:0,pFixed:100,pLinked:0,pVar:0,rFixed:0}); persist();")
    f = E("dealFin()")
    check("RT07 הכנסה פנויה: 50% × (20,000 − 5,000) = 7,500 → תקרה 2,250,000, פער 0", "2,250,000 · 0", f"{round(f['capacity']):,} · {round(f['gap']):,}", abs(f["capacity"] - 2250000) < 1 and f["gap"] < 1)
    check("RT07b יחס ההחזר על ההכנסה הפנויה", "50%", E("Math.round(pti(7500))"), E("Math.round(pti(7500))") == 50)

    # RT08: one assumed key date for a second-hand deal without one, and no 60-day wording
    E(RESALE + "go('calc','cash');"); pg.wait_for_timeout(150); t = pg.inner_text("#view"); c = E("(()=>{const c=cashflow();return {end:c.end.m,after:c.afterDelivery,assumed:c.assumedDelivery}})()")
    check("RT08a בלי מועד מפתח: ההנחה = התשלום האחרון, בכל המקומות", ym(P3), c, c["end"] == ym(P3) and c["after"] == 0 and c["assumed"])
    check("RT08b במסקנה של יד שנייה אין הנחת 60 יום, וההנחה על המפתח כתובה", "בלי 60 יום · 'לא הזנתם מועד קבלת מפתח'", "תקין" if "60 יום" not in t and "לא הזנתם מועד קבלת מפתח" in t else t[:200], "60 יום" not in t and "לא הזנתם מועד קבלת מפתח" in t)

    # RT09 + parser: negative or non-numeric values are rejected with a message, never changed silently
    e1 = E("(()=>{wiz={i:0,d:{savings:'150000',income:'30000',expenses:'-10000'}}; const r=wizValidate('money'); wiz=null; return r})()")
    check("RT09 הוצאה שלילית באשף נחסמת", "הודעה", e1, bool(e1) and "שלילי" in e1)
    e2 = E("checkNum('1e6','money').err || ''")
    check("RT09b '1e6' לא נקרא כ-16", "הודעה", e2, bool(e2))

    # RT10: after "reset this deal" the other saved deals stay reachable
    E("localStorage.clear();"); pg.reload(); pg.wait_for_timeout(700)
    E("startWizard(); wiz.d.type='resale'; wiz.d.buyer='first'; wiz.d.city='חיפה'; wiz.d.price='1000000'; wiz.d.sign='" + str(SIGN) + "'; wiz.d.savings='300000'; wiz.d.income='20000'; wiz.d.expenses='20000'; wizFinish();"); pg.wait_for_timeout(500)
    aid = E("dealsReg().active")
    E("newDeal(); wiz.d.type='resale'; wiz.d.buyer='first'; wiz.d.city='עכו'; wiz.d.price='900000'; wiz.d.sign='" + str(SIGN) + "'; wiz.d.savings='200000'; wiz.d.income='15000'; wiz.d.expenses='9000'; wizFinish();"); pg.wait_for_load_state("load"); pg.wait_for_timeout(800)
    E("setupOpen=true; confirmReset=true; render();"); pg.wait_for_timeout(100); pg.click("[data-act=resetyes]"); pg.wait_for_timeout(200); pg.click("[data-act=wzcancel]"); pg.wait_for_timeout(200)
    pg.reload(); pg.wait_for_timeout(800); t = pg.inner_text("#view")
    check("RT10a אחרי איפוס וביטול: העסקה השמורה מוצגת", "העסקאות השמורות שלכם · חיפה", "תקין" if "העסקאות השמורות שלכם" in t and "חיפה" in t else t[:150], "העסקאות השמורות שלכם" in t and "חיפה" in t)
    pg.click(f"[data-deal='{aid}']"); pg.wait_for_load_state("load"); pg.wait_for_timeout(800)
    st = E("({city:S.profile.city,ex:S.example,n:dealsReg().list.length})")
    check("RT10b מעבר לעסקה השמורה בלי ליצור חדשה; העסקה שאופסה לא נשארת כדוגמה", "חיפה · 1 שמורה", st, st["city"] == "חיפה" and not st["ex"] and st["n"] == 1)

    # ===== round 2 (version 20) =====
    import json as _json, tempfile as _tf, os as _os
    # V20-01: a backup with a value the screens never accept restores as a blocked draft, never as a result
    E("localStorage.clear();"); pg.reload(); pg.wait_for_timeout(700)
    DELIV = add_m(SIGN, 26)
    E(RESALE + f"S.profile.delivery='{DELIV}'; S.fin.savings=1100000; S.fin.income=200000; S.fin.expenses=200000; Object.assign(S.mix,{{years:1,pPrime:0,pFixed:100,pLinked:0,pVar:0,rFixed:0,infl:0}}); persist();")
    good = E("JSON.stringify({app:'maftech',v:1,state:S})")
    def restore(mut):
        j = _json.loads(good); mut(j["state"]); fd, path = _tf.mkstemp(suffix=".json"); _os.write(fd, _json.dumps(j, ensure_ascii=False).encode()); _os.close(fd)
        pg.set_input_files("#restorefile", path); pg.wait_for_timeout(500); _os.unlink(path)
        E("go('home')"); pg.wait_for_timeout(150); return pg.inner_text("#view")
    cases = [("שיפוץ ‎−100,000", lambda s: s["costs"].__setitem__("renovation", -100000)),
             ("ריבית קבועה ‎−5%", lambda s: s["mix"].__setitem__("rFixed", -5)),
             ("אחוז תשלום שלילי", lambda s: s["payments"][0].__setitem__("pct", -15)),
             ("כרית ‎−10", lambda s: s["fin"].__setitem__("reserve", -10)),
             ("הכנסה 'abc'", lambda s: s["fin"].__setitem__("income", "abc"))]
    for name, mut in cases:
        t = restore(mut); bl = E("['cash','costs','mortgage','equity'].map(s=>dealBlockers(s).length)")
        check(f"V20-01 גיבוי עם {name}: הבית וכל המסכים התלויים חסומים", "חסום, בלי 'מספיק'", f"{bl} · {[l for l in t.splitlines() if 'מספיק' in l][:3]}", "מספיק," not in t and "מספיק." not in t and "לא ניתן לחשב" in t and bl[0] > 0 and bl[1] > 0 and (bl[2] > 0 or name in ("שיפוץ ‎−100,000", "אחוז תשלום שלילי", "כרית ‎−10")))
    t = restore(lambda s: None)
    check("V20-01b גיבוי תקין אחריהם: תוצאה תקינה, בלי שאריות", "26,000 במסירה", E("dealBlockers('cash').length") == 0 and round(E("cashflow().end.close")), E("dealBlockers('cash').length") == 0 and abs(E("cashflow().end.close") - 26000) <= 12)

    # V20-02: what is typed in the wizard is never turned into another number
    E("localStorage.clear();"); pg.reload(); pg.wait_for_timeout(700)
    E("startWizard(); Object.assign(wiz.d,{type:'resale',buyer:'first',city:'חיפה',price:'1000000',sign:'" + str(SIGN) + "'}); wiz.i=wizSteps().indexOf('money'); render();"); pg.wait_for_timeout(200)
    for field, typed in (("expenses", "abc10000"), ("savings", "1e6"), ("income", "10k")):
        pg.fill(f"[data-wzf={field}]", ""); pg.type(f"[data-wzf={field}]", typed); pg.wait_for_timeout(100)
        kept = pg.input_value(f"[data-wzf={field}]"); pg.click("[data-act=wznext]"); pg.wait_for_timeout(200)
        err = pg.inner_text(".wzerr") if pg.query_selector(".wzerr") else ""
        check(f"V20-02 אשף: '{typed}' נשאר כמו שהוקלד ונחסם עם הודעה", f"{typed} + הודעה, בלי עסקה", f"{kept} · {err[:40]}", kept == typed and bool(err) and E("!!wiz"))
        pg.fill(f"[data-wzf={field}]", "")
    pg.fill("[data-wzf=expenses]", "abc10000"); pg.click("[data-act=wzfinish]"); pg.wait_for_timeout(200)
    check("V20-02b 'דלג וסיים' לא עוקף את הבדיקה", "הודעה, האשף פתוח", E("!!wiz"), E("!!wiz") and pg.query_selector(".wzerr") is not None)
    pg.fill("[data-wzf=expenses]", ""); pg.type("[data-wzf=expenses]", "12345"); pg.fill("[data-wzf=savings]", ""); pg.type("[data-wzf=savings]", "1234567")
    check("V20-02c מספרים תקינים מקבלים פסיקים", "12,345 · 1,234,567", f"{pg.input_value('[data-wzf=expenses]')} · {pg.input_value('[data-wzf=savings]')}", pg.input_value("[data-wzf=expenses]") == "12,345" and pg.input_value("[data-wzf=savings]") == "1,234,567")
    pg.fill("[data-wzf=income]", "20000"); pg.click("[data-act=wznext]"); pg.wait_for_timeout(400)
    st = E("({w:!!wiz,e:S.fin.expenses,s:S.fin.savings})")
    check("V20-02d עם ערכים תקינים העסקה נוצרת עם המספרים שהוקלדו", "12,345 · 1,234,567", st, not st["w"] and st["e"] == 12345 and st["s"] == 1234567)

    # the other money fields keep what was typed too (equity)
    E(RESALE + "advOpen=true; go('calc','equity');"); pg.wait_for_timeout(200)
    if pg.query_selector_all("[data-c='fin.equity']"):
        pg.fill("[data-c='fin.equity']", ""); pg.type("[data-c='fin.equity']", "abc260000"); pg.wait_for_timeout(300)
        check("V20-02e הון עצמי 'abc260000' לא נשמר כמספר אחר", "נשאר 250,000", E("S.fin.equity"), E("S.fin.equity") == 250000 and pg.input_value("[data-c='fin.equity']") == "abc260000")
    else: check("V20-02e שדה ההון העצמי נמצא", "נמצא", "חסר", False)
    # V20-03: the schedule has to add up to the price to the shekel
    for diff in (1, 99, 100, 101, -1, -100):
        E(RESALE + f"S.payments.forEach((x,i)=>{{x.pct=i===2?50-({diff})/10000:x.pct}}); persist();")
        bl = E("dealBlockers('cash').map(b=>b.msg)")
        check(f"V20-03 לוח שסוטה ב-{diff} ₪ חסום", "חסום", bl[:1], any("לוח התשלומים" in m for m in bl))
    E(RESALE); bl = E("dealBlockers('cash').map(b=>b.msg)")
    check("V20-03b לוח שמסתכם בדיוק במחיר לא חסום", "לא חסום", bl, not any("לוח התשלומים" in m for m in bl))

    check("שגיאות JavaScript", "אין", errs or "אין", not errs)
    b.close()
for r in R: print(f"{r[3]} | {r[0]} | צפוי: {r[1]} | בפועל: {r[2]}")
print("FAILED" if any(r[3] == "FAIL" for r in R) else "ALL PASS", sum(r[3] == "PASS" for r in R), "/", len(R))
