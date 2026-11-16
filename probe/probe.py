import re, requests
H={"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/130 Safari/537.36"}
h=requests.get("https://www.nadlan.gov.il/",headers=H,timeout=60).text
js=sorted(set(re.findall(r"/assets/[A-Za-z0-9_.\-]+\.js",h))) or ["/assets/index.DJW8Ah-v.1794726637441.js"]; print(js)
for s in js:
    t=requests.get("https://www.nadlan.gov.il"+s,headers=H,timeout=60).text
    print("LEN",len(t))
    for u in sorted(set(re.findall(r'https?://[A-Za-z0-9.\-]+(?:/[A-Za-z0-9_\-./]*)?',t))): print("URL",u)
    for k in ["recaptcha","grecaptcha","sitekey","deal","api/","pako","base64","btoa","fetch("]:
        for m in list(re.finditer(re.escape(k),t))[:6]:
            print("CTX",k,"::",t[max(0,m.start()-150):m.end()+200].replace("\n"," "))
