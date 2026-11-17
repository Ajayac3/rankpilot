"""
RankPilot — Backlink Trend Analysis
Weekly gain/loss counts + correlation with ranking position changes.
"""
import os, sys
from datetime import date, timedelta
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import TARGET_DOMAIN
from core.db import get_session, Site, Backlink, Ranking, Keyword


def _week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def get_weekly_backlink_trends(site_domain: str = TARGET_DOMAIN, weeks: int = 12) -> list[dict]:
    """
    Returns a list of dicts, one per week, newest last:
      [{'week': date, 'gained': int, 'lost': int, 'net': int, 'total_live': int}, ...]

    Gained = backlinks whose first_seen falls in that week.
    Lost   = backlinks whose status='lost' and last_seen falls in that week
             (last_seen is the last time it was confirmed live, so lost "this week" ≈
              last_seen was last week).
    """
    cutoff = date.today() - timedelta(weeks=weeks)

    with get_session() as s:
        site = s.query(Site).filter_by(domain=site_domain).first()
        if not site:
            return []
        backlinks = s.query(Backlink).filter_by(site_id=site.id).all()

    gained_by_week: dict[date, int] = defaultdict(int)
    lost_by_week:   dict[date, int] = defaultdict(int)

    for b in backlinks:
        if b.first_seen and b.first_seen >= cutoff:
            gained_by_week[_week_start(b.first_seen)] += 1
        if b.status == 'lost' and b.last_seen and b.last_seen >= cutoff:
            lost_by_week[_week_start(b.last_seen)] += 1

    today_week = _week_start(date.today())
    all_weeks = sorted({_week_start(date.today() - timedelta(weeks=i)) for i in range(weeks)})

    total_live = sum(1 for b in backlinks if b.status == 'live')
    running_total = total_live

    results = []
    for w in reversed(all_weeks):
        g = gained_by_week.get(w, 0)
        l = lost_by_week.get(w, 0)
        results.append({
            'week':       w,
            'gained':     g,
            'lost':       l,
            'net':        g - l,
            'total_live': running_total,
        })
        running_total -= g
        running_total += l

    return list(reversed(results))


def get_backlink_ranking_correlation(site_domain: str = TARGET_DOMAIN, weeks: int = 8) -> list[dict]:
    """
    Compares weekly net backlink change vs average ranking position change.
    Returns list of dicts: {'week': date, 'net_backlinks': int, 'avg_position_change': float}
    Useful for spotting whether new backlinks correlate with rank improvements.
    """
    trends = get_weekly_backlink_trends(site_domain, weeks=weeks)
    cutoff = date.today() - timedelta(weeks=weeks)

    with get_session() as s:
        site = s.query(Site).filter_by(domain=site_domain).first()
        if not site:
            return []
        rankings = (s.query(Ranking, Keyword)
                    .join(Keyword)
                    .filter(Keyword.site_id == site.id)
                    .filter(Ranking.date >= cutoff)
                    .all())

    pos_by_week: dict[date, list[float]] = defaultdict(list)
    for r, kw in rankings:
        if r.position:
            pos_by_week[_week_start(r.date)].append(r.position)

    avg_pos_by_week = {
        w: sum(positions) / len(positions)
        for w, positions in pos_by_week.items()
    }

    result = []
    weeks_sorted = sorted(avg_pos_by_week.keys())
    for i, w in enumerate(weeks_sorted):
        prev_w = weeks_sorted[i - 1] if i > 0 else None
        pos_change = None
        if prev_w:
            pos_change = round(avg_pos_by_week[w] - avg_pos_by_week[prev_w], 2)

        bl_trend = next((t for t in trends if t['week'] == w), {})
        result.append({
            'week':               w,
            'net_backlinks':      bl_trend.get('net', 0),
            'avg_position':       round(avg_pos_by_week[w], 1),
            'avg_position_change': pos_change,
        })

    return result


def run_backlink_trends(site_domain: str = TARGET_DOMAIN) -> dict:
    """Entry point called by run.py analyse. Returns summary for report."""
    trends  = get_weekly_backlink_trends(site_domain, weeks=4)
    corr    = get_backlink_ranking_correlation(site_domain, weeks=4)

    if not trends:
        return {}

    latest = trends[-1]
    total_gained_4w = sum(t['gained'] for t in trends)
    total_lost_4w   = sum(t['lost']   for t in trends)

    print(f'  Backlink trends (last 4 weeks):')
    print(f'    Gained: {total_gained_4w}  Lost: {total_lost_4w}  Net: {total_gained_4w - total_lost_4w}')
    print(f'    Current live: {latest["total_live"]}')

    if corr:
        last = corr[-1]
        if last['avg_position_change'] is not None:
            direction = 'improved' if last['avg_position_change'] < 0 else 'declined'
            print(f'    Rankings {direction} by {abs(last["avg_position_change"]):.1f} positions this week')

    return {
        'weekly':        trends,
        'correlation':   corr,
        'gained_4w':     total_gained_4w,
        'lost_4w':       total_lost_4w,
        'net_4w':        total_gained_4w - total_lost_4w,
        'total_live':    latest['total_live'],
    }


if __name__ == '__main__':
    result = run_backlink_trends()
    print(f'\nSummary: +{result.get("gained_4w",0)} gained, -{result.get("lost_4w",0)} lost over 4 weeks')
