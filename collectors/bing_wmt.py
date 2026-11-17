"""
RankPilot — Bing Webmaster Tools API
Free data source: Bing search performance, crawl stats, index coverage, backlinks.
NRI diaspora in US/UK/Canada heavily uses Bing/DuckDuckGo — worth tracking.
Setup: Get free API key at https://www.bing.com/webmasters/
"""
import logging
import os, sys, requests
from datetime import date, timedelta

log = logging.getLogger(__name__)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import TARGET_DOMAIN, BING_WMT_API_KEY
from core.db import get_session, Site, BingQuery

BASE_URL = 'https://ssl.bing.com/webmaster/api.svc/json'
HEADERS  = {'Content-Type': 'application/json; charset=utf-8'}


def _api_get(endpoint: str, params: dict = None) -> dict:
    """Make a GET request to Bing WMT API."""
    if not BING_WMT_API_KEY:
        return {}
    p = {'apikey': BING_WMT_API_KEY, **(params or {})}
    try:
        r = requests.get(f'{BASE_URL}/{endpoint}', params=p, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            result = r.json()
            # Bing API sometimes returns a list directly — wrap it
            return result if isinstance(result, dict) else {'results': result}
        print(f'  ⚠️ Bing WMT {endpoint}: HTTP {r.status_code}')
    except Exception as e:
        print(f'  ⚠️ Bing WMT {endpoint}: {e}')
    return {}


def fetch_query_stats(site_url: str, days: int = 7) -> list[dict]:
    """
    Fetch top search queries from Bing for the site.
    Returns list of {query, impressions, clicks, ctr, avg_position}

    IMPORTANT — what a stored row means. This requests a ROLLING `days`-day
    window and every row is written stamped with date.today(). A row is
    therefore "the last 7 days as at this date", NOT "this date". Summing the
    same query across dates counts the same clicks about seven times over.
    Read the latest date only (see report/pdf_builder.py, which uses
    func.max(BingQuery.date) correctly).
    """
    end   = date.today()
    start = end - timedelta(days=days)
    data  = _api_get('GetQueryStats', {
        'siteUrl':   site_url,
        'startDate': start.isoformat(),
        'endDate':   end.isoformat(),
        'timegrain': 'Weekly',
    })
    queries = []
    # Bing API returns {'d': [...]} or {'d': {'results': [...]}} or a direct list
    d   = data.get('d', []) if isinstance(data, dict) else data
    raw = d if isinstance(d, list) else d.get('results', [])
    rejected = 0
    for item in raw:
        q = {
            'query':        item.get('Query', ''),
            'impressions':  item.get('Impressions', 0) or 0,
            'clicks':       item.get('Clicks', 0) or 0,
            'ctr':          item.get('Ctr', 0.0) or 0.0,
            # The field is AvgImpressionPosition — singular "Impression". The old
            # code asked for 'AvgImpressionsPos', which does not exist, so .get()
            # returned the 0.0 default on every single row: all 296,540 stored
            # positions were zero and nobody noticed because nothing reported them.
            # Confirmed against a live response 2026-08-01; the response also
            # carries AvgClickPosition.
            'avg_position': item.get('AvgImpressionPosition') or 0.0,
            'avg_click_position': item.get('AvgClickPosition') or 0.0,
        }
        # Rows where clicks exceed impressions are dropped. Correction to an
        # earlier note: these are NOT caused by our field mapping — Bing's live
        # API genuinely returns them (68 in one full response), presumably because
        # clicks and impressions are attributed with different lag or sampling.
        # They are still unusable as a metric and a CTR above 100% is worse than
        # no number, so they are discarded rather than stored.
        if q['clicks'] > q['impressions']:
            rejected += 1
            log.warning('Bing row dropped, clicks > impressions: %r %s/%s '
                        '(Bing-side attribution artifact, not a mapping error)',
                        q['query'][:60], q['clicks'], q['impressions'])
            continue
        queries.append(q)
    if rejected:
        log.error('Bing: %d of %d rows were impossible and were discarded. '
                  'Do not report Bing numbers until this is diagnosed.',
                  rejected, rejected + len(queries))
    return queries


def fetch_crawl_stats(site_url: str) -> dict:
    """Fetch Bing crawl statistics for the site."""
    data = _api_get('GetCrawlStats', {'siteUrl': site_url})
    d = data.get('d', {}) if isinstance(data, dict) else {}
    return d if isinstance(d, dict) else {}


def fetch_index_stats(site_url: str) -> dict:
    """Fetch Bing index coverage statistics."""
    data = _api_get('GetUrlTrafficInfo', {'siteUrl': site_url})
    d = data.get('d', {}) if isinstance(data, dict) else {}
    return d if isinstance(d, dict) else {}


def submit_urls(site_url: str, urls: list[str]) -> bool:
    """Submit URLs to Bing for (re)crawling."""
    if not BING_WMT_API_KEY or not urls:
        return False
    try:
        r = requests.post(
            f'{BASE_URL}/SubmitUrlbatch',
            params={'apikey': BING_WMT_API_KEY},
            json={'siteUrl': site_url, 'urlList': urls[:500]},
            headers=HEADERS,
            timeout=15
        )
        return r.status_code in (200, 204)
    except Exception as e:
        print(f'  ⚠️ Bing WMT submit: {e}')
        return False


def run_bing_wmt(site_domain: str = TARGET_DOMAIN) -> dict:
    """
    Fetch all Bing WMT data and save to DB.
    Returns summary dict.
    """
    if not BING_WMT_API_KEY:
        print('  ⚠️ Bing WMT: BING_WMT_API_KEY not set in .env')
        print('     Get free key at: https://www.bing.com/webmasters/ → Settings → API access')
        return {}

    site_url = f'https://{site_domain}/'

    print(f'  Fetching Bing WMT data for {site_domain}...')
    queries = fetch_query_stats(site_url)
    print(f'    Queries: {len(queries)}')

    if not queries:
        print('  ⚠️ No query data returned. Verify site is verified in Bing WMT.')
        return {}

    with get_session() as s:
        site = s.query(Site).filter_by(domain=site_domain).first()
        if not site:
            return {}

        saved = 0
        for q in queries:
            if not q['query']:
                continue
            existing = (s.query(BingQuery)
                        .filter_by(site_id=site.id, date=date.today(), query=q['query'])
                        .first())
            if existing:
                existing.impressions  = q['impressions']
                existing.clicks       = q['clicks']
                existing.ctr          = q['ctr']
                existing.avg_position = q['avg_position']
            else:
                s.add(BingQuery(
                    site_id=site.id, date=date.today(),
                    query=q['query'],
                    impressions=q['impressions'], clicks=q['clicks'],
                    ctr=q['ctr'], avg_position=q['avg_position'],
                ))
                saved += 1
        s.commit()

    total_clicks = sum(q['clicks'] for q in queries)
    total_imps   = sum(q['impressions'] for q in queries)
    avg_ctr      = total_clicks / total_imps * 100 if total_imps else 0

    result = {
        'queries':      len(queries),
        'total_clicks': total_clicks,
        'total_impressions': total_imps,
        'avg_ctr_pct':  round(avg_ctr, 2),
        'saved_new':    saved,
    }
    print(f'    ✅ Bing: {total_clicks} clicks, {total_imps:,} imps, CTR {avg_ctr:.2f}%')
    return result


if __name__ == '__main__':
    result = run_bing_wmt()
    print(result)
