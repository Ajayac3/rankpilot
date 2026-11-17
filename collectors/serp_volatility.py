"""
RankPilot — SERP Volatility Index
Detects Google algorithm updates by measuring mean absolute position change across
all tracked keywords vs 2 days ago. Score > 5 = suspected algo update.
"""
import os, sys, statistics
from datetime import date, timedelta
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import TARGET_DOMAIN
from core.db import get_session, Site, Keyword, Ranking, SerpVolatility


def calculate_volatility(site_domain: str = TARGET_DOMAIN) -> dict:
    today      = date.today()
    two_ago    = today - timedelta(days=2)

    with get_session() as s:
        site = s.query(Site).filter_by(domain=site_domain).first()
        if not site:
            return {}
        site_id = site.id

        today_ranks = {
            r.keyword_id: r.position
            for r in (s.query(Ranking)
                       .join(Keyword)
                       .filter(Keyword.site_id == site_id, Ranking.date == today)
                       .all())
            if r.position
        }
        prev_ranks = {
            r.keyword_id: r.position
            for r in (s.query(Ranking)
                       .join(Keyword)
                       .filter(Keyword.site_id == site_id, Ranking.date == two_ago)
                       .all())
            if r.position
        }

    common = set(today_ranks) & set(prev_ranks)
    if not common:
        return {'score': 0, 'keywords_moved': 0, 'suspected_update': False,
                'message': 'Not enough data yet (need 2+ days of rankings)'}

    deltas        = [abs(today_ranks[k] - prev_ranks[k]) for k in common]
    score         = round(statistics.mean(deltas), 2)
    moved         = sum(1 for d in deltas if d >= 3)
    suspected     = score > 5
    avg_delta     = round(statistics.mean(deltas), 2)

    result = {
        'score':            score,
        'keywords_tracked': len(common),
        'keywords_moved':   moved,
        'avg_position_delta': avg_delta,
        'suspected_update': suspected,
    }

    with get_session() as s:
        site = s.query(Site).filter_by(domain=site_domain).first()
        existing = s.query(SerpVolatility).filter_by(
            site_id=site.id, date=today
        ).first()
        if existing:
            existing.volatility_score   = score
            existing.keywords_moved     = moved
            existing.avg_position_delta = avg_delta
            existing.suspected_update   = suspected
        else:
            s.add(SerpVolatility(
                site_id=site.id, date=today,
                volatility_score=score, keywords_moved=moved,
                avg_position_delta=avg_delta, suspected_update=suspected
            ))
        s.commit()

    if suspected:
        print(f'  🚨 ALGO UPDATE SUSPECTED — volatility score: {score:.1f} '
              f'({moved}/{len(common)} keywords moved 3+ positions)')
    else:
        print(f'  ✅ SERP stable — volatility score: {score:.1f}')

    return result


if __name__ == '__main__':
    r = calculate_volatility()
    print(r)
