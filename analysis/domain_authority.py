"""
RankPilot — Domain Authority Checker
Uses Open PageRank (free API key required) or falls back to backlink-count proxy.
Also checks competitor domains for comparison.
"""
import os, sys, requests
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import TARGET_DOMAIN, COMPETITORS, DATAFORSEO_LOGIN, DATAFORSEO_PASSWORD
from utils.logger import get_logger
log = get_logger(__name__)

OPR_API_KEY = os.getenv('OPEN_PAGE_RANK_KEY', '')


def get_open_pagerank(domains: list[str]) -> dict:
    """
    Fetch Open PageRank scores (free — sign up at openpagerank.com for API key).
    Without a key, returns empty dict and falls back to backlink-count proxy.
    """
    if not domains or not OPR_API_KEY:
        return {}

    results = {}
    for i in range(0, len(domains), 100):
        batch = domains[i:i+100]
        try:
            r = requests.get(
                'https://openpagerank.com/api/v1.0/getPageRank',
                params={'domains[]': batch},
                headers={'API-OPR': OPR_API_KEY},
                timeout=15
            )
            if r.status_code == 200:
                for item in r.json().get('response', []):
                    domain = item.get('domain', '')
                    results[domain] = {
                        'pagerank':         float(item.get('page_rank_integer', 0)),
                        'pagerank_decimal': float(item.get('page_rank_decimal', 0)),
                        'rank':             item.get('rank', 0),
                    }
            else:
                log.warning('OpenPageRank HTTP %s: %s', r.status_code, r.text[:100])
        except Exception as e:
            log.error('OpenPageRank error: %s', e)

    return results


def _backlink_proxy_scores(our_domain: str, all_domains: list[str]) -> dict:
    """
    Proxy domain authority from backlink counts in our DB.
    Maps backlink count → 0-10 score using log scale.
    Only our domain has backlink data; competitors get 0 (we don't track theirs).
    """
    import math
    from core.db import get_session, Backlink, Site

    results = {d: {'pagerank': 0.0} for d in all_domains}
    try:
        with get_session() as s:
            site = s.query(Site).filter_by(domain=our_domain).first()
            if site:
                count = s.query(Backlink).filter_by(site_id=site.id, status='live').count()
                # log10(1)=0 → score 0, log10(100)=2 → score ~4, log10(10000)=4 → score 8
                score = min(10.0, round(math.log10(max(count, 1)) * 2, 1))
                results[our_domain] = {'pagerank': score, 'backlink_count': count}
                log.info('Domain authority proxy: %s → %d backlinks → %.1f/10', our_domain, count, score)
    except Exception as e:
        log.error('Backlink proxy score error: %s', e)
    return results

def get_dataforseo_domain_metrics(domains: list[str]) -> dict:
    """Get domain metrics from DataForSEO (richer data, small cost)."""
    if not DATAFORSEO_LOGIN or not domains:
        return {}
    try:
        post_data = [{"target": d} for d in domains]
        r = requests.post(
            'https://api.dataforseo.com/v3/domain_analytics/whois/overview/live',
            json=post_data,
            auth=(DATAFORSEO_LOGIN, DATAFORSEO_PASSWORD),
            timeout=20
        )
        if r.status_code == 200:
            results = {}
            for task in r.json().get('tasks', []):
                if task.get('result'):
                    for item in task['result']:
                        domain = item.get('domain', '')
                        results[domain] = {
                            'backlinks': item.get('backlinks', 0),
                            'referring_domains': item.get('referring_domains', 0),
                        }
            return results
    except Exception as e:
        print(f'  ⚠️ DataForSEO domain metrics: {e}')
    return {}

def check_domain_authority(our_domain: str = TARGET_DOMAIN) -> dict:
    """
    Check domain authority for our site + all competitors.
    Uses OpenPageRank if OPEN_PAGE_RANK_KEY is set; otherwise uses backlink-count proxy.
    """
    all_domains = [our_domain] + [c['domain'] for c in COMPETITORS]

    print(f'  Checking domain authority for {len(all_domains)} domains...')

    pr_data = get_open_pagerank(all_domains)
    if not pr_data:
        if not OPR_API_KEY:
            print('  ℹ️ OPEN_PAGE_RANK_KEY not set — using backlink-count proxy')
            print('     Free key at: openpagerank.com (takes 2 min to sign up)')
        pr_data = _backlink_proxy_scores(our_domain, all_domains)

    results = {}
    for domain in all_domains:
        data = pr_data.get(domain, {'pagerank': 0})
        results[domain] = {
            'domain':   domain,
            'pagerank': data.get('pagerank', 0),
            'is_ours':  domain == our_domain,
        }

    sorted_results = sorted(results.values(), key=lambda x: -x['pagerank'])

    print('\n  Domain Authority Comparison:')
    for item in sorted_results:
        marker = ' ← OURS' if item['is_ours'] else ''
        source = ' (backlink proxy)' if not OPR_API_KEY and item['is_ours'] else ''
        print(f'    {item["domain"]:<35} PR: {item["pagerank"]:.1f}/10{marker}{source}')

    our_data = results.get(our_domain, {})
    competitors_stronger = [r for r in sorted_results
                            if not r['is_ours'] and r['pagerank'] > our_data.get('pagerank', 0)]

    return {
        'our_domain':          our_domain,
        'our_pagerank':        our_data.get('pagerank', 0),
        'all':                 sorted_results,
        'competitors_stronger': len(competitors_stronger),
        'data_source':         'openpagerank' if OPR_API_KEY else 'backlink_proxy',
        'insight': (f'{len(competitors_stronger)} competitors have higher domain authority. '
                    f'Focus on earning backlinks from legal publications (LiveLaw, Bar & Bench, Mondaq).')
        if competitors_stronger else '✅ Good domain authority vs competitors'
    }

if __name__ == '__main__':
    result = check_domain_authority()
    print(f'\nOur PageRank: {result["our_pagerank"]}/10')
    print(f'Insight: {result["insight"]}')
