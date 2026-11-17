"""
RankPilot — Keyword Cannibalization Detector
Finds cases where multiple pages on our site compete for the same keyword.
This hurts rankings — Google can't decide which page to show.
"""
import os, sys
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.db import get_session, GscQuery, GscPage, Site, Ranking, Keyword
from core.config import TARGET_DOMAIN

def run_cannibalization_check(site_domain: str = TARGET_DOMAIN) -> list[dict]:
    """
    Detect keyword cannibalization using GSC data.
    If 2+ pages appear in top 50 for the same keyword = cannibalization.
    """
    with get_session() as s:
        site = s.query(Site).filter_by(domain=site_domain).first()
        if not site:
            return []

        # Group GSC queries by keyword, collect which pages rank
        queries = s.query(GscQuery).filter_by(site_id=site.id).all()

    # Group by keyword
    keyword_pages = defaultdict(list)
    for q in queries:
        if q.page and q.impressions and q.impressions > 5:
            keyword_pages[q.query.lower()].append({
                'page': q.page,
                'position': q.position or 100,
                'clicks': q.clicks or 0,
                'impressions': q.impressions or 0
            })

    # Find cannibalization: 2+ pages for same keyword
    cannibalized = []
    for keyword, pages in keyword_pages.items():
        unique_pages = {}
        for p in pages:
            page_url = p['page']
            if page_url not in unique_pages:
                unique_pages[page_url] = p
            else:
                # Keep the one with better position
                if p['position'] < unique_pages[page_url]['position']:
                    unique_pages[page_url] = p

        if len(unique_pages) >= 2:
            sorted_pages = sorted(unique_pages.values(), key=lambda x: x['position'])
            # Only flag if keyword has meaningful search volume
            total_impressions = sum(p['impressions'] for p in sorted_pages)
            if total_impressions >= 20:
                cannibalized.append({
                    'keyword': keyword,
                    'competing_pages': sorted_pages,
                    'total_impressions': total_impressions,
                    'recommendation': _get_recommendation(keyword, sorted_pages)
                })

    # Sort by total impressions (highest impact first)
    cannibalized.sort(key=lambda x: -x['total_impressions'])

    if cannibalized:
        print(f'  ⚠️ {len(cannibalized)} keyword cannibalization issues found:')
        for issue in cannibalized[:5]:
            print(f'    "{issue["keyword"]}" ({issue["total_impressions"]} imp):')
            for page in issue['competing_pages'][:3]:
                slug = page['page'].replace(f'https://{site_domain}', '')
                print(f'      pos {page["position"]:.0f}: {slug}')
    else:
        print('  ✅ No keyword cannibalization detected')

    return cannibalized

def _get_recommendation(keyword: str, pages: list[dict]) -> str:
    """Generate a specific fix recommendation."""
    if len(pages) == 2:
        winner = pages[0]  # lower position = better rank
        loser  = pages[1]
        winner_slug = winner['page'].replace(f'https://{TARGET_DOMAIN}', '').replace(f'https://www.{TARGET_DOMAIN}', '') or '/'
        loser_slug  = loser['page'].replace(f'https://{TARGET_DOMAIN}', '').replace(f'https://www.{TARGET_DOMAIN}', '') or '/'
        return (f'Keep "{keyword}" targeting on {winner_slug}. '
                f'Change focus keyword on {loser_slug} to a related but distinct term. '
                f'Add canonical tag from {loser_slug} pointing to {winner_slug}.')
    return f'Multiple pages compete for "{keyword}". Consolidate content or differentiate each page\'s target keyword.'

if __name__ == '__main__':
    issues = run_cannibalization_check()
    print(f'\nTotal cannibalization issues: {len(issues)}')
    for issue in issues[:3]:
        print(f'\nKeyword: "{issue["keyword"]}"')
        print(f'Fix: {issue["recommendation"]}')
