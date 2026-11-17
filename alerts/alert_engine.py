"""
RankPilot — Alerts Engine
Detects critical SEO events and sends immediate email alerts.
Runs daily (separate from weekly full report).

Alert types:
  rank_drop           — keyword drops > 5 positions overnight
  lost_backlink       — high-value backlink marked as lost
  competitor_page     — competitor published a new page
  pagespeed_drop      — mobile score dropped > 10 points
  site_down           — our site returned 5xx / timed out
  low_ctr_page        — page with >100 impressions and <2% CTR
  unexpected_noindex  — page has noindex but is not on the allowlist
"""
import os, sys, requests
from datetime import date, timedelta, datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import TARGET_DOMAIN, SMTP_USER, SMTP_PASS, REPORT_RECIPIENTS, ALERT_COOLDOWN_HOURS
from core.db import (get_session, Site, Ranking, Keyword, Backlink,
                     CompetitorUrl, PageSpeed, Alert)
from utils.logger import get_logger
log = get_logger(__name__)

ALERT_EMAIL_CAPS = {
    'rank_drop':          5,
    'lost_backlink':      3,
    'competitor_page':    10,
    'pagespeed_drop':     2,
    'low_ctr_page':       5,
    'unexpected_noindex': 10,
}


def _send_alert_email(subject: str, body: str):
    """Send alert email using existing SMTP credentials."""
    if not SMTP_USER or not SMTP_PASS:
        print(f'  ℹ️ Alert email skipped (SMTP not configured): {subject}')
        return
    try:
        import smtplib
        from email.mime.text import MIMEText
        msg = MIMEText(body, 'plain')
        msg['Subject'] = f'🚨 RankPilot Alert: {subject}'
        msg['From']    = SMTP_USER
        msg['To']      = ', '.join(REPORT_RECIPIENTS)
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(SMTP_USER, SMTP_PASS)
            smtp.sendmail(SMTP_USER, REPORT_RECIPIENTS, msg.as_string())
        print(f'  ✅ Alert email sent: {subject}')
    except Exception as e:
        print(f'  ⚠️ Alert email failed: {e}')


def _save_alert(site_id: int, alert_type: str, severity: str,
                message: str, details: dict, send_email: bool = True):
    """Save alert to DB and optionally email it."""
    with get_session() as s:
        # Avoid duplicate alerts for same type within cooldown window
        existing = s.query(Alert).filter_by(
            site_id=site_id, alert_type=alert_type
        ).filter(Alert.created_at >= datetime.utcnow() - timedelta(hours=ALERT_COOLDOWN_HOURS)).first()
        if existing:
            return  # already alerted this window

        alert = Alert(
            site_id=site_id, alert_type=alert_type,
            severity=severity, message=message,
            details=details, is_emailed=send_email
        )
        s.add(alert)
        s.commit()

    if send_email and severity in ('critical', 'warning'):
        body = f'{message}\n\nDetails:\n{_fmt_dict(details)}'
        _send_alert_email(alert_type.replace('_', ' ').title(), body)


def _fmt_dict(d: dict) -> str:
    return '\n'.join(f'  {k}: {v}' for k, v in d.items())


# ── Alert checks ──────────────────────────────────────────────────────────────

def check_rank_drops(site_id: int, drop_threshold: int = 5) -> list[dict]:
    """Alert when any tracked keyword drops > threshold positions."""
    today     = date.today()
    yesterday = today - timedelta(days=1)
    alerts    = []

    with get_session() as s:
        today_ranks = (s.query(Ranking, Keyword)
                       .join(Keyword)
                       .filter(Keyword.site_id == site_id, Ranking.date == today)
                       .all())
        yesterday_map = {
            r.keyword_id: r.position
            for r, _ in s.query(Ranking, Keyword)
                          .join(Keyword)
                          .filter(Keyword.site_id == site_id, Ranking.date == yesterday)
                          .all()
            if r.position
        }

    for ranking, kw in today_ranks:
        if not ranking.position:
            continue
        prev = yesterday_map.get(kw.id)
        if prev and (ranking.position - prev) >= drop_threshold:
            drop = ranking.position - prev
            msg  = (f'"{kw.keyword}" dropped {drop} positions: '
                    f'pos {prev} → pos {ranking.position}')
            alerts.append({'keyword': kw.keyword, 'from': prev, 'to': ranking.position})
            _save_alert(site_id, 'rank_drop', 'critical', msg,
                        {'keyword': kw.keyword, 'from_pos': prev,
                         'to_pos': ranking.position, 'drop': drop})

    return alerts


