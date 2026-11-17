"""
RankPilot — Google AI Overview Detector (Free, DIY)
Uses Playwright to detect AI Overview presence + check if our domain is cited.
Rate: max 10 queries/day per IP, 10-15s delay. Reuses playwright_serp.py browser infra.
"""
import os, sys, asyncio, time
from datetime import date
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import TARGET_DOMAIN

# Top NRI legal keywords to check for AI Overview presence
AIO_KEYWORDS = [
    'nri property dispute lawyer',
    '498a nri husband',
    'anticipatory bail for nri india',
    'power of attorney for nri india',
    'fir quashing for nri',
    'nri divorce lawyer india',
    'oci card renewal process',
    'nri property encroachment india',
    'nri proclaimed offender india',
    'nri legal services delhi',
]


async def _check_ai_overview_async(keyword: str, domain: str,
                                   country: str = 'IN') -> dict:
    """
    Check a single keyword for AI Overview presence and domain citation.
    Returns {'keyword', 'ai_overview_present', 'ai_cited', 'snippet', 'sources'}
    """
    from playwright.async_api import async_playwright

    gl  = {'IN': 'in', 'US': 'us', 'GB': 'gb', 'CA': 'ca', 'AE': 'ae'}.get(country, 'in')
    url = f'https://www.google.com/search?q={keyword}&gl={gl}&hl=en&pws=0'

    result = {
        'keyword':           keyword,
        'ai_overview_present': False,
        'ai_cited':          False,
        'snippet':           '',
        'sources':           [],
        'date':              date.today(),
    }

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-blink-features=AutomationControlled',
                  '--disable-dev-shm-usage']
        )
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            viewport={'width': 1280, 'height': 900},
            locale='en-US',
        )
        page = await context.new_page()
        try:
            await page.goto(url, wait_until='domcontentloaded', timeout=15000)
            # AI Overviews load async — wait up to 5s
            try:
                await page.wait_for_selector(
                    'div[jsname][data-rl]',
                    timeout=5000
                )
                result['ai_overview_present'] = True
            except Exception:
                # Try alternate selector
                count = await page.locator('[data-async-type="aiovervieww"], [jsname="rGLJd"]').count()
                result['ai_overview_present'] = count > 0

            if result['ai_overview_present']:
                # Extract snippet text
                try:
                    aio_div = page.locator('div[jsname][data-rl]').first
                    snippet = await aio_div.inner_text()
                    result['snippet'] = snippet[:500]
                except Exception:
                    pass

                # Extract source citations (links in AIO block)
                try:
                    links = await page.locator('div[jsname][data-rl] a[href]').all()
                    sources = []
                    for link in links[:10]:
                        href = await link.get_attribute('href') or ''
                        if href.startswith('http'):
                            sources.append(href)
                    result['sources'] = sources
                    clean_domain = domain.lower().replace('www.', '')
                    result['ai_cited'] = any(clean_domain in s.lower() for s in sources)
                except Exception:
                    pass

        except Exception as e:
            result['error'] = str(e)
        finally:
            await browser.close()

    return result


def check_ai_overview(keyword: str, domain: str = TARGET_DOMAIN,
                      country: str = 'IN') -> dict:
    """Synchronous wrapper."""
    return asyncio.run(_check_ai_overview_async(keyword, domain, country))


def run_ai_overview_check(site_domain: str = TARGET_DOMAIN,
                          keywords: list[str] = None,
                          max_queries: int = 8) -> list[dict]:
    """
    Check AI Overview presence for top NRI keywords.
    Saves results to DB. Rate-limits to max_queries per run.
    """
    from core.db import get_session, Site, Keyword, Ranking, AeoResult

    kws = (keywords or AIO_KEYWORDS)[:max_queries]
    results = []

    print(f'  Checking AI Overview for {len(kws)} keywords (10-15s delay each)...')

    with get_session() as s:
        site = s.query(Site).filter_by(domain=site_domain).first()
        if not site:
            print('  ⚠️ Site not found in DB — run: python run.py setup')
            return []
        site_id = site.id

    for i, kw in enumerate(kws):
        print(f'    [{i+1}/{len(kws)}] {kw}')
        r = check_ai_overview(kw, site_domain)
        results.append(r)

        # Save to AeoResult table
        with get_session() as s:
            existing = (s.query(AeoResult)
                        .filter_by(site_id=site_id, date=date.today(),
                                   query=kw, engine='google_aio')
                        .first())
            if existing:
                existing.is_cited    = r['ai_cited']
                existing.raw_snippet = r['snippet'][:500] if r.get('snippet') else None
            else:
                s.add(AeoResult(
                    site_id=site_id, date=date.today(), query=kw,
                    engine='google_aio',
                    is_cited=r['ai_cited'],
                    raw_snippet=r['snippet'][:500] if r.get('snippet') else None,
                ))
            s.commit()

        status = '✅ CITED' if r['ai_cited'] else ('📌 AIO present' if r['ai_overview_present'] else '❌ No AIO')
        print(f'       {status}')

        # Polite delay — 12 seconds between queries
        if i < len(kws) - 1:
            time.sleep(12)

    cited = sum(1 for r in results if r['ai_cited'])
    present = sum(1 for r in results if r['ai_overview_present'])
    print(f'\n  AI Overview summary: {present}/{len(results)} queries had AIO, cited in {cited}')
    return results


if __name__ == '__main__':
    results = run_ai_overview_check()
    for r in results:
        print(f'  {r["keyword"]}: AIO={r["ai_overview_present"]} cited={r["ai_cited"]}')
