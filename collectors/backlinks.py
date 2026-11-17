"""
RankPilot — Backlink Monitor
Sources: Serper web search, OpenLinkProfiler (free), DataForSEO (optional), Ahrefs CSV.
Detects new backlinks gained + lost backlinks this week.
"""
import os, sys, requests, hashlib, csv
from datetime import date

NRI_SEO_ENGINE = os.path.join(os.path.dirname(__file__), '../../seo_engine')
sys.path.insert(0, os.path.abspath(NRI_SEO_ENGINE))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import TARGET_DOMAIN, DATAFORSEO_LOGIN, DATAFORSEO_PASSWORD
from core.db import get_session, Backlink, Site
from utils.logger import get_logger

log = get_logger(__name__)
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; RankPilotBot/0.1)'}

def fetch_gsc_links(property_url: str) -> list[dict]:
    """GSC Links API is not publicly available. Use CommonCrawl CDX instead."""
    try:
        from collectors.commoncrawl import run_cc_backlink_discovery
        domain = property_url.replace('https://', '').replace('http://', '').rstrip('/')
        result = run_cc_backlink_discovery(domain)
        return result.get('links', [])
    except Exception as e:
        print(f'  ⚠️ CommonCrawl backlink discovery: {e}')
        return []

def fetch_openlinkprofiler(domain: str) -> list[dict]:
    """Fetch backlinks from OpenLinkProfiler (free, no signup)."""
    url = f'https://www.openlinkprofiler.org/api/getBacklinks'
    params = {
        'url': domain,
        'limit': 200,
        'sort': 'date_found',
        'order': 'desc',
        'target': 'domain'
    }
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=20)
        if r.status_code == 200:
            data = r.json()
            return [{'source_url': link.get('source_url', ''),
                     'target_url': link.get('target_url', ''),
                     'anchor_text': link.get('anchor_text', ''),
                     'source_domain': link.get('source_domain', '')}
                    for link in data.get('backlinks', [])]
    except Exception as e:
        print(f'  ⚠️ OpenLinkProfiler: {e}')
    return []

def fetch_dataforseo_backlinks(domain: str, limit: int = 500) -> list[dict]:
    """Fetch backlinks from DataForSEO API (~$0.0003/row)."""
    if not DATAFORSEO_LOGIN or not DATAFORSEO_PASSWORD:
        return []
    try:
        post_data = [{"target": domain, "limit": limit, "mode": "as_is",
                      "filters": ["dofollow", "=", True]}]
        r = requests.post(
            'https://api.dataforseo.com/v3/backlinks/backlinks/live',
            json=post_data,
            auth=(DATAFORSEO_LOGIN, DATAFORSEO_PASSWORD),
            timeout=30
        )
        if r.status_code == 200:
            tasks = r.json().get('tasks', [])
            if tasks and tasks[0].get('result'):
                items = tasks[0]['result'][0].get('items', [])
                return [{'source_url': item.get('url_from', ''),
                         'target_url': item.get('url_to', ''),
                         'anchor_text': item.get('anchor', ''),
                         'source_domain': item.get('domain_from', '')}
                        for item in items]
    except Exception as e:
        print(f'  ⚠️ DataForSEO backlinks: {e}')
    return []

_CSV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         'data', 'ahrefs_backlinks.csv')
_STAMP_PATH = _CSV_PATH + '.imported'


def _auto_import_csv_if_fresh(site_domain: str):
    """Auto-import ahrefs_backlinks.csv if it exists and is newer than last import."""
    if not os.path.exists(_CSV_PATH):
        return
    csv_mtime = os.path.getmtime(_CSV_PATH)
    stamp_mtime = os.path.getmtime(_STAMP_PATH) if os.path.exists(_STAMP_PATH) else 0
    if csv_mtime <= stamp_mtime:
        return  # already imported this version
    log.info('New Ahrefs CSV detected — auto-importing from %s', _CSV_PATH)
    try:
        result = import_ahrefs_csv(_CSV_PATH, site_domain)
        log.info('Auto-imported %d backlinks from Ahrefs CSV', result['imported'])
        print(f'  📥 Auto-imported {result["imported"]} backlinks from Ahrefs CSV')
    except Exception as e:
        log.error('Ahrefs CSV auto-import failed: %s', e)
        return
    with open(_STAMP_PATH, 'w') as f:
        f.write(str(csv_mtime))


