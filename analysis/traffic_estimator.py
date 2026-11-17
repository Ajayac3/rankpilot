"""
RankPilot — Competitor Traffic Estimator
Estimates monthly organic traffic for our site and competitors.
Formula: Σ(keyword_volume × CTR_at_position) for all tracked keywords.
"""
import os, sys
from datetime import date, timedelta
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import TARGET_DOMAIN, COMPETITORS
from core.db import get_session, Site, Keyword, Ranking, KeywordOpportunity, SerpAnalysisResult

# Standard CTR curve (SmartInsights + Sistrix data)
CTR_CURVE = {
    1: 0.285, 2: 0.157, 3: 0.110, 4: 0.080, 5: 0.072,
    6: 0.052, 7: 0.042, 8: 0.035, 9: 0.030, 10: 0.025,
}

def _ctr(pos: float | None) -> float:
    if not pos or pos < 1:
        return 0.0
    p = int(pos)
    if p <= 10:
        return CTR_CURVE.get(p, 0.025)
    if p <= 20:
        return 0.012
    if p <= 30:
        return 0.008
    if p <= 50:
        return 0.003
    return 0.001


def _get_volume(keyword: str, site_id: int) -> int:
    """Get best available volume estimate for a keyword."""
    with get_session() as s:
        opp = s.query(KeywordOpportunity).filter_by(
            site_id=site_id, keyword=keyword
        ).first()
        if opp and opp.est_volume:
            return opp.est_volume
        # Fall back to GSC impressions × 4.3 / our CTR
        from core.db import GscQuery
        rows = (s.query(GscQuery)
                .filter_by(site_id=site_id, query=keyword)
                .order_by(GscQuery.date.desc())
                .limit(4).all())
        if rows:
            avg_imps = sum(r.impressions for r in rows) / len(rows)
            avg_pos  = sum(r.position for r in rows if r.position) / max(len([r for r in rows if r.position]), 1)
            our_ctr  = _ctr(avg_pos)
            if our_ctr > 0:
                return int((avg_imps * 4.3) / our_ctr)
    return 100  # default floor estimate


def estimate_our_traffic(site_domain: str = TARGET_DOMAIN) -> int:
    """Estimate our total monthly organic traffic from GSC clicks × 4.3."""
    from core.db import GscPage
    with get_session() as s:
        site = s.query(Site).filter_by(domain=site_domain).first()
        if not site:
            return 0
        cutoff = date.today() - timedelta(days=7)
        pages  = (s.query(GscPage)
                  .filter_by(site_id=site.id)
                  .filter(GscPage.date >= cutoff)
                  .all())
    if not pages:
        return 0
    weekly_clicks = sum(p.clicks for p in pages)
    return int(weekly_clicks * 4.3)


def estimate_competitor_traffic(competitor_domain: str, site_id: int) -> int:
    """
    Estimate competitor traffic using SERP analysis data.
    For each keyword where we checked SERP, find competitor's position.
    """
    with get_session() as s:
        serp_rows = (s.query(SerpAnalysisResult)
                     .filter_by(site_id=site_id)
                     .filter(SerpAnalysisResult.domain.contains(
                         competitor_domain.replace('www.', '').split('.')[0]
                     ))
                     .all())

    if not serp_rows:
        return 0

    total = 0
    for row in serp_rows:
        vol = _get_volume(row.keyword, site_id)
        total += int(vol * _ctr(row.position))

    return total


def run_traffic_estimator(site_domain: str = TARGET_DOMAIN) -> dict:
    """
    Estimate traffic for us + all competitors.
    Returns dict sorted by traffic (highest first).
    """
    with get_session() as s:
        site = s.query(Site).filter_by(domain=site_domain).first()
        if not site:
            return {}
        site_id = site.id

    our_traffic = estimate_our_traffic(site_domain)

    estimates = {site_domain: our_traffic}
    for comp in COMPETITORS:
        domain = comp['domain']
        traffic = estimate_competitor_traffic(domain, site_id)
        estimates[domain] = traffic

    # Sort by traffic
    sorted_est = dict(sorted(estimates.items(), key=lambda x: -x[1]))

    print(f'\n  📊 Estimated Monthly Organic Traffic:')
    for domain, traffic in sorted_est.items():
        marker = '⭐ US' if domain == site_domain else '   '
        print(f'    {marker} {domain:<35} ~{traffic:,} visits/month')

    return sorted_est


if __name__ == '__main__':
    run_traffic_estimator()
