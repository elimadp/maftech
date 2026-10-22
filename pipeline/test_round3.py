"""Regression tests for red-team round 3 on version 21 (RT3-01..RT3-09; RT3-06 is in test_household.mjs).
Through the screens where the finding was in the screens: typing char by char, pasting, restoring a backup file.
Expected numbers are computed here. Dates are relative to today. Usage: python3 test_round3.py http://localhost:PORT/"""
import sys, json, os, tempfile, datetime
from playwright.sync_api import sync_playwright
B = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8765/"
R = []
def check(name, expected, actual, ok): R.append((name, expected, str(actual), "PASS" if ok else "FAIL"))
def add_m(d, k): y, m = d.year + (d.month - 1 + k) // 12, (d.month - 1 + k) % 12 + 1; return datetime.date(y, m, d.day)
ym = lambda d: d.strftime("%Y-%m")
T0 = datetime.date.today(); SIGN = add_m(T0.replace(day=1), 1); P2, P3, DELIV = add_m(SIGN, 2), add_m(SIGN, 4), add_m(SIGN, 26)
# B0: second-hand, 1,000,000; savings 1,100,000; equity 250,000; income = expenses = 200,000; 1 year at 0%; costs 39,000 + 35,000 -> 26,000 at delivery
B0 = f"""S=newState({{type:'resale',buyer:'first',city:'חיפה',price:1000000,sign:'{SIGN}',delivery:'{DELIV}',linkedShare:0}},false);
 const P=S.payments.sort((a,b)=>a.date.localeCompare(b.date)); P[0].date='{SIGN}'; P[0].pct=15; P[1].date='{P2}'; P[1].pct=35; P[2].date='{P3}'; P[2].pct=50;
 S.fin.savings=1100000; S.fin.savTouched=true; S.fin.income=200000; S.fin.expenses=200000; S.fin.expTouched=true; S.fin.equity=250000;
 Object.assign(S.mix,{{years:1,pPrime:0,pFixed:100,pLinked:0,pVar:0,rFixed:0,infl:0}}); S.costs={{lawyer:39000,advisor:0,broker:0,appraiser:0,bankfees:0,moving:35000,renovation:0,other:0}}; persist();"""