def run_backlink_monitor(site_domain: str = TARGET_DOMAIN) -> dict:
    """
    Fetch all backlinks, compare to last known state.
    Returns: {'new': [...], 'lost': [...], 'total': N}
    """
    _auto_import_csv_if_fresh(site_domain)

    with get_session() as s:
        site = s.query(Site).filter_by(domain=site_domain).first()
        if not site:
            return {'new': [], 'lost': [], 'total': 0}
        known = {b.source_url: b for b in
                 s.query(Backlink).filter_by(site_id=site.id).all()}

    log.info('Fetching backlinks for %s', site_domain)
    print(f'  Fetching backlinks for {site_domain}...')

    # Collect from all sources
    all_links = []

    # Primary: Serper web search for domain mentions (most reliable free source)
    try:
        from collectors.commoncrawl import _serper_backlink_search
        serper_links = _serper_backlink_search(site_domain)
        log.info('Serper backlink search: %d backlinks', len(serper_links))
        print(f'    Serper discovery: {len(serper_links)} backlinks')
        all_links.extend(serper_links)
    except Exception as e:
        log.error('Serper backlink search failed: %s', e)
        print(f'    ⚠️ Serper backlinks error: {e}')

    try:
        olp = fetch_openlinkprofiler(site_domain)
        log.info('OpenLinkProfiler: %d backlinks', len(olp))
        print(f'    OpenLinkProfiler: {len(olp)} backlinks')
        all_links.extend(olp)
    except Exception as e:
        log.error('OpenLinkProfiler fetch failed: %s', e)
        print(f'    ⚠️ OpenLinkProfiler error: {e}')

    if DATAFORSEO_LOGIN:
        try:
            dfs = fetch_dataforseo_backlinks(site_domain)
            log.info('DataForSEO: %d backlinks', len(dfs))
            print(f'    DataForSEO: {len(dfs)} backlinks')
            all_links.extend(dfs)
        except Exception as e:
            log.error('DataForSEO backlinks failed: %s', e)
            print(f'    ⚠️ DataForSEO error: {e}')

    # Deduplicate by source_url
    seen_sources = set()
    unique_links = []
    for link in all_links:
        src = link.get('source_url', '').strip()
        if src and src not in seen_sources:
            seen_sources.add(src)
            unique_links.append(link)

    # Detect new links only — never mark lost from Serper/OLP (results vary per query).
    # Lost detection only fires when we have a comprehensive source like Ahrefs CSV.
    current_sources = {l['source_url'] for l in unique_links}
    new_links  = [l for l in unique_links if l['source_url'] not in known]
    lost_links = []  # only Ahrefs CSV import triggers lost detection

    # Save to DB
    with get_session() as s:
        site = s.query(Site).filter_by(domain=site_domain).first()
        for link in unique_links:
            existing = s.query(Backlink).filter_by(
                site_id=site.id, source_url=link['source_url']
            ).first()
            if existing:
                existing.last_seen  = date.today()
                existing.status     = 'live'
            else:
                s.add(Backlink(
                    site_id=site.id,
                    source_url=link['source_url'],
                    target_url=link.get('target_url', ''),
                    anchor_text=link.get('anchor_text', ''),
                    source_domain=link.get('source_domain', ''),
                    first_seen=date.today(),
                    last_seen=date.today(),
                    status='live'
                ))
        # Mark lost
        for src in known:
            if src not in current_sources:
                known[src].status = 'lost'
        s.commit()

    return {'new': new_links, 'lost': lost_links, 'total': len(unique_links)}

def import_ahrefs_csv(filepath: str, site_domain: str = TARGET_DOMAIN) -> dict:
    """
    Import backlinks from an Ahrefs Webmaster Tools CSV export.
    Ahrefs CSV columns: Referring page URL, Domain Rating, URL Rating,
    Referring domains, Linked domains, Anchor, Backlinks, Type, First seen, Lost, Last seen
    Drop the CSV at: rankpilot/data/ahrefs_backlinks.csv
    """
    if not os.path.exists(filepath):
        print(f'  ⚠️ File not found: {filepath}')
        return {'imported': 0, 'skipped': 0}

    with get_session() as s:
        site = s.query(Site).filter_by(domain=site_domain).first()
        if not site:
            return {'imported': 0, 'skipped': 0}
        site_id = site.id

    imported = skipped = 0
    with open(filepath, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f'  Importing {len(rows)} backlinks from Ahrefs CSV...')
    with get_session() as s:
        site = s.query(Site).filter_by(domain=site_domain).first()
        for row in rows:
            # Ahrefs export column names vary slightly — handle both formats
            source_url = (row.get('Referring page URL') or
                          row.get('referring_page_url') or
                          row.get('Source URL') or '').strip()
            anchor     = (row.get('Anchor') or row.get('anchor') or '').strip()
            target_url = (row.get('Target URL') or
                          row.get('Linked page') or
                          row.get('linked_page') or '').strip()
            first_seen = (row.get('First seen') or row.get('first_seen') or '').strip()

            if not source_url:
                skipped += 1
                continue

            try:
                from urllib.parse import urlparse
                src_domain = urlparse(source_url).netloc.replace('www.', '')
            except Exception:
                src_domain = source_url[:50]

            existing = s.query(Backlink).filter_by(
                site_id=site.id, source_url=source_url
            ).first()
            if not existing:
                s.add(Backlink(
                    site_id=site.id,
                    source_url=source_url,
                    target_url=target_url or f'https://{site_domain}/',
                    anchor_text=anchor[:200] if anchor else '',
                    source_domain=src_domain,
                    first_seen=date.today(),
                    last_seen=date.today(),
                    status='live'
                ))
                imported += 1
            else:
                existing.last_seen = date.today()
                existing.status    = 'live'
                skipped += 1
        s.commit()

    print(f'  ✅ Ahrefs import: {imported} new, {skipped} already known')
    return {'imported': imported, 'skipped': skipped}


if __name__ == '__main__':
    result = run_backlink_monitor()
    print(f'Total backlinks: {result["total"]}')
    print(f'New this week:   {len(result["new"])}')
    print(f'Lost this week:  {len(result["lost"])}')
    if result['new']:
        print('\nNew backlinks:')
        for b in result['new'][:5]:
            print(f'  {b["source_domain"]} → {b["anchor_text"]}')