def check_lost_backlinks(site_id: int) -> list[dict]:
    """Alert when backlinks are marked as lost this week."""
    cutoff = date.today() - timedelta(days=7)
    alerts = []

    with get_session() as s:
        lost = (s.query(Backlink)
                .filter_by(site_id=site_id, status='lost')
                .filter(Backlink.last_seen >= cutoff)
                .all())

    for bl in lost:
        msg = f'Lost backlink from {bl.source_domain}: {bl.anchor_text or "no anchor"}'
        alerts.append({'domain': bl.source_domain, 'anchor': bl.anchor_text})
        _save_alert(site_id, 'lost_backlink', 'warning', msg,
                    {'source_domain': bl.source_domain,
                     'source_url':    bl.source_url,
                     'anchor':        bl.anchor_text},
                    send_email=len(lost) <= 3)  # batch: only email if few losses

    if lost:
        print(f'  ⚠️ {len(lost)} lost backlinks detected this week')
    return alerts


def check_competitor_new_pages(site_id: int) -> list[dict]:
    """Alert when competitors publish new pages."""
    cutoff = date.today() - timedelta(days=2)
    alerts = []

    with get_session() as s:
        from core.db import Competitor
        new_pages = (s.query(CompetitorUrl, Competitor)
                     .join(Competitor)
                     .filter(Competitor.site_id == site_id)
                     .filter(CompetitorUrl.first_seen >= cutoff,
                             CompetitorUrl.is_new == True)
                     .all())

    for page, comp in new_pages:
        msg = f'{comp.domain} published new page: {page.title or page.url}'
        alerts.append({'competitor': comp.domain, 'url': page.url, 'title': page.title})
        _save_alert(site_id, 'competitor_page', 'info', msg,
                    {'competitor': comp.domain, 'url': page.url, 'title': page.title or ''},
                    send_email=False)

    return alerts


def check_pagespeed_drops(site_id: int, drop_threshold: int = 10) -> list[dict]:
    """Alert when mobile PageSpeed score drops significantly between the last two recorded dates."""
    alerts = []

    with get_session() as s:
        # Find the two most recent distinct dates with mobile data for this site
        distinct_dates = (s.query(PageSpeed.date)
                          .filter_by(site_id=site_id, strategy='mobile')
                          .distinct()
                          .order_by(PageSpeed.date.desc())
                          .limit(2)
                          .all())

    if len(distinct_dates) < 2:
        log.info('pagespeed_drop: fewer than 2 dates of data, skipping comparison')
        return alerts

    latest_date, prev_date = distinct_dates[0][0], distinct_dates[1][0]

    with get_session() as s:
        latest_scores = {r.page_url: r.performance for r in
                         s.query(PageSpeed)
                         .filter_by(site_id=site_id, date=latest_date, strategy='mobile')
                         .all()
                         if r.performance is not None}
        prev_scores   = {r.page_url: r.performance for r in
                         s.query(PageSpeed)
                         .filter_by(site_id=site_id, date=prev_date, strategy='mobile')
                         .all()
                         if r.performance is not None}

    for url, score in latest_scores.items():
        prev = prev_scores.get(url)
        if prev is None:
            continue
        diff = prev - score
        if diff >= drop_threshold:
            from urllib.parse import urlparse
            page_path = urlparse(url).path or '/'
            msg = f'Mobile score for {page_path} dropped {prev}→{score} (-{diff} pts)'
            alerts.append({'url': url, 'from': prev, 'to': score, 'diff': diff})
            _save_alert(site_id, 'pagespeed_drop', 'warning', msg,
                        {'url': url, 'page_path': page_path,
                         'from_score': prev, 'to_score': score,
                         'diff': diff,
                         'latest_date': str(latest_date), 'prev_date': str(prev_date)})

    return alerts


