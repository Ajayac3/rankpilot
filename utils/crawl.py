"""
RankPilot — Shared web crawler utility.
Primary: requests + BeautifulSoup (fast, works for PHP/static sites).
JS mode: Playwright headless Chrome (for JavaScript-rendered sites).
Crawl4AI was planned but lxml 5.x has no wheel for Python 3.14 — using Playwright instead.
"""
import asyncio, hashlib, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; RankPilotBot/0.1)'}


def crawl_url(url: str, timeout: int = 20, js: bool = False) -> dict:
    """
    Fetch a URL. Returns {'html': str, 'markdown': str, 'success': bool}.
    js=True: use Playwright (slower, handles JS-rendered pages).
    js=False (default): use requests+BS4 (fast, works for most legal sites).
    """
    if js:
        return _crawl_playwright(url, timeout)
    return _crawl_requests(url, timeout)


def _crawl_requests(url: str, timeout: int) -> dict:
    try:
        import requests
        from bs4 import BeautifulSoup
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        soup = BeautifulSoup(r.text, 'html.parser')
        markdown = soup.get_text(separator='\n', strip=True)
        return {'html': r.text, 'markdown': markdown, 'success': r.status_code == 200}
    except Exception as e:
        return {'html': '', 'markdown': '', 'success': False, 'error': str(e)}


def _crawl_playwright(url: str, timeout: int) -> dict:
    async def _fetch():
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True,
                                              args=['--no-sandbox', '--disable-dev-shm-usage'])
            context = await browser.new_context(user_agent=HEADERS['User-Agent'])
            page    = await context.new_page()
            try:
                await page.goto(url, wait_until='domcontentloaded', timeout=timeout * 1000)
                await page.wait_for_timeout(1500)
                html = await page.content()
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html, 'html.parser')
                markdown = soup.get_text(separator='\n', strip=True)
                return {'html': html, 'markdown': markdown, 'success': True}
            except Exception as e:
                return {'html': '', 'markdown': '', 'success': False, 'error': str(e)}
            finally:
                await browser.close()
    try:
        return asyncio.run(_fetch())
    except Exception as e:
        return {'html': '', 'markdown': '', 'success': False, 'error': str(e)}


def get_page_text(url: str, js: bool = False) -> str:
    """Get clean readable text, stripping nav/header/footer."""
    result = crawl_url(url, js=js)
    if not result['success']:
        return ''
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(result['html'], 'html.parser')
        for tag in soup.find_all(['nav', 'header', 'footer', 'script', 'style', 'aside']):
            tag.decompose()
        main = (soup.find('main') or soup.find('article') or
                soup.find(id='main-content') or soup.find('body'))
        return main.get_text(separator=' ', strip=True)[:10000] if main else ''
    except Exception:
        return result['markdown'][:10000]


def get_page_title_and_hash(url: str, js: bool = False) -> tuple[str, str]:
    """Return (title, content_hash) in one request."""
    result = crawl_url(url, js=js)
    title = ''
    chash = ''
    if result['success'] and result['html']:
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(result['html'], 'html.parser')
            t = soup.find('title')
            title = t.text.strip() if t else ''
            main = soup.find('main') or soup.find('article') or soup.find('body')
            text = main.get_text()[:5000] if main else result['html'][:5000]
            chash = hashlib.md5(text.encode()).hexdigest()
        except Exception:
            chash = hashlib.md5(result['markdown'][:5000].encode()).hexdigest()
    return title, chash
