"""
RankPilot — Link Gap Analysis
Finds domains linking to competitors but NOT to us — top backlink opportunities.
Uses existing backlink data in DB (from CommonCrawl + OpenLinkProfiler).
"""
import os, sys, requests
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import TARGET_DOMAIN, COMPETITORS
from core.db import get_session, Site, Backlink, Competitor, CompetitorUrl

HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; RankPilotBot/0.1)'}


def get_our_backlink_domains(site_id: int) -> set[str]:
    """Get all domains linking to us."""
    with get_session() as s:
        backlinks = s.query(Backlink).filter_by(site_id=site_id, status='live').all()
    return {b.source_domain.lower().replace('www.', '')
            for b in backlinks if b.source_domain}


def get_competitor_backlink_domains(competitor_domain: str) -> set[str]:
    """Get linking domains for a competitor via OpenLinkProfiler (free)."""
    try:
        r = requests.get(
            'https://www.openlinkprofiler.org/api/getBacklinks',
            params={'url': competitor_domain, 'limit': 200,
                    'sort': 'total_links', 'order': 'desc', 'target': 'domain'},
            headers=HEADERS, timeout=20
        )
        if r.status_code == 200:
            data = r.json()
            return {
                link.get('source_domain', '').lower().replace('www.', '')
                for link in data.get('backlinks', [])
                if link.get('source_domain')
            }
    except Exception as e:
        print(f'  ⚠️ OLP {competitor_domain}: {e}')
    return set()


def run_link_gap(site_domain: str = TARGET_DOMAIN,
                 max_competitors: int = 4) -> list[dict]:
    """
    Find link gap opportunities: domains linking to competitors but not us.
    Returns top 30 opportunities sorted by how many competitors link from there.
    """
    with get_session() as s:
        site = s.query(Site).filter_by(domain=site_domain).first()
        if not site:
            return []
        site_id = site.id

    print(f'  Fetching our backlink domains...')
    our_domains = get_our_backlink_domains(site_id)
    print(f'    We have backlinks from {len(our_domains)} domains')

    # Count how many competitors link from each domain
    domain_competitor_count: dict[str, list[str]] = defaultdict(list)

    for comp in COMPETITORS[:max_competitors]:
        comp_domain = comp['domain']
        print(f'  Fetching {comp_domain} backlinks...')
        comp_bl_domains = get_competitor_backlink_domains(comp_domain)
        print(f'    {comp_domain}: {len(comp_bl_domains)} linking domains')

        for domain in comp_bl_domains:
            if domain and domain not in our_domains:
                domain_competitor_count[domain].append(comp_domain)

    # Sort by number of competitors linking from that domain
    gap_list = [
        {
            'linking_domain':    domain,
            'competitor_count':  len(comp_list),
            'competitors':       comp_list,
            'priority':          'high' if len(comp_list) >= 3 else ('medium' if len(comp_list) == 2 else 'low'),
        }
        for domain, comp_list in domain_competitor_count.items()
        if len(comp_list) >= 1
    ]
    gap_list.sort(key=lambda x: -x['competitor_count'])

    top30 = gap_list[:30]

    print(f'\n  📊 Top link gap opportunities ({len(top30)} domains):')
    for item in top30[:10]:
        comps = ', '.join(item['competitors'][:2])
        print(f'    [{item["priority"].upper()}] {item["linking_domain"]:<40} '
              f'({item["competitor_count"]} competitors: {comps})')

    return top30


if __name__ == '__main__':
    gaps = run_link_gap()
    print(f'\nTotal opportunities: {len(gaps)}')
