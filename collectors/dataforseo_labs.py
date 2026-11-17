#!/usr/bin/env python3
"""DataForSEO Labs full-suite intelligence pull for example-legal.in.
Reuses the basic-auth pattern from keyword_volume.py. Dumps everything to
audit/dataforseo-data.json for Claude to turn into the intelligence report.
Run: python3 collectors/dataforseo_labs.py
"""
import sys, os, json, time
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import DATAFORSEO_LOGIN, DATAFORSEO_PASSWORD

AUTH = (DATAFORSEO_LOGIN, DATAFORSEO_PASSWORD)
BASE = "https://api.dataforseo.com/v3/"
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "audit", "dataforseo-data.json")
LOC, LANG = "India", "English"
OUR = "example-legal.in"
COMPETITORS = ["sheokandlegal.com", "nrilegalservices.com"]

# money-cluster seeds for opportunity discovery
SEED_TOPICS = [
    "498a quashing nri", "nri property dispute lawyer", "look out circular nri",
    "power of attorney for nri", "oci card rejected", "nri divorce lawyer india",
    "fir quashing nri", "anticipatory bail nri",
]
# top money pages for the on-page technical audit
KEY_PAGES = [
    "https://example-legal.in/498a-nri-husband-defense-guide-2026/",
    "https://example-legal.in/get-look-out-circular-revoked-or-cancelled/",
    "https://example-legal.in/power-of-attorney-nri-india/",
    "https://example-legal.in/nri-property-dispute-lawyer/",
    "https://example-legal.in/oci-card-rejected-appeal/",
]

cost = {"total": 0.0}


def call(ep, payload):
    r = requests.post(BASE + ep, json=[payload], auth=AUTH, timeout=120)
    d = r.json()
    cost["total"] += d.get("cost", 0) or 0
    if d.get("status_code") != 20000:
        print(f"  ! {ep}: {d.get('status_code')} {d.get('status_message')}")
    return d


def result0(d):
    t = (d.get("tasks") or [{}])[0]
    return (t.get("result") or [None])[0]


data = {"generated": "2026-06-14", "location": LOC, "our_domain": OUR, "competitors": {}}

# 1) our full ranking footprint
print("1/8 ranked_keywords (us)…")
d = call("dataforseo_labs/google/ranked_keywords/live",
         {"target": OUR, "location_name": LOC, "language_name": LANG, "limit": 1000,
          "order_by": ["keyword_data.keyword_info.search_volume,desc"]})
r = result0(d)
ours = []
if r:
    for it in (r.get("items") or []):
        kw = it.get("keyword_data", {})
        ki = kw.get("keyword_info", {})
        se = it.get("ranked_serp_element", {}).get("serp_item", {})
        ours.append({"keyword": kw.get("keyword"), "pos": se.get("rank_absolute"),
                     "volume": ki.get("search_volume"), "cpc": ki.get("cpc"),
                     "url": se.get("url"), "intent": (kw.get("search_intent_info") or {}).get("main_intent")})
    data["our_total_ranked"] = r.get("total_count")
data["our_keywords"] = ours
print(f"   {len(ours)} keywords (total {data.get('our_total_ranked')})")

# 2) competitors' ranking footprints
for c in COMPETITORS:
    print(f"2/8 ranked_keywords ({c})…")
    d = call("dataforseo_labs/google/ranked_keywords/live",
             {"target": c, "location_name": LOC, "language_name": LANG, "limit": 700,
              "order_by": ["keyword_data.keyword_info.search_volume,desc"]})
    r = result0(d)
    lst = []
    if r:
        for it in (r.get("items") or []):
            kw = it.get("keyword_data", {})
            ki = kw.get("keyword_info", {})
            se = it.get("ranked_serp_element", {}).get("serp_item", {})
            lst.append({"keyword": kw.get("keyword"), "pos": se.get("rank_absolute"),
                        "volume": ki.get("search_volume"), "url": se.get("url")})
    data["competitors"][c] = {"total": (r or {}).get("total_count"), "keywords": lst}
    print(f"   {len(lst)} keywords (total {(r or {}).get('total_count')})")

# 3) keyword GAP — competitor ranks top 20, we don't rank at all
our_kw = {k["keyword"] for k in ours if k["keyword"]}
gap = {}
for c, cd in data["competitors"].items():
    for k in cd["keywords"]:
        if k["keyword"] and k["keyword"] not in our_kw and (k["pos"] or 99) <= 20 and (k["volume"] or 0) >= 50:
            g = gap.setdefault(k["keyword"], {"keyword": k["keyword"], "volume": k["volume"], "competitor_pos": {}})
            g["competitor_pos"][c] = k["pos"]
