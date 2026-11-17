"""
RankPilot — Rank Tracker
Checks our position for tracked keywords using ValueSERP (or Scrapingdog fallback).
Saves results to rankings table.
"""
import os, sys, time, requests
from datetime import date
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import (VALUESERP_KEY, SCRAPINGDOG_KEY, SERPER_KEY,
                         TARGET_DOMAIN, TRACK_MOBILE, LOCAL_RANK_TARGETS)
from core.db import get_session, Keyword, Ranking, Site
from utils.logger import get_logger
log = get_logger(__name__)

COUNTRY_GL = {
    'IN': 'in', 'US': 'us', 'GB': 'gb', 'CA': 'ca',
    'AE': 'ae', 'AU': 'au', 'SG': 'sg'
}

def check_rank_valueserp(keyword: str, country: str, domain: str) -> dict:
    """Check SERP position using ValueSERP API."""
    if not VALUESERP_KEY:
        return {'position': None, 'url': None, 'serp_features': {}, 'error': 'no_key'}

    params = {
        'api_key': VALUESERP_KEY,
        'q': keyword,
        'gl': COUNTRY_GL.get(country, 'in'),
        'hl': 'en',
        'num': '100',
        'output': 'json'
    }
    try:
        r = requests.get('https://api.valueserp.com/search', params=params, timeout=30)
        if r.status_code != 200:
            return {'position': None, 'url': None, 'serp_features': {}}

        data = r.json()
        results = data.get('organic_results', [])
        serp_features = {
            'featured_snippet': bool(data.get('answer_box')),
            'paa':              bool(data.get('related_questions')),
            'local_pack':       bool(data.get('local_results')),
            'video_pack':       bool(data.get('inline_videos')),
        }

        for i, result in enumerate(results, 1):
            result_url = result.get('link', '')
            if domain.lower() in result_url.lower():
                return {
                    'position': i,
                    'url': result_url,
                    'serp_features': serp_features
                }

        return {'position': None, 'url': None, 'serp_features': serp_features}

    except Exception as e:
        print(f'    ⚠️ ValueSERP error for "{keyword}": {e}')
        return {'position': None, 'url': None, 'serp_features': {}}

def check_rank_scrapingdog(keyword: str, country: str, domain: str) -> dict:
    """Fallback rank checker using Scrapingdog."""
    if not SCRAPINGDOG_KEY:
        return {'position': None, 'url': None, 'serp_features': {}}

    params = {
        'api_key': SCRAPINGDOG_KEY,
        'query': keyword,
        'country': COUNTRY_GL.get(country, 'in'),
        'results': 100
    }
    try:
        r = requests.get('https://api.scrapingdog.com/google', params=params, timeout=30)
        if r.status_code != 200:
            return {'position': None, 'url': None, 'serp_features': {}}

        results = r.json().get('organic_results', [])
        for i, result in enumerate(results, 1):
            if domain.lower() in result.get('link', '').lower():
                return {'position': i, 'url': result.get('link'), 'serp_features': {}}

        return {'position': None, 'url': None, 'serp_features': {}}
    except Exception as e:
        print(f'    ⚠️ Scrapingdog error: {e}')
        return {'position': None, 'url': None, 'serp_features': {}}

