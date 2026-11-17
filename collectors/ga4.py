"""
RankPilot — GA4 Collector
Fetches this week + prev week conversions, sessions, sources.
"""
import os, sys, json
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import GOOGLE_OAUTH_TOKEN_PATH, GOOGLE_SERVICE_ACCOUNT_PATH


def _get_credentials():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    if os.path.exists(GOOGLE_SERVICE_ACCOUNT_PATH):
        from google.oauth2 import service_account
        try:
            sa = service_account.Credentials.from_service_account_file(
                GOOGLE_SERVICE_ACCOUNT_PATH,
                scopes=['https://www.googleapis.com/auth/analytics.readonly'])
            sa.refresh(Request())  # validate now — the SA key on disk may be revoked
            return sa
        except Exception as e:
            print(f'  ℹ️ Service account unusable ({type(e).__name__}) — falling back to user OAuth token')
    with open(GOOGLE_OAUTH_TOKEN_PATH) as f:
        data = json.load(f)
    creds = Credentials(
        token=data['token'], refresh_token=data['refresh_token'],
        token_uri=data['token_uri'], client_id=data['client_id'],
        client_secret=data['client_secret'], scopes=data['scopes']
    )
    # Always refresh: the stored token has no expiry field here, so creds.expired
    # reads False and the GA4 gRPC client (unlike GSC's REST client) won't
    # auto-refresh on 401 — it just fails. We always hold a refresh_token.
    try:
        creds.refresh(Request())
    except Exception as e:
        raise RuntimeError(
            f'OAuth token refresh failed ({e}) — refresh_token is dead. '
            f'Re-authenticate: python3 seo_engine/reauth.py'
        ) from e
    data['token'] = creds.token
    with open(GOOGLE_OAUTH_TOKEN_PATH, 'w') as f:
        json.dump(data, f)
    return creds


def fetch(property_id: str, days: int = 7) -> dict:
    """
    Fetch this week + previous week GA4 data.
    Returns dict with conversions, sessions, landing pages, sources for both periods.
    """
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    from google.analytics.data_v1beta.types import (
        RunReportRequest, Metric, Dimension, DateRange
    )

    creds  = _get_credentials()
    client = BetaAnalyticsDataClient(credentials=creds)

    today  = datetime.now(timezone.utc)
    end1   = today.strftime('%Y-%m-%d')
    start1 = (today - timedelta(days=days-1)).strftime('%Y-%m-%d')
    end2   = (today - timedelta(days=days)).strftime('%Y-%m-%d')
    start2 = (today - timedelta(days=days*2-1)).strftime('%Y-%m-%d')

    def run(dimensions, metrics, date_ranges):
        return client.run_report(RunReportRequest(
            property=f'properties/{property_id}',
            date_ranges=date_ranges,
            dimensions=[Dimension(name=d) for d in dimensions],
            metrics=[Metric(name=m) for m in metrics]
        ))

    # Events both periods — dateRange is auto-added, don't list it as dimension
    ev = run(['eventName'], ['eventCount'],
             [DateRange(start_date=start1, end_date=end1, name='this'),
              DateRange(start_date=start2, end_date=end2, name='prev')])
    events = {'this': {}, 'prev': {}}
    for row in ev.rows:
        name   = row.dimension_values[0].value
        # When multiple date ranges given, last dimension_value is the dateRange name
        period = row.dimension_values[-1].value if len(row.dimension_values) > 1 else 'this'
        count  = int(row.metric_values[0].value)
        if period in events:
            events[period][name] = events[period].get(name, 0) + count

    # Sessions both periods
    sr = run([], ['sessions'],
             [DateRange(start_date=start1, end_date=end1, name='this'),
              DateRange(start_date=start2, end_date=end2, name='prev')])
    sessions = {'this': 0, 'prev': 0}
    for row in sr.rows:
        period = row.dimension_values[0].value if row.dimension_values else 'this'
        if period in sessions:
            sessions[period] = int(row.metric_values[0].value)

    # Top landing pages (this week)
    pr = client.run_report(RunReportRequest(
        property=f'properties/{property_id}',
        date_ranges=[DateRange(start_date=start1, end_date=end1)],
        dimensions=[Dimension(name='landingPage')],
        metrics=[Metric(name='sessions'), Metric(name='eventCount')],
        limit=10
    ))
    landing_pages = [{'page': row.dimension_values[0].value,
                      'sessions': int(row.metric_values[0].value),
                      'events': int(row.metric_values[1].value)}
                     for row in pr.rows]

    # Traffic source (this week)
    source_resp = client.run_report(RunReportRequest(
        property=f'properties/{property_id}',
        date_ranges=[DateRange(start_date=start1, end_date=end1)],
        dimensions=[Dimension(name='sessionDefaultChannelGroup')],
        metrics=[Metric(name='sessions')],
        limit=8
    ))
    sources = {row.dimension_values[0].value: int(row.metric_values[0].value)
               for row in source_resp.rows}

    def conv(period):
        e = events[period]
        return {
            'contact_form_submit': e.get('contact_form_submit', 0),
            'whatsapp_click':      e.get('whatsapp_click', 0),
            'phone_click':         e.get('phone_click', 0),
        }

    return {
        'this': conv('this'), 'prev': conv('prev'),
        'sessions': sessions, 'landing_pages': landing_pages,
        'sources': sources, 'start': start1, 'end': end1
    }