data["keyword_gap"] = sorted(gap.values(), key=lambda x: -(x["volume"] or 0))[:120]
print(f"3/8 keyword gap: {len(data['keyword_gap'])} terms competitors rank for, we don't")

# 4) keyword ideas/suggestions for money topics
print("4/8 keyword_suggestions (money topics)…")
ideas = []
for s in SEED_TOPICS:
    d = call("dataforseo_labs/google/keyword_suggestions/live",
             {"keyword": s, "location_name": LOC, "language_name": LANG, "limit": 40,
              "order_by": ["keyword_info.search_volume,desc"]})
    r = result0(d)
    if r:
        for it in (r.get("items") or []):
            ki = it.get("keyword_info", {})
            si = it.get("search_intent_info") or {}
            ideas.append({"seed": s, "keyword": it.get("keyword"), "volume": ki.get("search_volume"),
                          "cpc": ki.get("cpc"), "competition": ki.get("competition"),
                          "intent": si.get("main_intent")})
    time.sleep(0.3)
data["keyword_ideas"] = ideas
print(f"   {len(ideas)} ideas")

# 5) bulk keyword difficulty for our seed + top gap + top ideas
print("5/8 bulk_keyword_difficulty…")
diff_terms = list({*SEED_TOPICS,
                   *[g["keyword"] for g in data["keyword_gap"][:40]],
                   *[i["keyword"] for i in sorted(ideas, key=lambda x: -(x["volume"] or 0))[:40] if i["keyword"]]})
kd = {}
for i in range(0, len(diff_terms), 100):
    d = call("dataforseo_labs/google/bulk_keyword_difficulty/live",
             {"keywords": diff_terms[i:i+100], "location_name": LOC, "language_name": LANG})
    r = result0(d)
    if r:
        for it in (r.get("items") or []):
            kd[it.get("keyword")] = it.get("keyword_difficulty")
data["keyword_difficulty"] = kd
print(f"   difficulty for {len(kd)} terms")

# 6) backlinks summary (us + competitors)
print("6/8 backlinks summary…")
bl = {}
for dom in [OUR] + COMPETITORS:
    d = call("backlinks/summary/live", {"target": dom, "internal_list_limit": 1, "backlinks_status_type": "live"})
    r = result0(d)
    if r:
        bl[dom] = {"backlinks": r.get("backlinks"), "referring_domains": r.get("referring_domains"),
                   "rank": r.get("rank"), "referring_main_domains": r.get("referring_main_domains")}
data["backlinks"] = bl
print(f"   {json.dumps(bl)}")

# 7) on-page instant audit of key money pages
print("7/8 on_page instant audit…")
op = []
for u in KEY_PAGES:
    d = call("on_page/instant_pages", {"url": u, "enable_javascript": False})
    r = result0(d)
    if r:
        items = r.get("items") or []
        if items:
            it = items[0]
            m = it.get("meta", {})
            ch = it.get("checks", {})
            op.append({"url": u, "title_len": len((m.get("title") or "")), "h1": m.get("htags", {}).get("h1"),
                       "internal_links": m.get("internal_links_count"), "broken": ch.get("broken_links"),
                       "no_h1": ch.get("no_h1_tag"), "title_too_long": ch.get("title_too_long"),
                       "low_content": ch.get("low_content_rate"), "load_s": it.get("page_timing", {}).get("dom_complete")})
    time.sleep(0.3)
data["on_page"] = op
print(f"   audited {len(op)} pages")

# 8) AI visibility — best-effort (new endpoints, may vary)
print("8/8 AI visibility (best-effort)…")
try:
    d = call("ai_optimization/ai_keyword_data/keywords_search_volume/live",
             {"keywords": SEED_TOPICS[:5], "location_name": LOC, "language_name": LANG})
    data["ai_keyword_data"] = result0(d)
    print("   ai_keyword_data ok")
except Exception as e:
    data["ai_keyword_data"] = {"error": str(e)[:120]}
    print(f"   ai endpoint skipped: {e}")

data["api_cost_usd"] = round(cost["total"], 4)
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
print(f"\n✅ saved {OUT} | total API cost ${data['api_cost_usd']}")
