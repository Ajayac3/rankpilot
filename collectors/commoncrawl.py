"""
RankPilot — Backlink Discovery via Serper + CommonCrawl CDX
Primary:  Serper search for "domain.com" mentions on external sites (fast, accurate).
Fallback: CommonCrawl CDX competitor-outlink scan (slow, limited coverage).
"""
import os, sys, gzip, json, requests
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import TARGET_DOMAIN, SERPER_KEY
from utils.logger import get_logger

log = get_logger(__name__)

CC_CDX  = 'https://index.commoncrawl.org'
CC_DATA = 'https://data.commoncrawl.org'
HEADERS = {'User-Agent': 'RankPilotBot/0.1 (research; contact@rankpilot.io)'}


# ── Serper-based backlink discovery ──────────────────────────────────────────

def _serper_backlink_search(domain: str, max_results: int = 100) -> list[dict]:
    """
    Search for external pages that mention our domain.
    Uses: '"domain.com" -site:domain.com' query on Serper.
    Returns list of {source_url, source_domain, anchor_text, target_url}.
    """
    if not SERPER_KEY:
        log.warning('SERPER_KEY not set — cannot run Serper backlink discovery')
        return []

    backlinks = []
    queries = [
        f'site:* "{domain}" legal',
        f'site:* "{domain}" nri',
        f'site:* "{domain}" lawyer',
    ]

    for query in queries:
        try:
            log.debug('Serper backlink query: %s', query)
            r = requests.post(
                'https://google.serper.dev/search',
                headers={'X-API-KEY': SERPER_KEY, 'Content-Type': 'application/json'},
                json={'q': query, 'num': 10, 'gl': 'in'},
                timeout=15
            )
            if r.status_code != 200:
                log.warning('Serper returned HTTP %s for query: %s', r.status_code, query)
                continue

            results = r.json().get('organic', [])
            log.debug('Serper returned %d results for: %s', len(results), query)

            for res in results:
                source_url = res.get('link', '')
                if not source_url:
                    continue
                if domain.lower().replace('www.', '') in source_url.lower():
                    continue  # skip our own domain

                try:
                    from urllib.parse import urlparse
                    source_domain = urlparse(source_url).netloc.replace('www.', '')
                except Exception:
                    source_domain = source_url[:60]

                # Extract anchor/snippet text that mentions our domain
                snippet = res.get('snippet', '')
                anchor  = res.get('title', '')

                backlinks.append({
                    'source_url':    source_url,
                    'source_domain': source_domain,
                    'anchor_text':   anchor[:200],
                    'target_url':    f'https://{domain}/',
                    'snippet':       snippet[:300],
                })

        except requests.exceptions.Timeout:
            log.error('Serper timeout on query: %s', query)
        except requests.exceptions.ConnectionError as e:
            log.error('Serper connection error: %s', e)
        except Exception as e:
            log.exception('Unexpected error in Serper backlink search: %s', e)

    # Deduplicate by source_url
    seen = set()
    unique = []
    for b in backlinks:
        if b['source_url'] not in seen:
            seen.add(b['source_url'])
            unique.append(b)

    log.info('Serper backlink discovery: %d unique external mentions found', len(unique))
    return unique[:max_results]


# ── CommonCrawl CDX fallback ──────────────────────────────────────────────────

def get_latest_crawl() -> str:
    """Get the ID of the most recent CommonCrawl crawl."""
    try:
        r = requests.get(f'{CC_CDX}/collinfo.json', timeout=10)
        r.raise_for_status()
        crawl_id = r.json()[0]['id']
        log.debug('Latest CommonCrawl crawl: %s', crawl_id)
        return crawl_id
    except requests.exceptions.Timeout:
        log.error('Timeout fetching CommonCrawl collinfo')
        return 'CC-MAIN-2026-21'
    except Exception as e:
        log.error('Failed to get latest crawl ID: %s', e)
        return 'CC-MAIN-2026-21'


def cdx_query(domain: str, crawl_id: str = None, limit: int = 500) -> list[dict]:
    """Query CDX index for pages from a domain."""
    crawl_id = crawl_id or get_latest_crawl()
    url      = f'{CC_CDX}/{crawl_id}-index'
    params   = {'url': f'{domain}/*', 'output': 'json', 'limit': limit,
                'filter': 'status:200', 'fl': 'url,filename,offset,length'}
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=20)
        if r.status_code != 200:
            log.warning('CDX query returned HTTP %s for domain %s', r.status_code, domain)
            return []
        results = []
        for line in r.text.strip().split('\n'):
            if line.strip():
                try:
                    results.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        log.debug('CDX query for %s: %d records', domain, len(results))
        return results
    except requests.exceptions.Timeout:
        log.error('CDX query timeout for domain: %s', domain)
        return []
    except Exception as e:
        log.error('CDX query error for %s: %s', domain, e)
        return []


def fetch_wat_record(filename: str, offset: int, length: int) -> str | None:
    """Fetch a single WAT record via HTTP Range request."""
    url     = f'{CC_DATA}/{filename}'
    headers = {**HEADERS, 'Range': f'bytes={offset}-{int(offset)+int(length)-1}'}
    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code not in (200, 206):
            log.debug('WAT fetch returned HTTP %s for %s', r.status_code, filename)
            return None
        try:
            return gzip.decompress(r.content).decode('utf-8', errors='ignore')
        except Exception:
            return r.content.decode('utf-8', errors='ignore')
    except requests.exceptions.Timeout:
        log.warning('WAT fetch timeout: %s offset=%s', filename, offset)
        return None
    except Exception as e:
        log.error('WAT fetch error: %s — %s', filename, e)
        return None


