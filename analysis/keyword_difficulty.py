"""
RankPilot — Keyword Difficulty Calculator
Replicates Ahrefs KD methodology: median referring domains to top 10 SERP results.
Uses: ValueSERP (SERP data) + DataForSEO (domain backlink count) or CommonCrawl estimate.
"""
import os, sys, math, statistics, requests, base64, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import (SERPER_KEY, VALUESERP_KEY, DATAFORSEO_LOGIN,
                         DATAFORSEO_PASSWORD, MOZ_ACCESS_ID, MOZ_SECRET_KEY)

DATAFORSEO_ENDPOINT = 'https://api.dataforseo.com/v3'

def get_top10_urls(keyword: str, country: str = 'in') -> list[str]:
    """Get top 10 organic SERP results. Uses Serper → ValueSERP → empty."""
    if SERPER_KEY:
        try:
            r = requests.post(
                'https://google.serper.dev/search',
                headers={'X-API-KEY': SERPER_KEY, 'Content-Type': 'application/json'},
                json={'q': keyword, 'gl': country, 'num': 10},
                timeout=15
            )
            if r.status_code == 200:
                return [res.get('link', '') for res in r.json().get('organic', [])[:10]
                        if res.get('link')]
        except:
            pass
    if VALUESERP_KEY:
        try:
            r = requests.get('https://api.valueserp.com/search',
                             params={'api_key': VALUESERP_KEY, 'q': keyword,
                                     'gl': country, 'hl': 'en', 'num': '10'}, timeout=20)
            if r.status_code == 200:
                return [res.get('link', '') for res in r.json().get('organic_results', [])[:10]
                        if res.get('link')]
        except:
            pass
    return []


def get_moz_referring_domains(domain: str) -> int:
    """Get referring domain count from Moz Free API (50 rows/month free)."""
    if not MOZ_ACCESS_ID or not MOZ_SECRET_KEY:
        return 0
    try:
        auth = base64.b64encode(f'{MOZ_ACCESS_ID}:{MOZ_SECRET_KEY}'.encode()).decode()
        r = requests.post(
            'https://lsapi.seomoz.com/v2/url_metrics',
            headers={'Authorization': f'Basic {auth}', 'Content-Type': 'application/json'},
            json={'targets': [domain], 'metrics': ['linking_root_domains']},
            timeout=15
        )
        if r.status_code == 200:
            results = r.json().get('results', [])
            if results:
                return int(results[0].get('linking_root_domains', 0))
    except Exception as e:
        print(f'  ⚠️ Moz API: {e}')
    return 0

def get_referring_domains_dataforseo(domain: str) -> int:
    """Get referring domain count from DataForSEO."""
    if not DATAFORSEO_LOGIN:
        return 0
    try:
        r = requests.post(
            f'{DATAFORSEO_ENDPOINT}/backlinks/domain_pages_summary/live',
            json=[{"target": domain, "limit": 1}],
            auth=(DATAFORSEO_LOGIN, DATAFORSEO_PASSWORD),
            timeout=15
        )
        if r.status_code == 200:
            tasks = r.json().get('tasks', [])
            if tasks and tasks[0].get('result'):
                return tasks[0]['result'][0].get('referring_domains', 0)
    except:
        pass
    return 0

def get_open_pagerank(domain: str) -> float:
    """Get Open PageRank score (0-10) from openrankdata.com — free."""
    try:
        r = requests.get(
            f'https://openpagerank.com/api/v1.0/getPageRank?domains[]={domain}',
            headers={'API-OPR': 'free_key'},   # free tier, no key needed for basic
            timeout=10
        )
        if r.status_code == 200:
            resp = r.json().get('response', [])
            if resp:
                return float(resp[0].get('page_rank_integer', 0))
    except:
        pass
    return 0.0

def estimate_referring_domains_from_pagerank(pagerank: float) -> int:
    """Estimate referring domain count from PageRank score (proxy when no backlink data)."""
    # PageRank 1 ≈ 1-5 RDs, PR 3 ≈ 50-200 RDs, PR 5 ≈ 1000-5000 RDs
    if pagerank <= 0: return 1
    return int(10 ** (pagerank * 0.6))

def calculate_kd(keyword: str, country: str = 'in') -> dict:
    """
    Calculate Keyword Difficulty score (0-100).
    Matches Ahrefs methodology: median referring domains to top 10 SERP results.
    """
    urls = get_top10_urls(keyword, country)

    if not urls:
        return {'kd': None, 'method': 'no_serp_data',
                'label': 'unknown', 'urls_checked': 0}

    domains = [url.split('/')[2].replace('www.', '') for url in urls if '/' in url]

    # Get referring domain counts: DataForSEO → Moz → Open PageRank estimate
    rd_counts = []
    method = 'open_pagerank_estimate'
    for domain in domains[:10]:
        if DATAFORSEO_LOGIN:
            rd = get_referring_domains_dataforseo(domain)
            method = 'dataforseo'
        elif MOZ_ACCESS_ID:
            rd = get_moz_referring_domains(domain)
            method = 'moz'
            time.sleep(0.2)  # Moz rate limit
        else:
            pr = get_open_pagerank(domain)
            rd = estimate_referring_domains_from_pagerank(pr)
        rd_counts.append(rd)

    if not rd_counts:
        return {'kd': 50, 'method': 'estimate', 'label': 'unknown', 'urls_checked': 0}

    median_rds = statistics.median(rd_counts)
    kd = min(100, int(math.log10(median_rds + 1) * 40))
    label = 'easy' if kd < 30 else ('medium' if kd < 60 else ('hard' if kd < 80 else 'very hard'))

    return {
        'kd': kd,
        'label': label,
        'median_referring_domains': int(median_rds),
        'urls_checked': len(rd_counts),
        'method': method
    }

def batch_calculate_kd(keywords: list[str], country: str = 'in') -> dict:
    """Calculate KD for multiple keywords."""
    import time
    results = {}
    for kw in keywords:
        results[kw] = calculate_kd(kw, country)
        print(f'  KD "{kw}": {results[kw]["kd"]} ({results[kw]["label"]})')
        time.sleep(0.5)
    return results

if __name__ == '__main__':
    test_keywords = ['nri property lawyer', 'nri inheritance lawyer', 'nri legal services delhi']
    for kw in test_keywords:
        result = calculate_kd(kw)
        print(f'{kw}: KD={result["kd"]} ({result["label"]})')
