"""Regression tests for red-team round 5 on version 23 (RT23-01, RT23-02). Usage: python3 test_round5.py http://localhost:PORT/"""
import sys, json, os, tempfile, datetime
from playwright.sync_api import sync_playwright
B = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8765/"
R = []
def check(name, expected, actual, ok): R.append((name, expected, str(actual), "PASS" if ok else "FAIL"))
def add_m(d, k): y, m = d.year + (d.month - 1 + k) // 12, (d.month - 1 + k) % 12 + 1; return datetime.date(y, m, d.day)
T0 = datetime.date.today(); SIGN = add_m(T0.replace(day=1), 1); P2, P3, DELIV = add_m(SIGN, 2), add_m(SIGN, 4), add_m(SIGN, 26)
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
        pg.set_input_files("#restorefile", path); pg.wait_for_timeout(600); os.unlink(path)
    rows = lambda: E("(()=>{const c=cashflow();return [Math.round(c.rows[0].close),Math.round(c.end.close)]})()")
    pg.goto(B); pg.wait_for_timeout(800); E("localStorage.clear();"); pg.reload(); pg.wait_for_timeout(700)
    E(B0); GOOD = E("JSON.parse(JSON.stringify(S))")

    # RT23-01: one same-day payment without a time, another with a known time; the answer changes only the unknown one
    ts_sav = int(datetime.datetime.combine(T0, datetime.time(9)).timestamp() * 1000); ts_pay2 = ts_sav - 3600_000
    def mixed(s):
        s["fin"].update({"savings": 600000, "savingsAt": str(T0), "savingsTs": ts_sav})
        ps = sorted(s["payments"], key=lambda x: x["date"])
        ps[0].update({"paid": True, "paidOn": str(T0), "paidAmt": 150000, "paidLink": 0}); ps[0].pop("paidTs", None)
        ps[1].update({"paid": True, "paidOn": str(T0), "paidAmt": 350000, "paidLink": 0, "paidTs": ts_pay2})
    st = json.loads(json.dumps(GOOD)); mixed(st)
    restore(st); E("go('calc','cash')"); pg.wait_for_timeout(200); t = pg.inner_text("#view")
    check("RT23-01a השאלה מתייחסת רק לתשלום בלי השעה", "שאלה על 'חתימה' בלבד", E("savOrderOpen().map(x=>x.paidAmt)"), "שאלה אחת לפני החישוב" in t and E("savOrderOpen().map(x=>x.paidAmt)") == [150000])
    pg.click("[data-act=savorder][data-v=after]"); pg.wait_for_timeout(300); r = rows()
    keep = E(f"({{sts:S.fin.savingsTs, p2:S.payments.find(x=>x.paidAmt===350000).paidTs}})")
    check("RT23-01b 'אחרי התשלום': 600,000 היום, ‎−224,000 בסוף", "[600000, -224000]", r, r == [600000, -224000])
    check("RT23-01c החותמות האמיתיות לא שונו", f"{ts_sav} · {ts_pay2}", keep, keep["sts"] == ts_sav and keep["p2"] == ts_pay2)
    pg.reload(); pg.wait_for_timeout(800)
    check("RT23-01d אחרי רענון: אותה תוצאה, בלי שאלה", "[600000, -224000]", rows(), rows() == [600000, -224000] and E("savOrderOpen().length") == 0)
    st = json.loads(json.dumps(GOOD)); mixed(st); restore(st); E("go('calc','cash')"); pg.wait_for_timeout(200)
    pg.click("[data-act=savorder][data-v=before]"); pg.wait_for_timeout(300); r = rows()
    check("RT23-01e 'לפני התשלום': רק החתימה יורדת שוב: 450,000 היום, ‎−374,000 בסוף", "[450000, -374000]", r, r == [450000, -374000])
    backup = E("JSON.parse(JSON.stringify(S))"); restore(backup); E("go('calc','cash')"); pg.wait_for_timeout(200)
    check("RT23-01f גיבוי ושחזור אחרי התשובה: אותה תוצאה, בלי שאלה", "[450000, -374000]", rows(), rows() == [450000, -374000] and E("savOrderOpen().length") == 0)
    # two payments without a time, answered once; then a new savings amount typed later is judged on its own (both already paid)
    def two(s):
        s["fin"].update({"savings": 600000, "savingsAt": str(T0)}); s["fin"].pop("savingsTs", None)
        for x, a in zip(sorted(s["payments"], key=lambda x: x["date"])[:2], (150000, 350000)): x.update({"paid": True, "paidOn": str(T0), "paidAmt": a, "paidLink": 0}); x.pop("paidTs", None)
    st = json.loads(json.dumps(GOOD)); two(st); restore(st); E("go('calc','cash')"); pg.wait_for_timeout(200)
    check("RT23-01g שני תשלומים בלי שעה: שאלה אחת על שניהם", "[150000, 350000]", E("savOrderOpen().map(x=>x.paidAmt)"), E("savOrderOpen().map(x=>x.paidAmt)") == [150000, 350000])
    import unicodedata; t = "".join(c for c in pg.inner_text("#savorder") if unicodedata.category(c) != "Cf").replace("\u00a0", " ")
    check("RT24-02a שאלה נפרדת לכל תשלום, עם החלק שיוצא מהחסכונות", "350,000 · מהם 100,000 מהחסכונות", "תקין" if "מהם ₪100,000 מהחסכונות" in t and len(pg.query_selector_all("#savorder [data-v=after]")) == 2 else repr(t[-300:]), "מהם ₪100,000 מהחסכונות" in t and len(pg.query_selector_all("#savorder [data-v=after]")) == 2 and "₪500,000" not in t)
    while pg.query_selector("[data-act=savorder][data-v=after]"): pg.click("[data-act=savorder][data-v=after]"); pg.wait_for_timeout(250)
    check("RT23-01h 'אחרי' על שניהם: 600,000 היום, ‎−224,000", "[600000, -224000]", rows(), rows() == [600000, -224000])
    st = json.loads(json.dumps(GOOD)); two(st); restore(st); E("go('calc','cash')"); pg.wait_for_timeout(200)
    ids = E("savOrderOpen().map(x=>x.id)"); pg.click(f"[data-act=savorder][data-id='{ids[0]}'][data-v=before]"); pg.wait_for_timeout(250); pg.click(f"[data-act=savorder][data-id='{ids[1]}'][data-v=after]"); pg.wait_for_timeout(250)
    check("RT24-02b היתרה בין שני התשלומים (הראשון עוד לא ירד, השני כבר ירד): 450,000 / ‎−374,000", "[450000, -374000]", rows(), rows() == [450000, -374000])
    st = json.loads(json.dumps(GOOD)); two(st); restore(st); E("go('calc','cash')"); pg.wait_for_timeout(200)
    while pg.query_selector("[data-act=savorder][data-v=before]"): pg.click("[data-act=savorder][data-v=before]"); pg.wait_for_timeout(250)
    check("RT24-02c 'עוד לא' על שניהם: 350,000 / ‎−474,000 (הפרש 250,000 מהחסכונות)", "[350000, -474000]", rows(), rows() == [350000, -474000])
    # RT24-01: data saved by version 23's answer (times 1 and 2) is not trusted: the order is asked again
    for ans, exp in (("after", [600000, -224000]), ("before", [350000, -474000])):
        st = json.loads(json.dumps(GOOD)); mixed(st); st["fin"]["savingsTs"] = 2 if ans == "after" else 1
        [x for x in st["payments"] if x.get("paidAmt") == 150000][0]["paidTs"] = 1 if ans == "after" else 2
        restore(st); E("go('calc','cash')"); pg.wait_for_timeout(200)
        q = E("savOrderOpen().map(x=>x.paidAmt)"); t = pg.inner_text("#view")
        check(f"RT24-01a נתון מגרסה 23 ({ans}): החותמות 1/2 הוסרו, שואלים על שני התשלומים, התזרים חסום", "[150000, 350000] · חסום", f"{q} · sTs={E('S.fin.savingsTs')}", sorted(q) == [150000, 350000] and E("S.fin.savingsTs") is None and "לא ניתן לחשב" in t)
        while pg.query_selector(f"[data-act=savorder][data-v={ans}]"): pg.click(f"[data-act=savorder][data-v={ans}]"); pg.wait_for_timeout(250)
        check(f"RT24-01b אחרי התשובה '{ans}' על שניהם", str(exp), rows(), rows() == exp)
        pg.reload(); pg.wait_for_timeout(800)
        check(f"RT24-01c אחרי רענון: אותה תוצאה, בלי שאלה ({ans})", str(exp), rows(), rows() == exp and E("savOrderOpen().length") == 0)
    E("editOpen.eqmoney=true; go('calc','equity');"); pg.wait_for_timeout(200); pg.fill("[data-c='fin.savings']", "590000"); pg.wait_for_timeout(700)
    check("RT23-01i עדכון חסכונות אחרי שהתשלומים כבר סומנו: בלי שאלה, 590,000 היום", 590000, rows()[0], rows()[0] == 590000 and E("savOrderOpen().length") == 0)

    # RT23-02: an edit made while a shared save is in flight is kept on top of what was merged (the other phone's change survives)
    res = pg.evaluate("""async () => {
      const b0 = clone(S); b0.profile.price = 1000000; b0.fin.income = 20000; b0.fin.rent = 5000;
      let server = JSON.stringify(Object.assign(clone(b0), { fin: Object.assign(clone(b0.fin), { income: 25000 }) }));   // phone B already saved income 25,000
      const writes = []; let release; const gate = new Promise(r => release = r); let first = true;
      const prevShared = store.shared; store.shared = { get: async () => ({ exists: true, data: () => ({ state: server, updatedAt: 'v' }) }),
        set: async v => { if (first) { first = false; await gate; } server = v.state; writes.push(JSON.parse(v.state)); } };
      S = clone(b0); S.profile.price = 1200000; setBase(clone(b0)); dirty = true; saving = false;
      const f1 = flush();
      await new Promise(r => setTimeout(r, 50));
      S.fin.rent = 6000; dirty = true;                       // A keeps editing while the first save waits
      release(); await f1; await new Promise(r => setTimeout(r, 50)); if (dirty && !saving) await flush();
      const last = writes[writes.length - 1]; const out = { writes: writes.length, price: last.profile.price, income: last.fin.income, rent: last.fin.rent, sIncome: S.fin.income, sRent: S.fin.rent };
      store.shared = prevShared; return out; }""")
    check("RT23-02 עריכה בזמן שמירה: מחיר 1,200,000, הכנסה 25,000 (מהטלפון השני), שכירות 6,000", "1200000 · 25000 · 6000", res, res["price"] == 1200000 and res["income"] == 25000 and res["rent"] == 6000 and res["sIncome"] == 25000 and res["sRent"] == 6000 and res["writes"] == 2)

    check("שגיאות JavaScript", "אין", errs or "אין", not errs)
    b.close()
for r in R: print(f"{r[3]} | {r[0]} | צפוי: {r[1]} | בפועל: {r[2]}")
print("FAILED" if any(r[3] == "FAIL" for r in R) else "ALL PASS", sum(r[3] == "PASS" for r in R), "/", len(R))