def check_rank_serper(keyword: str, country: str, domain: str,
                      location: str = '', device: str = 'desktop') -> dict:
    """Check SERP position using Serper.dev (2,500 free/month)."""
    if not SERPER_KEY:
        return {'position': None, 'url': None, 'serp_features': {}, 'error': 'no_key'}
    payload = {
        'q': keyword,
        'gl': COUNTRY_GL.get(country, 'in'),
        'hl': 'en',
        'num': 100,
    }
    if location:
        payload['location'] = location
    if device == 'mobile':
        payload['device'] = 'mobile'
    try:
        r = requests.post(
            'https://google.serper.dev/search',
            headers={'X-API-KEY': SERPER_KEY, 'Content-Type': 'application/json'},
            json=payload, timeout=20
        )
        if r.status_code != 200:
            log.error(f'Serper HTTP {r.status_code} for "{keyword}": {r.text[:120]}')
            return {'position': None, 'url': None, 'serp_features': {},
                    'error': f'http_{r.status_code}'}
        data = r.json()
        serp_features = {
            'featured_snippet': bool(data.get('answerBox')),
            'paa':              bool(data.get('peopleAlsoAsk')),
            'local_pack':       bool(data.get('localResults')),
            'video_pack':       bool(data.get('videos')),
        }
        for i, res in enumerate(data.get('organic', []), 1):
            if domain.lower() in res.get('link', '').lower():
                return {'position': i, 'url': res['link'], 'serp_features': serp_features}
        return {'position': None, 'url': None, 'serp_features': serp_features}
    except Exception as e:
        print(f'    ⚠️ Serper error for "{keyword}": {e}')
        return {'position': None, 'url': None, 'serp_features': {}}


_serper_quota_exhausted = False  # module-level flag; set on 400 to skip further Serper calls


def check_rank(keyword: str, country: str, domain: str,
               location: str = '', device: str = 'desktop') -> dict:
    """Check rank: ValueSERP (national, free) → Serper (location/mobile) → Scrapingdog.
    ValueSERP is the primary for national queries to preserve Serper monthly quota (2,500 free).
    """
    global _serper_quota_exhausted
    # For location-specific or mobile queries, only Serper supports them
    if location or device == 'mobile':
        if SERPER_KEY and not _serper_quota_exhausted:
            result = check_rank_serper(keyword, country, domain, location, device)
            if result.get('error') == 'http_400':
                _serper_quota_exhausted = True
            return result
        return {'position': None, 'url': None, 'serp_features': {}, 'error': 'serper_quota_exhausted'}
    # For national queries: ValueSERP first (preserves Serper quota)
    if VALUESERP_KEY:
        return check_rank_valueserp(keyword, country, domain)
    if SERPER_KEY and not _serper_quota_exhausted:
        result = check_rank_serper(keyword, country, domain)
        if result.get('error') == 'http_400':
            _serper_quota_exhausted = True
        return result
    if SCRAPINGDOG_KEY:
        return check_rank_scrapingdog(keyword, country, domain)
    return {'position': None, 'url': None, 'serp_features': {},
            'error': 'no_serp_api_key'}


def _save_ranking(kw_id: int, result: dict, today: date,
                  location: str = 'national', device: str = 'desktop'):
    with get_session() as s:
        existing = (s.query(Ranking)
                    .filter_by(keyword_id=kw_id, date=today)
                    .first())
        if existing:
            existing.position      = result.get('position')
            existing.url           = result.get('url')
            existing.serp_features = result.get('serp_features', {})
        else:
            s.add(Ranking(
                keyword_id=kw_id, date=today,
                position=result.get('position'),
                url=result.get('url'),
                serp_features=result.get('serp_features', {}),
            ))
        s.commit()


def _warn_if_ranks_stale(max_age_days: int = 14):
    """Say out loud how old the stored positions are when a run writes nothing.

    Every consumer reads `rankings` as if it were current. A run that aborts
    leaves the last good rows in place, so staleness is invisible unless it is
    reported here.
    """
    from datetime import date as _date
    try:
        with get_session() as s:
            newest = (s.query(Ranking.date)
                      .filter(Ranking.position.isnot(None))
                      .order_by(Ranking.date.desc()).first())
    except Exception:
        return
    if not newest or not newest[0]:
        print('  ⚠️  No rank data has ever been stored.')
        log.warning('rank data: empty')
        return
    age = (_date.today() - newest[0]).days
    msg = f'rank data stale since {newest[0]} ({age} days old)'
    if age > max_age_days:
        print(f'  ⚠️  {msg} — any position quoted in a report is from that date, not today')
        log.warning(msg)


