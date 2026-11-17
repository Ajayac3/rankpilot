"""
RankPilot — GSC Collector
Fetches queries + pages for this week AND previous week.
"""
import os, sys, json
from datetime import datetime, timedelta, timezone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.logger import get_logger
from core.config import GOOGLE_OAUTH_TOKEN_PATH
log = get_logger(__name__)


def _get_credentials():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    with open(GOOGLE_OAUTH_TOKEN_PATH) as f:
        data = json.load(f)
    creds = Credentials(
        token=data['token'], refresh_token=data['refresh_token'],
        token_uri=data['token_uri'], client_id=data['client_id'],
        client_secret=data['client_secret'], scopes=data['scopes']
    )
    if creds.expired:
        creds.refresh(Request())
        data['token'] = creds.token
        with open(GOOGLE_OAUTH_TOKEN_PATH, 'w') as f:
            json.dump(data, f)
    return creds


def _service():
    from googleapiclient.discovery import build
    return build('searchconsole', 'v1', credentials=_get_credentials(), cache_discovery=False)

def _date_range(days: int, end_offset: int):
    end   = (datetime.now(timezone.utc) - timedelta(days=end_offset)).strftime('%Y-%m-%d')
    start = (datetime.now(timezone.utc) - timedelta(days=end_offset + days - 1)).strftime('%Y-%m-%d')
    return start, end

def _query(svc, property_url, start, end, dimensions, row_limit=5000):
    body = {'startDate': start, 'endDate': end, 'dimensions': dimensions,
            'rowLimit': row_limit, 'dataState': 'final'}
    return svc.searchanalytics().query(siteUrl=property_url, body=body).execute().get('rows', [])

def fetch_daily(property_url: str, days: int = 7, end_offset: int = 3) -> dict:
    """Per-day GSC rows for the window, keyed by date.

    The old fetch() asked for one aggregate over the whole window and the caller
    stored it against a single date, so a row labelled 2026-08-28 actually held
    22-28 August. Summing seven such rows counted every day up to seven times —
    that is the ~7x inflation behind every historical report. Asking for the date
    dimension costs the same one call and gives rows that can be summed.

    Also pulls date x query x page so each query row records the page that earned
    it; the page dimension was requested nowhere before, leaving gsc_queries.page
    NULL for every row ever written.
    """
    svc = _service()
    start, end = _date_range(days, end_offset)

    days_out = {}

    def day(d):
        return days_out.setdefault(d, {'queries': {}, 'pages': {}, 'start': d, 'end': d})

    for row in _query(svc, property_url, start, end, ['date', 'query'], row_limit=25000):
        d, q = row['keys'][0], row['keys'][1].lower()
        day(d)['queries'][q] = {
            'clicks': row['clicks'], 'impressions': row['impressions'],
            'ctr': round(row['ctr'] * 100, 2), 'position': round(row['position'], 2)
        }
    for row in _query(svc, property_url, start, end, ['date', 'page'], row_limit=25000):
        d, pg = row['keys'][0], row['keys'][1]
        day(d)['pages'][pg] = {
            'clicks': row['clicks'], 'impressions': row['impressions'],
            'position': round(row['position'], 2)
        }

    # Attribute each query to the page that earned most of its impressions that day.
    # A query can surface several URLs; gsc_queries has one row per (date, query),
    # so the top page is the only attribution that fits without changing the key.
    best = {}
    for row in _query(svc, property_url, start, end, ['date', 'query', 'page'], row_limit=25000):
        d, q, pg = row['keys'][0], row['keys'][1].lower(), row['keys'][2]
        cur = best.get((d, q))
        if cur is None or row['impressions'] > cur[1]:
            best[(d, q)] = (pg, row['impressions'])
    for (d, q), (pg, _imp) in best.items():
        rec = days_out.get(d, {}).get('queries', {}).get(q)
        if rec is not None:
            rec['page'] = pg

    return days_out


def fetch(property_url: str, days: int = 7, end_offset: int = 3) -> dict:
    """Fetch one period of GSC data. Returns dict with queries, pages, countries, devices."""
    svc = _service()
    start, end = _date_range(days, end_offset)

    queries, pages, countries, devices = {}, {}, {}, {}

    for row in _query(svc, property_url, start, end, ['query']):
        q = row['keys'][0].lower()
        queries[q] = {
            'clicks': row['clicks'], 'impressions': row['impressions'],
            'ctr': round(row['ctr'] * 100, 2), 'position': round(row['position'], 2)
        }
    for row in _query(svc, property_url, start, end, ['page']):
        pages[row['keys'][0]] = {
            'clicks': row['clicks'], 'impressions': row['impressions'],
            'position': round(row['position'], 2)
        }
    for row in _query(svc, property_url, start, end, ['country'], row_limit=50):
        countries[row['keys'][0].upper()] = {
            'clicks': row['clicks'], 'impressions': row['impressions'],
            'ctr': round(row['ctr'] * 100, 2)
        }
    for row in _query(svc, property_url, start, end, ['device']):
        devices[row['keys'][0].upper()] = {
            'clicks': row['clicks'], 'impressions': row['impressions']
        }

    return {'queries': queries, 'pages': pages, 'countries': countries,
            'devices': devices, 'start': start, 'end': end}

def fetch_comparison(property_url: str) -> dict:
    """This week + previous week for reporting, plus per-day rows for the DB.

    'this'/'prev' stay 7-day aggregates because the weekly report is written in
    those terms. 'daily' is what gets persisted — see fetch_daily().
    """
    print(f'  Fetching GSC: this week + prev week')
    this = fetch(property_url, days=7, end_offset=3)
    prev = fetch(property_url, days=7, end_offset=10)
    daily = fetch_daily(property_url, days=17, end_offset=3)
    print(f'  This week: {len(this["queries"])} queries, {len(this["pages"])} pages')
    print(f'  Prev week: {len(prev["queries"])} queries')
    print(f'  Daily rows: {len(daily)} days')
    return {'this': this, 'prev': prev, 'daily': daily}

if __name__ == '__main__':
    from core.config import GSC_PROPERTY
    data = fetch_comparison(GSC_PROPERTY)
    print(f'Queries this week: {len(data["this"]["queries"])}')
    print(f'Countries: {list(data["this"]["countries"].keys())}')
