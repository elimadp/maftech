import json, requests, sys
from playwright.sync_api import sync_playwright
H={"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/130 Safari/537.36"}
def t(u, **kw):
    try:
        r=requests.get(u,headers=H,timeout=60,**kw); print("GET",r.status_code,u,"\n  ",r.text[:600].replace("\n"," "))
    except Exception as e: print("EXC",u,e)
print("=== data.gov.il")
for qq in ["מחיר למשתכן","הגרלות","עסקאות נדלן","מידע נדלן","רשות המסים עסקאות"]:
    try:
        j=requests.get("https://data.gov.il/api/3/action/package_search",params={"q":qq,"rows":10},headers=H,timeout=60).json()
        for p in j["result"]["results"]:
            print(qq,"|",p["name"],"|",p["title"],"|",[(r.get("id"),r.get("format"),r.get("last_modified")) for r in p["resources"]][:4])
    except Exception as e: print("EXC",qq,e)
print("=== dira direct")
t("https://www.dira.moch.gov.il/api/Invoker?method=Projects&param=%3FfirstApplicantIdentityNumber%3D%26secondApplicantIdentityNumber%3D%26ProjectStatus%3D4%26Entitlement%3D1%26PageNumber%3D1%26PageSize%3D5%26IsInit%3Dtrue%26")
print("=== playwright capture")
def cap(url, wait=15000, actions=None):
    with sync_playwright() as p:
        b=p.chromium.launch(); pg=b.new_page(user_agent=H["User-Agent"], locale="he-IL")
        seen=[]
        def on(resp):
            rt=resp.request.resource_type
            if rt in ("xhr","fetch"):
                try: body=resp.text()[:500]
                except Exception: body="?"
                print(" ",resp.status,resp.request.method,resp.url,"\n    REQ:",(resp.request.post_data or "")[:300],"\n    RESP:",body.replace("\n"," "))
        pg.on("response",on)
        try:
            pg.goto(url,timeout=60000); pg.wait_for_timeout(wait)
            if actions: actions(pg)
        except Exception as e: print("EXC",e)
        print("TITLE",pg.title()); b.close()
print("--- dira lotteries page"); cap("https://www.dira.moch.gov.il/ProjectsList")
print("--- dira results page"); cap("https://www.dira.moch.gov.il/LotteryResult")
print("--- nadlan city page"); cap("https://www.nadlan.gov.il/?view=settlement&id=7900&page=deals", wait=20000)
print("--- nadlan home"); cap("https://www.nadlan.gov.il/", wait=10000)