def check_site_health(site_domain: str = TARGET_DOMAIN) -> dict:
    """
    Check homepage and most-important page. Returns health dict.
    Creates a site_down alert if any key URL is 5xx or times out.
    """
    key_urls = [
        f'https://{site_domain}/',
        f'https://{site_domain}/nri-property-dispute-lawyer/',
    ]
    status_codes   = {}
    response_times = []
    any_down       = False

    for url in key_urls:
        try:
            import time as _time
            t0 = _time.monotonic()
            resp = requests.get(url, timeout=10, allow_redirects=True)
            elapsed_ms = int((_time.monotonic() - t0) * 1000)
            status_codes[url]   = resp.status_code
            response_times.append(elapsed_ms)
            if resp.status_code >= 500:
                log.warning('site_down: %s returned HTTP %s', url, resp.status_code)
                any_down = True
        except requests.exceptions.Timeout:
            log.warning('site_down: %s timed out', url)
            status_codes[url] = 'timeout'
            any_down = True
        except Exception as exc:
            log.warning('site_down: %s error — %s', url, exc)
            status_codes[url] = 'error'
            any_down = True

    # A local network failure makes every request fail identically, which is
    # indistinguishable from an outage if you only probe our own site. Before
    # calling the site down on transport errors alone, check that anything else
    # on the internet is reachable. On 2026-09-01 every host — Serper, DataForSEO,
    # Reddit, GitHub and the site — failed with the same SSL EOF, and this raised
    # a critical "site is down" alert for a site that was serving fine.
    transport_only = any_down and all(
        v in ('timeout', 'error') for v in status_codes.values()
    )
    egress_ok = None
    if transport_only:
        egress_ok = _egress_reachable()
        if egress_ok is False:
            log.warning('site_down suppressed: no outbound connectivity from this host')
            any_down = False

    avg_ms = int(sum(response_times) / len(response_times)) if response_times else 0
    return {
        'up':              not any_down,
        'status_codes':    status_codes,
        'response_time_ms': avg_ms,
        'egress_ok':       egress_ok,
    }


def _egress_reachable() -> bool:
    """Can this machine reach anything at all? Used to tell an outage from our
    own dead network. Two independent hosts so one being down is not decisive."""
    for url in ('https://www.cloudflare.com/cdn-cgi/trace',
                'https://api.github.com/'):
        try:
            requests.get(url, timeout=8)
            return True
        except Exception:
            continue
    return False


INTENTIONAL_NOINDEX = {'/404/', '/thank-you/', '/budget-2020-and-impact-on-nris/'}

# Paths under here are admin machinery, not public pages: CMS revision snapshots,
# the editor seed page, the data directory. noindex on them is correct and must
# not raise a critical alert — one revision snapshot fired daily for weeks.
NOINDEX_EXEMPT_PREFIXES = ('/admin/',)


def check_low_ctr_pages(site_id: int, min_impressions: int = 100, max_ctr: float = 0.02) -> list[dict]:
    """Flag pages with >min_impressions and <max_ctr CTR — title/meta rewrite opportunity."""
    from core.db import GscPage
    from sqlalchemy import func
    with get_session() as s:
        latest = s.query(func.max(GscPage.date)).filter_by(site_id=site_id).scalar()
        if not latest:
            return []
        rows = s.query(GscPage).filter(
            GscPage.site_id == site_id,
            GscPage.date == latest,
            GscPage.impressions >= min_impressions,
        ).all()
    found = []
    for r in rows:
        ctr = (r.clicks or 0) / r.impressions if r.impressions else 1
        if ctr < max_ctr:
            found.append({'page': r.page, 'impressions': r.impressions,
                          'clicks': r.clicks or 0, 'ctr': round(ctr * 100, 2),
                          'position': r.position})
    found.sort(key=lambda x: -x['impressions'])
    for item in found[:5]:
        slug = item['page'].replace(f'https://{TARGET_DOMAIN}', '') or '/'
        _save_alert(
            site_id, 'low_ctr_page', 'warning',
            f'Low CTR ({item["ctr"]}%) on {slug} — {item["impressions"]:,} impressions wasted',
            item, send_email=False,
        )
    return found


def check_noindex_monitor(site_id: int) -> list[dict]:
    """Alert when a page has noindex but is not on the intentional allowlist."""
    from core.db import SiteCrawlPage
    with get_session() as s:
        rows = s.query(SiteCrawlPage).filter_by(site_id=site_id, is_noindex=True).all()
    unexpected = []
    for r in rows:
        slug = r.url.replace(f'https://{TARGET_DOMAIN}', '').rstrip('/') + '/'
        if slug.startswith(NOINDEX_EXEMPT_PREFIXES):
            continue
        if slug not in INTENTIONAL_NOINDEX:
            unexpected.append({'url': r.url, 'slug': slug})
            _save_alert(
                site_id, 'unexpected_noindex', 'critical',
                f'Unexpected noindex on {slug} — Google will not index this page',
                {'url': r.url}, send_email=True,
            )
    return unexpected