def run_rank_tracking(site_domain: str = TARGET_DOMAIN,
                      priority_max: int = 2, dry_run: bool = False):
    """Check rankings for all tracked keywords up to priority_max."""
    global _serper_quota_exhausted
    with get_session() as s:
        site = s.query(Site).filter_by(domain=site_domain).first()
        if not site:
            print(f'Site {site_domain} not found in DB'); return
        keywords = (s.query(Keyword)
                    .filter_by(site_id=site.id)
                    .filter(Keyword.priority <= priority_max)
                    .all())

    if not keywords:
        print('No keywords to track. Run setup first.')
        return

    if not SERPER_KEY and not VALUESERP_KEY and not SCRAPINGDOG_KEY:
        print('⚠️  No SERP API key set. Add SERPER_KEY to .env')
        print('   Sign up free at: serper.dev (2,500 free/month)')
        _warn_if_ranks_stale()
        return

    print(f'Checking {len(keywords)} keywords for {site_domain}...')
    results = []
    today   = date.today()

    for i, kw in enumerate(keywords):
        result  = check_rank(kw.keyword, kw.country, site_domain)
        if result.get('error'):
            # API failure is not "not ranked" — abort so no fake NULL rows land
            print(f'  ✗ SERP API failed ("{result["error"]}") — aborting rank run, no rows written')
            log.error(f'rank tracking aborted: {result["error"]}')
            # Aborting silently is how positions went 95 days stale while weekly
            # reports kept quoting them as current. Say how old the data now is.
            _warn_if_ranks_stale()
            break
        pos_str = f'pos {result["position"]}' if result.get('position') else 'not found'
        print(f'  [{i+1}/{len(keywords)}] "{kw.keyword}" ({kw.country}) → {pos_str}')

        if not dry_run:
            _save_ranking(kw.id, result, today)

        results.append({'keyword': kw.keyword, 'country': kw.country, **result})
        time.sleep(0.3)

    # Local rank tracking for P1 keywords only (conserves free quota; skipped if Serper exhausted)
    if SERPER_KEY and not _serper_quota_exhausted:
        p1_keywords = [kw for kw in keywords if kw.priority <= 1]
        if p1_keywords:
            print(f'\n  Local tracking for {len(p1_keywords)} P1 keywords × {len(LOCAL_RANK_TARGETS)} cities...')
            for kw in p1_keywords:
                if _serper_quota_exhausted:
                    print('  ⚠️  Serper quota exhausted — skipping remaining local/mobile calls')
                    break
                for loc_name, loc_country in LOCAL_RANK_TARGETS:
                    res = check_rank_serper(kw.keyword, loc_country, site_domain, location=loc_name)
                    if res.get('error') == 'http_400':
                        _serper_quota_exhausted = True
                        print('  ⚠️  Serper quota exhausted — stopping local tracking')
                        break
                    pos_str = f'pos {res["position"]}' if res.get('position') else 'not found'
                    print(f'    "{kw.keyword}" @ {loc_name} → {pos_str}')
                    time.sleep(0.3)

        if TRACK_MOBILE and not _serper_quota_exhausted:
            print(f'\n  Mobile tracking for {len(p1_keywords)} P1 keywords...')
            for kw in p1_keywords:
                if _serper_quota_exhausted:
                    break
                res = check_rank_serper(kw.keyword, kw.country, site_domain, device='mobile')
                if res.get('error') == 'http_400':
                    _serper_quota_exhausted = True
                    break
                pos_str = f'pos {res["position"]}' if res.get('position') else 'not found'
                print(f'    "{kw.keyword}" mobile → {pos_str}')
                time.sleep(0.3)
    elif _serper_quota_exhausted:
        print('  ⚠️  Serper quota exhausted — local and mobile tracking skipped this run')

    return results


if __name__ == '__main__':
    run_rank_tracking(dry_run=True)
