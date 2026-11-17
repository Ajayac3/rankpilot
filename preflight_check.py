#!/usr/bin/env python3
"""Pre-flight: test every external dependency the today-plan needs.
Prints WORKING / BROKEN per system. DataForSEO calls are minimal (~$0.06 total)."""
import sys, os, json, traceback
import requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

OK, BAD = "✅ WORKING", "❌ BROKEN"
rows = []
def rec(name, ok, detail=""):
    rows.append((name, OK if ok else BAD, detail))
    print(f"{(OK if ok else BAD)}  {name:38} {detail}")

# ---- DataForSEO ----
try:
    from core.config import DATAFORSEO_LOGIN, DATAFORSEO_PASSWORD
    AUTH = (DATAFORSEO_LOGIN, DATAFORSEO_PASSWORD)
    BASE = "https://api.dataforseo.com/v3/"
    def dfs(ep, payload):
        r = requests.post(BASE+ep, json=[payload], auth=AUTH, timeout=90)
        d = r.json()
        return d.get("status_code"), d.get("status_message"), d.get("cost", 0), d
    # account
    sc, sm, c, d = dfs("appendix/user_data", {})  # appendix endpoint differs; use GET-like
except Exception as e:
    rec("DataForSEO import/auth", False, str(e)[:80])

tests = [
    ("DFS ranked_keywords", "dataforseo_labs/google/ranked_keywords/live",
     {"target":"example-legal.in","location_name":"India","language_name":"English","limit":1}),
    ("DFS keyword_suggestions", "dataforseo_labs/google/keyword_suggestions/live",
     {"keyword":"nri property lawyer","location_name":"India","language_name":"English","limit":1}),
    ("DFS keyword_ideas", "dataforseo_labs/google/keyword_ideas/live",
     {"keywords":["nri property lawyer"],"location_name":"India","language_name":"English","limit":1}),
    ("DFS bulk_keyword_difficulty", "dataforseo_labs/google/bulk_keyword_difficulty/live",
     {"keywords":["nri property lawyer"],"location_name":"India","language_name":"English"}),
    ("DFS search_intent", "dataforseo_labs/google/search_intent/live",
     {"keywords":["nri property lawyer"],"language_name":"English"}),
    ("DFS competitors_domain", "dataforseo_labs/google/competitors_domain/live",
     {"target":"example-legal.in","location_name":"India","language_name":"English","limit":1}),
    ("DFS backlinks/summary", "backlinks/summary/live", {"target":"example-legal.in"}),
    ("DFS keyword search_volume", "keywords_data/google_ads/search_volume/live",
     {"keywords":["nri property lawyer"],"location_name":"India","language_name":"English"}),
    ("DFS on_page/instant_pages", "on_page/instant_pages",
     {"url":"https://example-legal.in/","enable_javascript":False}),
    ("DFS ai_keyword_data", "ai_optimization/ai_keyword_data/keywords_search_volume/live",
     {"keywords":["nri property lawyer"],"location_name":"India","language_name":"English"}),
]
spent = 0.0
for name, ep, pl in tests:
    try:
        sc, sm, c, d = dfs(ep, pl)
        spent += c or 0
        rec(name, sc == 20000, f"({sm}, ${c})")
    except Exception as e:
        rec(name, False, str(e)[:80])
print(f"   DataForSEO test spend: ${round(spent,4)}\n")

# ---- GSC ----
try:
    from collectors.gsc import fetch_comparison
    from core.config import GSC_PROPERTY
    data = fetch_comparison(GSC_PROPERTY)
    n = len(data.get("this",{}).get("queries",[]))
    rec("Google Search Console (read)", n > 0, f"{n} queries this week")
except Exception as e:
    rec("Google Search Console (read)", False, str(e).splitlines()[0][:80])

# ---- GA4 (now that consent screen is published) ----
try:
    from collectors.ga4 import fetch as ga4_fetch
    from core.config import GA4_PROPERTY_ID
    g = ga4_fetch(GA4_PROPERTY_ID)
    s = g.get("sessions",{}).get("this")
    rec("Google Analytics 4", s is not None, f"sessions this week: {s}")
except Exception as e:
    rec("Google Analytics 4", False, str(e).splitlines()[0][:90])

# ---- Serper (rank tracking) ----
try:
    from core.config import SERPER_KEY
    if SERPER_KEY:
        r = requests.post("https://google.serper.dev/search",
                          headers={"X-API-KEY": SERPER_KEY, "Content-Type":"application/json"},
                          json={"q":"nri property lawyer","gl":"in"}, timeout=30)
        rec("Serper rank tracking", r.status_code == 200, f"HTTP {r.status_code}")
    else:
        rec("Serper rank tracking", False, "SERPER_KEY empty")
except Exception as e:
    rec("Serper rank tracking", False, str(e)[:80])

# ---- IndexNow key file (local + note server) ----
try:
    from core.config import INDEXNOW_KEY
    keyfile = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "complete_website", f"{INDEXNOW_KEY}.txt")
    rec("IndexNow key file (local)", os.path.exists(keyfile),
        "present" if os.path.exists(keyfile) else "MISSING — will create in step B")
except Exception as e:
    rec("IndexNow", False, str(e)[:80])

print("\n--- SUMMARY ---")
for n, s, d in rows:
    print(f"{s}  {n}")
