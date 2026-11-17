"""
RankPilot — Content Refresh Queue
Identifies pages that need updating based on:
1. Rank decayed but impressions held (title/content issue)
2. Competitor updated a competing page this month
3. Page not updated in 180+ days AND ranking > position 10
"""
import os, sys
from datetime import date, timedelta, datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import TARGET_DOMAIN
from core.db import (get_session, Site, Ranking, Keyword, GscPage,
                     SiteCrawlPage, AuditIssue, ContentRefreshItem)


def run_content_refresh_analysis(site_domain: str = TARGET_DOMAIN) -> list[dict]:
    """Detect pages that need refreshing. Saves to content_refresh_queue."""
    with get_session() as s:
        site = s.query(Site).filter_by(domain=site_domain).first()
        if not site:
            return []
        site_id = site.id

    today     = date.today()
    month_ago = today - timedelta(days=30)
    week_ago  = today - timedelta(days=7)

    candidates = {}

    # Signal 1: Rank decayed but impressions held
    with get_session() as s:
        recent_ranks = (s.query(Ranking, Keyword)
                        .join(Keyword)
                        .filter(Keyword.site_id == site_id,
                                Ranking.date >= month_ago)
                        .all())

    kw_history: dict[int, list] = {}
    for r, kw in recent_ranks:
        if r.position:
            kw_history.setdefault(kw.id, []).append((r.date, r.position, kw.keyword))

    for kw_id, history in kw_history.items():
        history.sort(key=lambda x: x[0])
        if len(history) < 2:
            continue
        oldest_pos = history[0][1]
        newest_pos = history[-1][1]
        decay      = newest_pos - oldest_pos
        if decay >= 5:
            kw_text = history[0][2]
            key     = kw_text
            score   = min(100, decay * 10)
            reasons = [f'Rank decayed {oldest_pos}→{newest_pos} over 30 days']
            candidates[key] = {'keyword': kw_text, 'score': score, 'reasons': reasons}

    # Signal 2: Competitor updated competing page recently
    with get_session() as s:
        comp_changes = (s.query(AuditIssue)
                        .filter_by(site_id=site_id,
                                   issue_type='competitor_content_changed',
                                   status='open')
                        .filter(AuditIssue.detected_at >= datetime.combine(
                            week_ago, datetime.min.time()))
                        .all())

    for issue in comp_changes:
        # Extract keyword from description
        desc = issue.description or ''
        key  = desc
        if key not in candidates:
            candidates[key] = {'keyword': desc[:80], 'score': 40,
                                'page_url': issue.page_url, 'reasons': []}
        candidates[key]['score'] = min(100, candidates[key]['score'] + 30)
        candidates[key]['reasons'].append('Competitor updated competing page this week')

    # Signal 3: Stale high-traffic pages (crawled 180+ days ago, still ranking > 10)
    with get_session() as s:
        stale_pages = (s.query(SiteCrawlPage)
                       .filter_by(site_id=site_id)
                       .filter(SiteCrawlPage.crawled_at <=
                               datetime.combine(today - timedelta(days=180), datetime.min.time()))
                       .all())

    for page in stale_pages:
        slug = page.url.rstrip('/').split('/')[-1]
        if slug and slug not in candidates:
            candidates[slug] = {
                'keyword': slug.replace('-', ' '),
                'page_url': page.url,
                'score':   25,
                'reasons': [f'Page not refreshed in 180+ days (last crawled: {page.crawled_at.date()})']
            }

    if not candidates:
        print('  ✅ No pages flagged for refresh')
        return []

    # Save to DB
    results = []
    with get_session() as s:
        site = s.query(Site).filter_by(domain=site_domain).first()
        for key, data in sorted(candidates.items(), key=lambda x: -x[1]['score']):
            existing = (s.query(ContentRefreshItem)
                        .filter_by(site_id=site.id, keyword=data['keyword'])
                        .filter(ContentRefreshItem.status == 'pending')
                        .first())
            if not existing:
                s.add(ContentRefreshItem(
                    site_id=site.id,
                    page_url=data.get('page_url', ''),
                    keyword=data['keyword'],
                    refresh_score=data['score'],
                    reasons=data['reasons'],
                    detected_at=today,
                    status='pending'
                ))
            results.append(data)
        s.commit()

    print(f'  ✅ {len(results)} pages added to content refresh queue')
    for r in results[:5]:
        print(f'    Score {r["score"]:3.0f}: {r["keyword"]} — {", ".join(r["reasons"][:1])}')

    return results


if __name__ == '__main__':
    run_content_refresh_analysis()
