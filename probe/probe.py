import json, requests, re
from playwright.sync_api import sync_playwright
H={"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/130 Safari/537.36"}
D="https://data.gov.il/api/3/action/"
j=requests.get(D+"datastore_search",params={"resource_id":"7c8255d0-49ef-49db-8904-4cf917586031","limit":2},headers=H,timeout=60).json()
print("LOT total",j["result"].get("total"),[f["id"] for f in j["result"]["fields"]]); print(json.dumps(j["result"]["records"],ensure_ascii=False)[:1500])
for qq in ["נדל\"ן","עסקאות","רשות המסים","taxes","nadlan","מכירת דירות","שווי מקרקעין"]:
    try:
        r=requests.get(D+"package_search",params={"q":qq,"rows":8},headers=H,timeout=60).json()["result"]["results"]
        for p in r: print("PKG",qq,"|",p["name"],"|",p["title"],"|",[(x["id"][:8],x.get("format")) for x in p["resources"]][:3])
    except Exception as e: print("EXC",qq,e)
try: print("RES",requests.get(D+"resource_search",params={"query":"id:f41fb496"},headers=H,timeout=60).text[:500])
except Exception as e: print(e)
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_page(user_agent=H["User-Agent"], locale="he-IL")
    def on(resp):
        u=resp.url
        if any(s in u for s in ("google","gstatic","fonts","doubleclick")): return
        rt=resp.request.resource_type
        if rt in ("image","stylesheet","font"): return
        try: body=resp.text()[:400] if rt in("xhr","fetch") else ""
        except Exception: body="?"
        print(" ",rt,resp.status,resp.request.method,u[:300]); 
        if body: print("    REQ:",(resp.request.post_data or "")[:400],"\n    RESP:",body.replace("\n"," "))
    pg.on("response",on)
    pg.goto("https://www.nadlan.gov.il/",timeout=60000); pg.wait_for_timeout(8000)
    html=pg.content(); print("HTML len",len(html)); print(re.sub(r"\s+"," ",pg.inner_text("body"))[:800])
    inputs=pg.query_selector_all("input"); print("INPUTS",[(i.get_attribute("id"),i.get_attribute("placeholder")) for i in inputs])
    try:
        inp=inputs[0]; inp.click(); inp.type("פתח תקווה",delay=120); pg.wait_for_timeout(4000)
        pg.keyboard.press("ArrowDown"); pg.keyboard.press("Enter"); pg.wait_for_timeout(15000)
        print("URL NOW",pg.url); print(re.sub(r"\s+"," ",pg.inner_text("body"))[:1500])
    except Exception as e: print("EXC",e)
    b.close()