LEAD_EVENTS = ('contact_form_submit', 'whatsapp_click', 'phone_click')


def fetch_daily(property_id: str, days: int = 30) -> dict:
    """Per-day, per-channel sessions and lead events.

    fetch() returns 7-day aggregates and save_to_db() stored them against
    date=today, so every ga4_sessions row was a rolling week labelled as one day —
    the same inflation GSC had. Worse, the site-wide conversion total was copied
    onto every channel row, so sum(conversions) multiplied by the number of
    channels reporting that day (5x on a typical day).

    Asking for the date and channel dimensions gives rows that are correct to sum
    on both axes, and backfills any day a previous run missed.
    """
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    from google.analytics.data_v1beta.types import (
        RunReportRequest, Metric, Dimension, DateRange
    )

    client = BetaAnalyticsDataClient(credentials=_get_credentials())
    today  = datetime.now(timezone.utc)
    end    = today.strftime('%Y-%m-%d')
    start  = (today - timedelta(days=days - 1)).strftime('%Y-%m-%d')
    rng    = [DateRange(start_date=start, end_date=end)]

    def run(dims, metrics, limit=100000):
        return client.run_report(RunReportRequest(
            property=f'properties/{property_id}', date_ranges=rng,
            dimensions=[Dimension(name=d) for d in dims],
            metrics=[Metric(name=m) for m in metrics], limit=limit))

    out = {}

    def slot(d, ch):
        return out.setdefault(d, {}).setdefault(
            ch, {'sessions': 0, 'events': {}, 'conversions': 0})

    for row in run(['date', 'sessionDefaultChannelGroup'], ['sessions']).rows:
        d, ch = row.dimension_values[0].value, row.dimension_values[1].value
        slot(_iso(d), ch)['sessions'] = int(row.metric_values[0].value)

    for row in run(['date', 'sessionDefaultChannelGroup', 'eventName'],
                   ['eventCount']).rows:
        d, ch, ev = (row.dimension_values[0].value,
                     row.dimension_values[1].value,
                     row.dimension_values[2].value)
        if ev not in LEAD_EVENTS:
            continue
        rec = slot(_iso(d), ch)
        n = int(row.metric_values[0].value)
        rec['events'][ev] = rec['events'].get(ev, 0) + n
        rec['conversions'] += n

    return out


def _iso(yyyymmdd: str) -> str:
    """GA4 returns the date dimension as YYYYMMDD."""
    return f'{yyyymmdd[0:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:8]}'


def save_daily_to_db(daily: dict, site_domain: str) -> int:
    """Upsert per-day, per-channel rows. Conversions belong to their own channel."""
    from datetime import datetime as dt_
    from core.db import get_session, Ga4Session, Site
    written = 0
    with get_session() as s:
        site = s.query(Site).filter_by(domain=site_domain).first()
        if not site:
            return 0
        for day, channels in daily.items():
            day_date = dt_.strptime(day, '%Y-%m-%d').date()
            for channel, v in channels.items():
                existing = s.query(Ga4Session).filter_by(
                    site_id=site.id, date=day_date, channel=channel
                ).first()
                if existing:
                    existing.sessions    = v['sessions']
                    existing.conversions = v['conversions']
                    existing.events      = v['events']
                    existing.window_days = 1
                else:
                    s.add(Ga4Session(
                        site_id=site.id, date=day_date, channel=channel,
                        sessions=v['sessions'], conversions=v['conversions'],
                        events=v['events'], window_days=1))
                written += 1
        s.commit()
    return written


def save_to_db(data: dict, site_domain: str) -> int:
    """Save GA4 fetch results to ga4_sessions table. Returns rows written."""
    from datetime import date as date_
    from core.db import get_session, Ga4Session, Site
    with get_session() as s:
        site = s.query(Site).filter_by(domain=site_domain).first()
        if not site:
            return 0
        today = date_.today()
        total_conv = sum(data.get('this', {}).values())
        for channel, sess_count in data.get('sources', {}).items():
            existing = s.query(Ga4Session).filter_by(
                site_id=site.id, date=today, channel=channel
            ).first()
            if existing:
                existing.sessions    = sess_count
                existing.conversions = total_conv
                existing.events      = data.get('this', {})
            else:
                s.add(Ga4Session(
                    site_id=site.id, date=today, channel=channel,
                    sessions=sess_count, conversions=total_conv,
                    events=data.get('this', {})
                ))
        s.commit()
        return len(data.get('sources', {}))


if __name__ == '__main__':
    from core.config import GA4_PROPERTY_ID, TARGET_DOMAIN
    if not GA4_PROPERTY_ID:
        print('Set GA4_PROPERTY_ID in .env')
    else:
        d = fetch(GA4_PROPERTY_ID)
        t = d['this']
        print(f'Sessions this week:  {d["sessions"]["this"]}')
        print(f'Total leads (this):  {sum(t.values())}')
        save_to_db(d, TARGET_DOMAIN)
        print('Saved to DB')
