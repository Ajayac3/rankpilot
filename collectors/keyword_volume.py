"""
RankPilot — Keyword Volume Estimator
Uses pytrends (Google Trends, unofficial) for relative interest + GSC impressions for calibration.
Gives accurate relative volume without any paid API.
"""
import os, sys, time, requests
from datetime import date
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import TARGET_DOMAIN, DATAFORSEO_LOGIN, DATAFORSEO_PASSWORD
from core.db import get_session, Site, Keyword, GscQuery, KeywordOpportunity

# CTR model: at position 1, roughly 28% of searchers click
# impressions × (1/CTR_pos1) ≈ total monthly searches
# With avg position ~17 → CTR ~1.2% → volume = impressions / 0.012 / 4.3 weeks
_POS_CTR = {1: 0.285, 2: 0.157, 3: 0.110, 4: 0.080, 5: 0.072,
             6: 0.052, 7: 0.042, 8: 0.035, 9: 0.030, 10: 0.025,
             15: 0.012, 20: 0.008, 30: 0.005, 50: 0.003}


def _ctr_at_position(pos: float) -> float:
    if not pos or pos < 1:
        return 0.285
    pos = int(pos)
    if pos in _POS_CTR:
        return _POS_CTR[pos]
    if pos <= 10:
        return _POS_CTR.get(pos, 0.025)
    if pos <= 20:
        return 0.012
    if pos <= 30:
        return 0.008
    return 0.003


def estimate_from_gsc(keyword: str, site_id: int) -> int | None:
    """
    Estimate monthly search volume from GSC impressions.
    Formula: volume = (weekly_impressions × 4.3) / CTR_at_position_1
    Because impressions = volume × CTR_pos_we_rank_at, so volume = impressions / our_CTR
    """
    with get_session() as s:
        rows = (s.query(GscQuery)
                .filter_by(site_id=site_id, query=keyword)
                .order_by(GscQuery.date.desc())
                .limit(4).all())
    if not rows:
        return None
    avg_imps = sum(r.impressions for r in rows) / len(rows)
    avg_pos  = sum(r.position for r in rows if r.position) / max(len([r for r in rows if r.position]), 1)
    our_ctr  = _ctr_at_position(avg_pos)
    if our_ctr == 0:
        return None
    # weekly impressions × 4.3 = monthly. impressions / our_CTR = total volume
    monthly_volume = int((avg_imps * 4.3) / our_ctr)
    return monthly_volume


def fetch_dataforseo_volumes(keywords: list[str], country: str = 'IN') -> dict[str, int]:
    """Fetch real Google Ads search volumes via DataForSEO. Cost: ~$0.0001/keyword."""
    if not DATAFORSEO_LOGIN or not keywords:
        return {}
    location_map = {'IN': 'India', 'US': 'United States', 'GB': 'United Kingdom',
                    'CA': 'Canada', 'AE': 'United Arab Emirates', 'AU': 'Australia'}
    location = location_map.get(country, 'India')
    results = {}
    for i in range(0, len(keywords), 1000):
        batch = keywords[i:i + 1000]
        try:
            r = requests.post(
                'https://api.dataforseo.com/v3/keywords_data/google_ads/search_volume/live',
                json=[{'keywords': batch, 'location_name': location, 'language_name': 'English'}],
                auth=(DATAFORSEO_LOGIN, DATAFORSEO_PASSWORD),
                timeout=30
            )
            if r.status_code == 200:
                for task in r.json().get('tasks', []):
                    for item in (task.get('result') or []):
                        kw  = item.get('keyword', '')
                        vol = item.get('search_volume') or 0
                        results[kw] = vol
            elif r.status_code in (401, 403):
                body = r.json()
                print(f'  ⚠️ DataForSEO auth error {r.status_code}: {body.get("status_message", "")[:80]}')
                print('     Account needs verification at app.dataforseo.com — using GSC estimates instead')
                break
        except Exception as e:
            print(f'  ⚠️ DataForSEO volume batch {i}: {e}')
    return results