def extract_outlinks_from_wat(wat_content: str) -> list[dict]:
    """Extract all outlinks from a WAT record."""
    links = []
    try:
        for line in wat_content.split('\n'):
            line = line.strip()
            if not line or not line.startswith('{'):
                continue
            try:
                record = json.loads(line)
                html_meta = (record.get('Envelope', {})
                             .get('Payload-Metadata', {})
                             .get('HTTP-Response-Metadata', {})
                             .get('HTML-Metadata', {}))
                if 'Links' not in html_meta:
                    continue
                source_url = (record.get('Envelope', {})
                              .get('WARC-Header-Metadata', {})
                              .get('WARC-Target-URI', ''))
                for link in html_meta['Links']:
                    href   = link.get('url', '')
                    anchor = link.get('text', '')
                    if href.startswith('http'):
                        links.append({'source_url': source_url,
                                      'target_url': href,
                                      'anchor_text': anchor})
            except (json.JSONDecodeError, KeyError):
                continue
    except Exception as e:
        log.error('WAT outlink extraction error: %s', e)
    return links


def _cc_competitor_fallback(our_domain: str, crawl_id: str = None) -> list[dict]:
    """
    Fallback: scan competitor pages in CommonCrawl for outlinks to our domain.
    Less accurate than Serper — only finds backlinks from competitors we track.
    """
    from core.db import get_session, Site, Competitor

    with get_session() as s:
        site = s.query(Site).filter_by(domain=our_domain).first()
        if not site:
            log.warning('Site %s not found in DB for CC fallback', our_domain)
            return []
        competitors = s.query(Competitor).filter_by(site_id=site.id).all()

    if not competitors:
        log.info('No competitors in DB — skipping CommonCrawl fallback')
        return []

    crawl_id  = crawl_id or get_latest_crawl()
    backlinks = []

    for comp in competitors:
        log.info('CommonCrawl: scanning %s outlinks for links to %s', comp.domain, our_domain)
        cdx_records = cdx_query(comp.domain, crawl_id, limit=50)
        log.info('  %s: %d pages in CommonCrawl', comp.domain, len(cdx_records))

        found_for_comp = 0
        for i, record in enumerate(cdx_records):
            filename = record.get('filename', '')
            offset   = record.get('offset', 0)
            length   = record.get('length', 0)
            if not filename:
                continue

            wat_content = fetch_wat_record(filename, offset, length)
            if wat_content:
                links = extract_outlinks_from_wat(wat_content)
                our_links = [l for l in links
                             if our_domain.lower().replace('www.', '')
                             in l.get('target_url', '').lower()]
                backlinks.extend(our_links)
                found_for_comp += len(our_links)

            if (i + 1) % 10 == 0:
                log.info('  Processed %d/%d pages...', i + 1, len(cdx_records))

        log.info('  %s: found %d links to %s', comp.domain, found_for_comp, our_domain)

    return backlinks


# ── Main entry point ──────────────────────────────────────────────────────────

def run_cc_backlink_discovery(our_domain: str) -> dict:
    """
    Discover backlinks to our_domain.
    Primary:  Serper web search for domain mentions (fast, ~30 results).
    Fallback: CommonCrawl competitor scan (slow, only if Serper unavailable).
    Saves new findings to the backlinks DB table.
    """
    from core.db import get_session, Backlink, Site

    log.info('Starting backlink discovery for %s', our_domain)

    # Primary: Serper
    backlinks = _serper_backlink_search(our_domain)

    # Fallback: CommonCrawl if Serper returned nothing
    if not backlinks:
        log.info('Serper returned 0 results — falling back to CommonCrawl competitor scan')
        backlinks = _cc_competitor_fallback(our_domain)

    log.info('Total backlinks found: %d', len(backlinks))

    saved = 0
    with get_session() as s:
        site = s.query(Site).filter_by(domain=our_domain).first()
        if not site:
            log.error('Site %s not in DB — cannot save backlinks', our_domain)
            return {'found': len(backlinks), 'saved': 0}

        for link in backlinks:
            try:
                existing = s.query(Backlink).filter_by(
                    site_id=site.id, source_url=link['source_url']
                ).first()
                if not existing:
                    s.add(Backlink(
                        site_id=site.id,
                        source_url=link['source_url'][:500],
                        target_url=link.get('target_url', f'https://{our_domain}/')[:500],
                        anchor_text=link.get('anchor_text', '')[:200],
                        source_domain=link.get('source_domain',
                                               link['source_url'].split('/')[2]
                                               .replace('www.', '') if '/' in link['source_url'] else '')[:100],
                        first_seen=date.today(),
                        last_seen=date.today(),
                        status='live'
                    ))
                    saved += 1
                else:
                    existing.last_seen = date.today()
                    existing.status    = 'live'
            except Exception as e:
                log.error('Failed to save backlink %s: %s', link.get('source_url'), e)

        try:
            s.commit()
            log.info('Saved %d new backlinks to DB', saved)
        except Exception as e:
            log.error('DB commit failed for backlinks: %s', e)
            s.rollback()

    print(f'\n  ✅ Found {len(backlinks)} total links pointing to {our_domain}')
    print(f'  ✅ CommonCrawl: {len(backlinks)} links found, {saved} new saved')
    return {'found': len(backlinks), 'saved': saved}


if __name__ == '__main__':
    domain = sys.argv[1] if len(sys.argv) > 1 else TARGET_DOMAIN
    result = run_cc_backlink_discovery(domain)
    print(f'Result: {result}')