def _send_batch_digest(site_id: int, all_alerts: dict):
    """Send one batched email digest with all alert types grouped."""
    total = sum(len(v) for v in all_alerts.values())
    if total == 0:
        return
    lines = [f'RankPilot detected {total} SEO event(s) requiring attention:\n']
    for alert_type, alerts in all_alerts.items():
        if not alerts:
            continue
        lines.append(f'{alert_type.replace("_", " ").upper()} ({len(alerts)}):')
        for a in alerts[:ALERT_EMAIL_CAPS.get(alert_type, 5)]:
            lines.append(f'  • {a.get("message", str(a))}')
        if len(alerts) > ALERT_EMAIL_CAPS.get(alert_type, 5):
            lines.append(f'  ... and {len(alerts) - ALERT_EMAIL_CAPS[alert_type]} more (see dashboard)')
        lines.append('')
    _send_alert_email(f'{total} SEO alerts need attention', '\n'.join(lines))


def run_alerts(site_domain: str = TARGET_DOMAIN) -> dict:
    """
    Run all alert checks. Sends one batched digest instead of per-alert emails.
    """
    with get_session() as s:
        site = s.query(Site).filter_by(domain=site_domain).first()
        if not site:
            return {}
        site_id = site.id

    print(f'  Running alert checks for {site_domain}...')

    health = check_site_health(site_domain)
    is_up  = health['up']
    log.info('site_health: up=%s status_codes=%s response_time_ms=%s',
             is_up, health['status_codes'], health['response_time_ms'])
    if not is_up:
        _save_alert(site_id, 'site_down', 'critical',
                    f'{site_domain} is returning errors or timing out',
                    {'domain': site_domain,
                     'status_codes': health['status_codes'],
                     'response_time_ms': health['response_time_ms'],
                     'time': datetime.utcnow().isoformat()},
                    send_email=False)

    rank_alerts    = check_rank_drops(site_id)
    bl_alerts      = check_lost_backlinks(site_id)
    comp_alerts    = check_competitor_new_pages(site_id)
    speed_alerts   = check_pagespeed_drops(site_id)
    ctr_alerts     = check_low_ctr_pages(site_id)
    noindex_alerts = check_noindex_monitor(site_id)

    # SERP volatility check
    try:
        from collectors.serp_volatility import calculate_volatility
        vol = calculate_volatility(site_domain)
        if vol.get('suspected_update'):
            _save_alert(site_id, 'serp_volatility', 'warning',
                        f'Possible Google algo update — volatility score {vol["score"]:.1f}',
                        vol, send_email=False)
    except Exception:
        pass

    total = len(rank_alerts) + len(bl_alerts) + len(comp_alerts) + len(speed_alerts)

    # Send one digest email instead of per-alert spam
    if total > 0 or not is_up:
        digest = {
            'rank_drop':          [{'message': f'"{a["keyword"]}" dropped {a["from"]}→{a["to"]}'} for a in rank_alerts],
            'lost_backlink':      [{'message': f'Lost: {a["domain"]} ({a.get("anchor","")})'}       for a in bl_alerts],
            'competitor_page':    [{'message': f'{a["competitor"]}: {a.get("title") or a["url"]}'}  for a in comp_alerts],
            'pagespeed_drop':     [{'message': f'Speed drop {a["from"]}→{a["to"]}: {a["url"]}'}     for a in speed_alerts],
        }
        _send_batch_digest(site_id, digest)

    if noindex_alerts:
        digest_ni = {'unexpected_noindex': [{'message': f'Unexpected noindex: {a["slug"]}'} for a in noindex_alerts]}
        _send_batch_digest(site_id, digest_ni)

    print(f'  ✅ Alerts: {len(rank_alerts)} rank drops, {len(bl_alerts)} lost backlinks, '
          f'{len(comp_alerts)} competitor pages, {len(speed_alerts)} speed drops, '
          f'{len(ctr_alerts)} low-CTR pages, {len(noindex_alerts)} unexpected noindex')

    return {
        'site_up':           is_up,
        'rank_drops':        rank_alerts,
        'lost_backlinks':    bl_alerts,
        'competitor_pages':  comp_alerts,
        'speed_drops':       speed_alerts,
        'low_ctr_pages':     ctr_alerts,
        'noindex_unexpected': noindex_alerts,
        'total':             total,
    }


if __name__ == '__main__':
    result = run_alerts()
    print(f'Total alerts: {result["total"]}')