with sync_playwright() as p:
    b = p.chromium.launch(); ctx = b.new_context(viewport={"width": 360, "height": 800}); pg = ctx.new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("dialog", lambda d: d.accept())
    E = lambda js: pg.evaluate("()=>{" + js + "}") if js.strip().endswith(";") else pg.evaluate("()=>(" + js + ")")
    def fresh(): E("localStorage.clear();"); pg.reload(); pg.wait_for_timeout(700)
    def restore_json(state):
        fd, path = tempfile.mkstemp(suffix=".json"); os.write(fd, json.dumps({"app": "maftech", "v": 1, "state": state}, ensure_ascii=False).encode()); os.close(fd)
        pg.set_input_files("#restorefile", path); pg.wait_for_timeout(600); os.unlink(path)
    pg.goto(B); pg.wait_for_timeout(800); fresh()
    E(B0); GOOD = E("JSON.parse(JSON.stringify(S))")
    def bad(mut):
        s = json.loads(json.dumps(GOOD)); mut(s); restore_json(s); E("go('home')"); pg.wait_for_timeout(150)
        return pg.inner_text("#view"), E("['cash','costs','mortgage','equity','home'].map(s=>dealBlockers(s).length)")

    # RT3-01: agorot typed char by char or pasted are kept, never shifted into shekels
    fresh()
    E("startWizard(); Object.assign(wiz.d,{type:'resale',buyer:'first',city:'חיפה',price:'2000000',sign:'" + str(SIGN) + "'}); wiz.i=wizSteps().indexOf('money'); render();"); pg.wait_for_timeout(200)
    for typed, shown, val in (("350000.75", "350,000.75", 350000.75), ("0.01", "0.01", 0.01), ("1.00", "1.00", 1.0)):
        pg.fill("[data-wzf=savings]", ""); pg.type("[data-wzf=savings]", typed, delay=15); pg.wait_for_timeout(80)
        check(f"RT3-01 אשף, הקלדה תו-תו '{typed}'", shown, pg.input_value("[data-wzf=savings]"), pg.input_value("[data-wzf=savings]") == shown and E("wiz.d.savings").replace(",", "") == shown.replace(",", ""))
    pg.fill("[data-wzf=savings]", "350000.75")
    check("RT3-01b אשף, הדבקה '350000.75'", "350000.75", pg.input_value("[data-wzf=savings]"), pg.input_value("[data-wzf=savings]").replace(",", "") == "350000.75")
    pg.fill("[data-wzf=savings]", ""); pg.type("[data-wzf=savings]", "350000.75", delay=15)
    for f, v in (("income", "30000"), ("expenses", "18000"), ("rent", "4000")):
        if pg.query_selector(f"[data-wzf={f}]"): pg.fill(f"[data-wzf={f}]", v)
    pg.click("[data-act=wznext]"); pg.wait_for_timeout(500); pg.reload(); pg.wait_for_timeout(800)
    check("RT3-01c אחרי סיום ורענון החסכונות 350,000.75", 350000.75, E("S.fin.savings"), abs(E("S.fin.savings") - 350000.75) < 1e-6)
    E("editOpen.eqmoney=true; go('calc','equity');"); pg.wait_for_timeout(200)
    pg.fill("[data-c='fin.savings']", ""); pg.type("[data-c='fin.savings']", "420000.5", delay=15); pg.wait_for_timeout(700)
    check("RT3-01d טופס רגיל: '420000.5' נשמר כמו שהוקלד", 420000.5, E("S.fin.savings"), abs(E("S.fin.savings") - 420000.5) < 1e-6)

    # RT3-02: a deal restored on a fresh install is kept when the next deal is created
    fresh(); restore_json(GOOD); pg.wait_for_timeout(200)
    E("editOpen.eqinc=true; go('calc','cash');"); pg.wait_for_timeout(200)
    if pg.query_selector("[data-c='fin.rent']"): pg.fill("[data-c='fin.rent']", "1234"); pg.wait_for_timeout(700)
    first = E("({city:S.profile.city,price:S.profile.price,rent:S.fin.rent,end:Math.round(cashflow().end.close)})"); aid = E("(dealsReg()||{}).active")
    E("newDeal(); Object.assign(wiz.d,{type:'resale',buyer:'first',city:'עכו',price:'900000',sign:'" + str(SIGN) + "',savings:'200000',income:'15000',expenses:'9000'}); wizFinish();"); pg.wait_for_load_state("load"); pg.wait_for_timeout(800)
    reg = E("dealsReg()")
    check("RT3-02a שחזור בהתקנה חדשה ואז עסקה חדשה: שתי עסקאות", 2, len(reg["list"]), len(reg["list"]) == 2 and aid and any(x["id"] == aid for x in reg["list"]))
    pg.reload(); pg.wait_for_timeout(700)
    if aid: pg.click(".dealpick"); pg.wait_for_timeout(150); pg.click(f"[data-deal='{aid}']"); pg.wait_for_load_state("load"); pg.wait_for_timeout(800)
    back = E("({city:S.profile.city,price:S.profile.price,rent:S.fin.rent,end:Math.round(cashflow().end.close)})")
    check("RT3-02b חזרה לעסקה ששוחזרה: הכול כמו לפני", first, back, back == first and first["rent"] == 1234)

    # RT3-03 / RT3-04 / RT3-08 / RT3-09: backups with numbers as text, missing values, impossible dates, negative paid linkage, fractional years
    fresh()
    s = json.loads(json.dumps(GOOD)); s["fin"]["savings"] = "1100000"; restore_json(s)
    check("RT3-03 חסכונות כטקסט '1100000': מומר למספר, יתרה 26,000", "26,000, מספר", E("[typeof S.fin.savings, Math.round(cashflow().end.close)]"), E("typeof S.fin.savings") == "number" and abs(E("cashflow().end.close") - 26000) <= 12)
    cases = [("הוצאות null", lambda s: s["fin"].__setitem__("expenses", None)), ("שיפוץ null", lambda s: s["costs"].__setitem__("renovation", None)),
             ("ריבית ריקה", lambda s: s["mix"].__setitem__("rFixed", "")), ("paidLink שלילי", lambda s: (s["payments"][0].__setitem__("paid", True), s["payments"][0].__setitem__("paidLink", -100000))),
             ("תאריך 2027-99-99", lambda s: s["payments"][2].__setitem__("date", "2027-99-99")), ("תקופה 1.5 שנים", lambda s: s["mix"].__setitem__("years", 1.5)),
             ("ריבית 'NaN'", lambda s: s["mix"].__setitem__("rFixed", "NaN")), ("חסכונות 1e100", lambda s: s["fin"].__setitem__("savings", 1e100))]
    for name, mut in cases:
        t, bl = bad(mut)
        dep = bl[0] > 0 and (bl[2] > 0 if name in ("ריבית ריקה", "תקופה 1.5 שנים", "ריבית 'NaN'") else True)
        check(f"RT3-04 גיבוי עם {name}: חסום", "חסום, בלי מסקנת מספיק", bl, dep and "מספיק," not in t and "מספיק." not in t and "לא ניתן לחשב" in t)
    t, bl = bad(lambda s: (s["payments"][0].__setitem__("pct", -15), s["payments"][1].__setitem__("pct", 65)))
    check("RT3-08 אחוז תשלום שלילי: כרטיס 'הדבר הבא' מבקש תיקון, בלי סכום שלילי", "לוח התשלומים צריך תיקון", "תקין" if "לוח התשלומים צריך תיקון" in t and "150,000" not in t else t[:200], "לוח התשלומים צריך תיקון" in t and "150,000" not in t)
    restore_json(GOOD); E("go('home')"); pg.wait_for_timeout(150)
    check("RT3-04b גיבוי תקין אחרי הפגומים: 26,000, בלי שאריות", 26000, round(E("cashflow().end.close")), E("dealBlockers('cash').length") == 0 and abs(E("cashflow().end.close") - 26000) <= 12)

    # RT3-05: money that arrives after delivery but before the last payment is in the forecast
    D2, P3b = add_m(SIGN, 3), add_m(SIGN, 5)
    E(B0 + f"S.profile.delivery='{D2}'; S.payments.sort((a,b)=>a.date.localeCompare(b.date))[2].date='{P3b}'; S.fin.sources=[{{id:'a1',name:'קרן',kind:'asset',amount:100000,now:0,date:'{P3b}',inc:true}}]; persist();")
    with_src = E(f"cashflow().rows.find(r=>r.m==='{ym(P3b)}')")
    E("S.fin.sources=[]; persist();"); without = E(f"cashflow().rows.find(r=>r.m==='{ym(P3b)}')")
    check("RT3-05 מקור שמגיע אחרי המסירה ולפני התשלום האחרון נכנס בחודש שלו", "+100,000", round(with_src["close"] - without["close"]), with_src["src"] == 100000 and round(with_src["close"] - without["close"]) == 100000)

    # RT3-07: day 60 after signing is the day the bank can start, in the text and in the calculation (59 own / 60 and 61 bank)
    for day, bank in ((59, False), (60, True), (61, True)):
        d = SIGN + datetime.timedelta(days=day)
        E(f"S=newState({{type:'new',buyer:'first',city:'רמת גן',price:1000000,sign:'{SIGN}',delivery:'{add_m(SIGN, 30)}',linkedShare:0}},false); S.payments=[{{id:'a',name:'חתימה',date:'{SIGN}',pct:15,linked:false,paid:false}},{{id:'b',name:'שני',date:'{d}',pct:35,linked:false,paid:false}},{{id:'c',name:'שלישי',date:'{add_m(SIGN, 4)}',pct:50,linked:false,paid:false}}]; S.fin.savings=1100000; S.fin.savTouched=true; S.fin.income=20000; S.fin.expenses=20000; S.fin.expTouched=true; S.fin.equity=250000; S.fin.bankEarly=false; persist();")
        al = E("payAlloc().map(a=>Math.round(a.bank))")
        check(f"RT3-07 תשלום ביום {day} אחרי החתימה: {'הבנק מממן' if bank else 'מהכיס'}", "bank>0" if bank else "bank=0", al[1], (al[1] > 0) == bank and (al[1] == 250000 if bank else al[1] == 0))
    E("go('calc','cash')"); pg.wait_for_timeout(150); E("document.querySelectorAll('details').forEach(d=>d.open=true)")
    lim = E("fmtDate(addDays(S.profile.sign,60))"); t = pg.inner_text("#view")
    check("RT3-07b הטקסט מציג את אותו יום (60) שהחישוב משתמש בו", lim, "תקין" if ("מ-" + lim) in t else "חסר", ("מ-" + lim) in t)

    check("שגיאות JavaScript", "אין", errs or "אין", not errs)
    b.close()
for r in R: print(f"{r[3]} | {r[0]} | צפוי: {r[1]} | בפועל: {r[2]}")
print("FAILED" if any(r[3] == "FAIL" for r in R) else "ALL PASS", sum(r[3] == "PASS" for r in R), "/", len(R))
