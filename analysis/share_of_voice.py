"""
RankPilot — Share of Voice / Visibility Score
Single metric showing what % of total available search traffic we capture.
Ahrefs calls this "Traffic Potential", Semrush calls it "Visibility %".
Formula: Σ(keyword_volume × CTR_at_our_position) / Σ(keyword_volume × CTR_at_pos_1) × 100
"""
import os, sys
from datetime import date, timedelta
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import TARGET_DOMAIN, COMPETITORS
from core.db import (get_session, Site, Keyword, Ranking, KeywordOpportunity,
                     SerpAnalysisResult, VisibilityScore, GscQuery)

CTR_CURVE = {
    1: 0.285, 2: 0.157, 3: 0.110, 4: 0.080, 5: 0.072,
    6: 0.052, 7: 0.042, 8: 0.035, 9: 0.030, 10: 0.025,
}

def _ctr(pos):
    if not pos or pos < 1:
        return 0.0
    p = int(pos)
    if p <= 10:
        return CTR_CURVE.get(p, 0.025)
    if p <= 20: return 0.012
    if p <= 30: return 0.008
    if p <= 50: return 0.003
    return 0.001


def _volume(keyword: str, site_id: int) -> int:
    with get_session() as s:
        opp = s.query(KeywordOpportunity).filter_by(
            site_id=site_id, keyword=keyword
        ).first()
        if opp and opp.est_volume:
            return opp.est_volume
    return 100  # default


def calculate_share_of_voice(site_domain: str = TARGET_DOMAIN) -> dict:
    """
    Calculate our Share of Voice and compare vs competitors.
    Saves daily snapshot to VisibilityScore table.
    Returns {'our_score': float, 'competitors': {domain: score}}
    """
    with get_session() as s:
        site = s.query(Site).filter_by(domain=site_domain).first()
        if not site:
            return {}
        site_id = site.id

        # Get latest rankings for our keywords
        cutoff = date.today() - timedelta(days=3)
        rankings = (s.query(Ranking, Keyword)
                    .join(Keyword)
                    .filter(Keyword.site_id == site_id)
                    .filter(Ranking.date >= cutoff)
                    .all())

    # Group by keyword → most recent position
    keyword_positions: dict[str, float] = {}
    for r, kw in rankings:
        kw_text = kw.keyword
        if kw_text not in keyword_positions or r.date > date.today() - timedelta(days=1):
            keyword_positions[kw_text] = r.position or 101

    if not keyword_positions:
        # Fall back to GSC-based estimate when no ranking data exists
        with get_session() as s:
            week_ago = date.today() - timedelta(days=7)
            gsc_rows = s.query(GscQuery).filter(
                GscQuery.site_id == site_id,
                GscQuery.date >= week_ago
            ).all()
        weekly_clicks = sum(r.clicks or 0 for r in gsc_rows)
        monthly_est = int(weekly_clicks * 4.3)
        market_baseline = 5000  # NRI legal niche monthly baseline
        fallback_sov = round(monthly_est / market_baseline * 100, 2) if market_baseline else 0
        print('  ℹ️ No ranking data yet — using GSC estimate. Run: python run.py rank')
        return {
            'our_score':   fallback_sov,
            'our_traffic': monthly_est,
            'competitors': {},
            'total_tracked': 0,
            'insight': f'Estimated from GSC data ({weekly_clicks} clicks/week). Run rank for full SoV.',
        }

    # Calculate total addressable traffic (all keywords at position 1)
    total_addressable = 0
    our_captured      = 0

    for kw, pos in keyword_positions.items():
        vol = _volume(kw, site_id)
        total_addressable += vol * CTR_CURVE[1]  # if we ranked #1
        our_captured      += vol * _ctr(pos)

    our_sov = (our_captured / total_addressable * 100) if total_addressable > 0 else 0
    our_traffic_est = int(our_captured * 4.3)  # monthly

    # Competitor SoV from SERP analysis data
    comp_scores: dict[str, float] = {}
    with get_session() as s:
        for comp in COMPETITORS:
            comp_domain = comp['domain']
            serp_rows = (s.query(SerpAnalysisResult)
                         .filter_by(site_id=site_id)
                         .filter(SerpAnalysisResult.domain.contains(
                             comp_domain.replace('www.', '').split('.')[0]
                         ))
                         .all())
            comp_traffic = sum(_volume(r.keyword, site_id) * _ctr(r.position)
                               for r in serp_rows)
            comp_sov = (comp_traffic / total_addressable * 100) if total_addressable > 0 else 0
            comp_scores[comp_domain] = round(comp_sov, 2)

    our_sov = round(our_sov, 2)

    # Save to DB
    all_domains = {site_domain: (our_sov, our_traffic_est)}
    all_domains.update({
        d: (csov, int(csov * total_addressable * 4.3 / 100))
        for d, csov in comp_scores.items()
    })
    with get_session() as db:
        for domain, (score, traffic) in all_domains.items():
            existing = db.query(VisibilityScore).filter_by(
                site_id=site_id, date=date.today(), domain=domain
            ).first()
            if existing:
                existing.score = score
                existing.traffic_est = traffic
            else:
                db.add(VisibilityScore(
                    site_id=site_id, date=date.today(),
                    domain=domain, score=score, traffic_est=traffic
                ))
        db.commit()

    # Print comparison
    all_sov = {site_domain: our_sov, **comp_scores}
    sorted_sov = sorted(all_sov.items(), key=lambda x: -x[1])

    print(f'\n  📊 Share of Voice (% of available NRI legal search traffic):')
    for domain, sov in sorted_sov:
        marker = '⭐ US' if domain == site_domain else '   '
        bar    = '█' * max(1, int(sov * 2)) + '░' * max(0, 20 - int(sov * 2))
        print(f'    {marker} {domain:<35} {bar} {sov:.2f}%')
    print(f'\n  Our estimated traffic: ~{our_traffic_est:,} visits/month')

    top_comp = max(comp_scores.items(), key=lambda x: x[1], default=(None, 0))
    if top_comp[0] and top_comp[1] > our_sov:
        insight = (f'Trailing {top_comp[0]} by {top_comp[1] - our_sov:.1f}pp. '
                   f'Capturing {our_sov:.1f}% of NRI legal search traffic '
                   f'(est. {our_traffic_est:,} visits/month).')
    else:
        insight = (f'Leading competitors with {our_sov:.1f}% share of NRI legal search traffic '
                   f'(est. {our_traffic_est:,} visits/month).')

    return {
        'our_score':     our_sov,
        'our_traffic':   our_traffic_est,
        'competitors':   comp_scores,
        'total_tracked': len(keyword_positions),
        'insight':       insight,
    }


if __name__ == '__main__':
    calculate_share_of_voice()
