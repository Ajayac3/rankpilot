"""
RankPilot — Playwright SERP Checker
Free, unlimited rank checking using headless Chrome.
No API cost. Works for ANY niche, ANY keyword.
Uses proxy rotation (BrightData) at scale; direct connection for local use.
"""
import os, sys, asyncio, re, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import env

PROXY_SERVER   = env('BRIGHTDATA_PROXY', '')   # host:port format
PROXY_USER     = env('BRIGHTDATA_USER', '')
PROXY_PASS     = env('BRIGHTDATA_PASS', '')

COUNTRY_GL = {
    'IN': 'in', 'US': 'us', 'GB': 'gb', 'CA': 'ca',
    'AE': 'ae', 'AU': 'au', 'SG': 'sg', 'NZ': 'nz'
}

async def _check_rank_async(keyword: str, domain: str, country: str = 'IN',
                             max_results: int = 100) -> dict:
    """Async rank check using Playwright headless Chrome."""
    from playwright.async_api import async_playwright

    gl = COUNTRY_GL.get(country.upper(), 'us')
    url = f'https://www.google.com/search?q={keyword}&gl={gl}&hl=en&num=100&pws=0'

    proxy = None
    if PROXY_SERVER and PROXY_USER:
        proxy = {'server': f'http://{PROXY_SERVER}',
                 'username': PROXY_USER, 'password': PROXY_PASS}

    result = {'position': None, 'url': None, 'serp_features': {}, 'method': 'playwright'}

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            proxy=proxy,
            args=['--no-sandbox', '--disable-blink-features=AutomationControlled']
        )
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15',
            viewport={'width': 390, 'height': 844},
            locale='en-US'
        )
        page = await context.new_page()

        try:
            await page.goto(url, wait_until='domcontentloaded', timeout=15000)
            await page.wait_for_timeout(1500)   # human-like delay

            # Check for CAPTCHA
            if 'captcha' in await page.title().lower() or await page.locator('#captcha-form').count() > 0:
                result['error'] = 'captcha'
                return result

            # Extract organic results
            results = await page.query_selector_all('div.g, div[data-sokoban-container]')

            serp_features = {
                'featured_snippet': await page.locator('[data-async-type="editableDirectAnswer"]').count() > 0,
                'paa':              await page.locator('[jsname="yEVEwb"]').count() > 0,
                'local_pack':       await page.locator('[data-attrid="kc:/location/location:business_feature"]').count() > 0,
                'video_pack':       await page.locator('[data-init-vis="true"] video').count() > 0,
            }
            result['serp_features'] = serp_features

            position = 1
            for res in results:
                link = await res.query_selector('a[href^="http"]')
                if link:
                    href = await link.get_attribute('href') or ''
                    if domain.lower().replace('www.', '') in href.lower():
                        result['position'] = position
                        result['url'] = href
                        break
                    position += 1
                    if position > max_results:
                        break

        except Exception as e:
            result['error'] = str(e)
        finally:
            await browser.close()

    return result

def check_rank(keyword: str, domain: str, country: str = 'IN') -> dict:
    """Synchronous wrapper for rank check."""
    return asyncio.run(_check_rank_async(keyword, domain, country))

async def batch_check_async(checks: list[dict], concurrency: int = 3) -> list[dict]:
    """
    Check multiple keywords concurrently.
    checks = [{'keyword': ..., 'domain': ..., 'country': ...}, ...]
    concurrency: max simultaneous browser instances (3 to avoid detection)
    """
    sem = asyncio.Semaphore(concurrency)
    results = []

    async def check_one(item):
        async with sem:
            r = await _check_rank_async(item['keyword'], item['domain'], item.get('country', 'IN'))
            r['keyword'] = item['keyword']
            r['country'] = item.get('country', 'IN')
            await asyncio.sleep(1.5)   # polite delay between checks
            return r

    tasks = [check_one(c) for c in checks]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return [r for r in results if isinstance(r, dict)]

def batch_check(checks: list[dict], concurrency: int = 3) -> list[dict]:
    """Synchronous batch rank check."""
    return asyncio.run(batch_check_async(checks, concurrency))

if __name__ == '__main__':
    # Test: check position for a keyword
    import sys
    keyword = sys.argv[1] if len(sys.argv) > 1 else 'nri property lawyer'
    domain  = sys.argv[2] if len(sys.argv) > 2 else 'example-legal.in'
    country = sys.argv[3] if len(sys.argv) > 3 else 'IN'

    print(f'Checking: "{keyword}" for {domain} in {country}...')
    result = check_rank(keyword, domain, country)
    print(f'Position: {result.get("position") or "Not in top 100"}')
    print(f'URL: {result.get("url", "")}')
    print(f'SERP features: {result.get("serp_features", {})}')
    if result.get('error'):
        print(f'Error: {result["error"]}')
