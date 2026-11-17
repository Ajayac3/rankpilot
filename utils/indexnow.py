"""
RankPilot — IndexNow URL submission.
Notifies Bing, Yandex, DuckDuckGo, Naver instantly when pages are added/updated.
Google does NOT support IndexNow (uses sitemaps instead).
"""
import os, sys, json, requests
from datetime import date, timedelta
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import TARGET_DOMAIN, INDEXNOW_KEY

API_URL = 'https://api.indexnow.org/indexnow'
LOG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        'data', 'indexnow_submitted.json')


def _load_submitted() -> set:
    try:
        with open(LOG_FILE) as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def _save_submitted(urls: set):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, 'w') as f:
        json.dump(list(urls), f)


def submit_urls(urls: list[str], host: str = TARGET_DOMAIN, force: bool = False) -> bool:
    """
    Submit URLs to IndexNow. Skips already-submitted URLs unless force=True.
    Returns True on success.
    """
    if not INDEXNOW_KEY:
        print('  ⚠️ IndexNow: INDEXNOW_KEY not set in .env — skipping')
        return False
    if not urls:
        return True

    submitted = _load_submitted()
    new_urls = urls if force else [u for u in urls if u not in submitted]
    if not new_urls:
        print('  IndexNow: all URLs already submitted')
        return True

    # Chunk into batches of 10,000
    for i in range(0, len(new_urls), 10000):
        batch = new_urls[i:i + 10000]
        payload = {
            'host': host,
            'key': INDEXNOW_KEY,
            'keyLocation': f'https://{host}/{INDEXNOW_KEY}.txt',
            'urlList': batch,
        }
        try:
            r = requests.post(API_URL, json=payload, timeout=15)
            if r.status_code in (200, 202):
                submitted.update(batch)
                print(f'  ✅ IndexNow: {len(batch)} URLs submitted (HTTP {r.status_code})')
            else:
                print(f'  ⚠️ IndexNow: HTTP {r.status_code} — {r.text[:200]}')
        except Exception as e:
            print(f'  ⚠️ IndexNow: {e}')
            return False

    _save_submitted(submitted)
    return True


def submit_recent_pages(site_domain: str = TARGET_DOMAIN, days: int = 7) -> bool:
    """Submit pages updated/tracked this week from the DB."""
    try:
        from core.db import get_session, GscPage, Site
        with get_session() as s:
            site = s.query(Site).filter_by(domain=site_domain).first()
            if not site:
                return False
            cutoff = date.today() - timedelta(days=days)
            pages = (s.query(GscPage)
                     .filter_by(site_id=site.id)
                     .filter(GscPage.date >= cutoff)
                     .all())
            urls = list({p.page for p in pages if p.page and p.page.startswith('https://')})
        return submit_urls(urls, site_domain)
    except Exception as e:
        print(f'  ⚠️ IndexNow submit_recent_pages: {e}')
        return False


if __name__ == '__main__':
    submit_recent_pages()