def estimate_from_trends(keywords: list[str], geo: str = 'IN') -> dict[str, int]:
    """
    Use pytrends (Google Trends) to get relative interest for keywords.
    Returns {keyword: estimated_monthly_volume} using a calibration baseline.
    """
    try:
        from pytrends.request import TrendReq
    except ImportError:
        print('  ℹ️ pytrends not installed. Run: pip install pytrends')
        return {}

    results = {}
    # Process in batches of 5 (pytrends limit)
    for i in range(0, len(keywords), 5):
        batch = keywords[i:i + 5]
        try:
            pt = TrendReq(hl='en-US', tz=330, timeout=(10, 25))  # IST = UTC+5:30
            pt.build_payload(batch, cat=0, timeframe='today 12-m', geo=geo)
            interest = pt.interest_over_time()
            if interest.empty:
                continue
            for kw in batch:
                if kw in interest.columns:
                    avg_interest = interest[kw].mean()  # 0-100 scale
                    # Calibration: interest=100 ≈ 10,000 searches/month for legal niche
                    results[kw] = max(10, int(avg_interest * 100))
            time.sleep(2)  # be polite to Google Trends
        except Exception as e:
            print(f'  ⚠️ pytrends batch {i}: {e}')
            time.sleep(5)
    return results


def run_keyword_volume(site_domain: str = TARGET_DOMAIN, max_keywords: int = 100) -> dict:
    """
    Update `est_volume` for all tracked keywords and opportunities.
    Prioritises GSC-derived estimates (more accurate) over trends.
    """
    with get_session() as s:
        site = s.query(Site).filter_by(domain=site_domain).first()
        if not site:
            return {}
        site_id = site.id

        keywords = (s.query(Keyword)
                    .filter_by(site_id=site_id)
                    .limit(max_keywords).all())
        opps = (s.query(KeywordOpportunity)
                .filter_by(site_id=site_id, status='new')
                .filter(KeywordOpportunity.est_volume == None)
                .limit(50).all())

    updated = 0
    kw_texts = [kw.keyword for kw in keywords]

    # Try DataForSEO first; falls back to GSC estimates on 403
    dfs_volumes = {}
    if DATAFORSEO_LOGIN and kw_texts:
        print(f'  Trying DataForSEO volumes for {len(kw_texts)} keywords...')
        dfs_volumes = fetch_dataforseo_volumes(kw_texts)
        if dfs_volumes:
            print(f'    ✅ Got {len(dfs_volumes)} volumes from DataForSEO')
        else:
            print('    ℹ️ DataForSEO unavailable — using GSC impression estimates')

    print(f'  Estimating volume for {len(keywords)} tracked keywords from GSC...')
    with get_session() as s:
        for kw in keywords:
            vol = dfs_volumes.get(kw.keyword) or estimate_from_gsc(kw.keyword, site_id)
            if vol and vol > 0:
                # Update on Keyword table directly (no separate opp needed)
                kw_row = s.query(Keyword).filter_by(site_id=site_id, keyword=kw.keyword).first()
                if kw_row:
                    kw_row.volume = vol
                opp = s.query(KeywordOpportunity).filter_by(
                    site_id=site_id, keyword=kw.keyword
                ).first()
                if opp:
                    opp.est_volume = vol
                updated += 1
        s.commit()

    # Opportunities without GSC data — try DataForSEO or skip (pytrends rate-limits)
    opp_keywords = [o.keyword for o in opps if o.keyword]
    if opp_keywords and dfs_volumes:
        opp_vols = fetch_dataforseo_volumes(opp_keywords)
        if opp_vols:
            with get_session() as s:
                for kw_text, vol in opp_vols.items():
                    opp = s.query(KeywordOpportunity).filter_by(
                        site_id=site_id, keyword=kw_text
                    ).first()
                    if opp and vol:
                        opp.est_volume = vol
                        updated += 1
                s.commit()

    print(f'  ✅ Volume updated for {updated} keywords')
    return {'updated': updated}


if __name__ == '__main__':
    run_keyword_volume()
