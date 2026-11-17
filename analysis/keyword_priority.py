"""
RankPilot — Dynamic Keyword Priority Scoring
Assigns tracking tier to each keyword based on real data.
Generic — no hardcoded niche categories.
"""
import os, sys, math
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.db import get_session, Keyword, Ranking, GscQuery, Site
from datetime import date, timedelta

def commercial_intent_score(keyword: str, gsc_ctr: float = 0.0) -> float:
    """
    Score 0-1 for commercial intent.
    Uses: CTR (high CTR = users want to act), linguistic signals.
    """
    q = keyword.lower()

    # High CTR from GSC = people are clicking service results = commercial
    if gsc_ctr > 0.05:   return 0.9
    if gsc_ctr > 0.02:   return 0.7

    # Linguistic signals (universal across niches)
    hire_words  = ['hire', 'cost', 'price', 'fee', 'lawyer', 'attorney', 'consultant',
                   'agency', 'company', 'service', 'firm', 'expert', 'professional',
                   'near me', 'best', 'top', 'affordable', 'cheap', 'buy', 'get']
    info_words  = ['what is', 'how to', 'definition', 'meaning', 'explain', 'guide',
                   'tutorial', 'learn', 'history', 'example']

    has_hire = any(w in q for w in hire_words)
    has_info = any(w in q for w in info_words)

    if has_hire and not has_info: return 0.85
    if has_hire and has_info:     return 0.55
    if has_info:                  return 0.25
    return 0.45   # unknown — moderate score

def calculate_priority_score(keyword_data: dict) -> float:
    """
    Calculate priority score for tracking tier assignment.
    Higher score = more important to check frequently.
    Inputs:
      - volume: estimated monthly searches
      - position: current SERP position (None = not ranking)
      - gsc_ctr: actual CTR from GSC
      - gsc_impressions: weekly impressions from GSC
    """
    volume      = keyword_data.get('volume', 10)
    position    = keyword_data.get('position') or 101
    ctr         = keyword_data.get('gsc_ctr', 0.0)
    impressions = keyword_data.get('gsc_impressions', 0)

    intent_score = commercial_intent_score(keyword_data.get('keyword', ''), ctr)

    # Volume signal (log scale)
    vol_score = math.log10(max(volume, 1)) / 6   # 0-1 where 1M searches = 1.0

    # Position signal: near page 1 = high priority (striking distance)
    if position <= 3:    pos_score = 1.0    # already ranking well — protect it
    elif position <= 10: pos_score = 0.9    # page 1 — monitor closely
    elif position <= 20: pos_score = 0.8    # page 2 — striking distance, push up
    elif position <= 50: pos_score = 0.4    # page 3-5 — track weekly
    else:                pos_score = 0.1    # not ranking — track monthly

    # GSC impressions signal (real data > estimates)
    imp_score = min(1.0, math.log10(max(impressions, 1)) / 4) if impressions > 0 else 0

    # Combined score (weighted)
    score = (intent_score * 0.35 +
             vol_score    * 0.25 +
             pos_score    * 0.30 +
             imp_score    * 0.10) * 100

    return round(score, 1)

def assign_tier(score: float) -> str:
    """Assign tracking tier based on priority score."""
    if score >= 70:  return 'daily'    # ~2,000 keywords
    if score >= 35:  return 'weekly'   # ~20,000 keywords
    return 'monthly'                    # everything else

def run_keyword_prioritization(site_domain: str) -> dict:
    """
    Score and tier all tracked keywords for a site.
    Run weekly to promote/demote keywords based on fresh data.
    """
    from analysis.volume_estimator import estimate_volume

    with get_session() as s:
        site = s.query(Site).filter_by(domain=site_domain).first()
        if not site: return {}
        keywords = s.query(Keyword).filter_by(site_id=site.id).all()

        # Get latest ranking data
        rankings = {}
        for r in (s.query(Ranking)
                  .join(Keyword)
                  .filter(Keyword.site_id == site.id)
                  .filter(Ranking.date >= date.today() - timedelta(days=7))
                  .all()):
            rankings[r.keyword_id] = r.position

        # Get GSC data
        gsc = {}
        for q in (s.query(GscQuery)
                  .filter_by(site_id=site.id)
                  .filter(GscQuery.date >= date.today() - timedelta(days=7))
                  .all()):
            key = q.query.lower()
            if key not in gsc or gsc[key]['impressions'] < q.impressions:
                gsc[key] = {'impressions': q.impressions, 'ctr': q.ctr or 0}

    tier_counts = {'daily': 0, 'weekly': 0, 'monthly': 0}
    updates = []

    for kw in keywords:
        gsc_data    = gsc.get(kw.keyword.lower(), {})
        position    = rankings.get(kw.id)

        # Get volume estimate (fast, cached)
        vol_data    = estimate_volume(kw.keyword, kw.country)
        volume      = vol_data.get('volume', 10)

        score = calculate_priority_score({
            'keyword':          kw.keyword,
            'volume':           volume,
            'position':         position,
            'gsc_ctr':          gsc_data.get('ctr', 0),
            'gsc_impressions':  gsc_data.get('impressions', 0),
        })
        tier = assign_tier(score)
        tier_counts[tier] += 1
        updates.append((kw.id, score, tier))

    # Save updated priorities
    with get_session() as s:
        for kw_id, score, tier in updates:
            kw = s.query(Keyword).get(kw_id)
            if kw:
                # Map tier to priority int (1=daily, 2=weekly, 3=monthly)
                kw.priority = {'daily': 1, 'weekly': 2, 'monthly': 3}[tier]
        s.commit()

    print(f'  Keyword tiers: daily={tier_counts["daily"]}, weekly={tier_counts["weekly"]}, monthly={tier_counts["monthly"]}')
    return tier_counts

if __name__ == '__main__':
    from core.config import TARGET_DOMAIN
    result = run_keyword_prioritization(TARGET_DOMAIN)
    print(f'Tier assignment complete: {result}')
