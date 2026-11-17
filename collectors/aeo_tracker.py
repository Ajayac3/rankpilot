"""
RankPilot — AEO (Answer Engine Optimization) Tracker
Tracks brand/domain citations in AI search engines.

Automated (via Playwright):
  - Google AI Overviews (via ai_overview.py)
  - Bing Copilot AI answers (Bing is more lenient than Google)

Manual entry (via Dashboard):
  - ChatGPT (requires login — enter manually)
  - Gemini (requires login — enter manually)
  - Perplexity (Cloudflare + ToS risk — enter manually)

Skip automated scraping of ChatGPT/Gemini/Perplexity — all require login
or have aggressive anti-bot measures. Perplexity has active legal disputes
over scraping. Manual tracking is more reliable for those.
"""
import os, sys, asyncio, time
from datetime import date
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import TARGET_DOMAIN

# Key NRI legal queries to track in AEO engines
AEO_QUERIES = [
    'nri property dispute lawyer india',
    '498a false case nri husband',
    'anticipatory bail nri',
    'power of attorney nri',
    'fir quashing nri',
]


async def _check_bing_copilot_async(keyword: str, domain: str) -> dict:
    """
    Check if domain is cited in Bing's AI-generated answer section.
    Bing AI answers appear above organic results for many queries.
    """
    from playwright.async_api import async_playwright

    url = f'https://www.bing.com/search?q={keyword}&setlang=en'
    result = {
        'keyword': keyword,
        'engine':  'bing_copilot',
        'ai_overview_present': False,
        'ai_cited': False,
        'snippet':  '',
        'date':     date.today(),
    }

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True,
                                          args=['--no-sandbox', '--disable-dev-shm-usage'])
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            locale='en-US',
        )
        page = await context.new_page()
        try:
            await page.goto(url, wait_until='domcontentloaded', timeout=15000)
            await page.wait_for_timeout(2000)

            # Bing AI answer selectors (Copilot integration in main search)
            ai_selectors = [
                '#b_sydConvCont',       # Bing Copilot conversation
                '.b_ai_answer',         # AI-generated answer block
                '[data-tag="AIAnswer"]', # AI answer tag
                '#ai_summary',          # AI summary block
            ]
            for sel in ai_selectors:
                count = await page.locator(sel).count()
                if count > 0:
                    result['ai_overview_present'] = True
                    try:
                        result['snippet'] = (await page.locator(sel).first.inner_text())[:500]
                    except Exception:
                        pass
                    break

            if result['ai_overview_present']:
                # Check for domain citation in AI answer links
                try:
                    links = await page.locator('#b_sydConvCont a, .b_ai_answer a').all()
                    clean = domain.lower().replace('www.', '')
                    for link in links[:15]:
                        href = (await link.get_attribute('href') or '').lower()
                        if clean in href:
                            result['ai_cited'] = True
                            break
                except Exception:
                    pass

        except Exception as e:
            result['error'] = str(e)
        finally:
            await browser.close()

    return result


def run_aeo_tracker(site_domain: str = TARGET_DOMAIN,
                    queries: list[str] = None) -> list[dict]:
    """
    Run AEO tracking for Google AI Overviews + Bing Copilot.
    Google AIO: via ai_overview.py (already called in run.py analyse)
    Bing: checked here.
    """
    from core.db import get_session, Site, AeoResult

    check_queries = (queries or AEO_QUERIES)
    results = []

    with get_session() as s:
        site = s.query(Site).filter_by(domain=site_domain).first()
        if not site:
            return []
        site_id = site.id

    print(f'  Bing Copilot AEO check for {len(check_queries)} queries...')

    for i, kw in enumerate(check_queries):
        r = asyncio.run(_check_bing_copilot_async(kw, site_domain))
        results.append(r)

        with get_session() as s:
            existing = (s.query(AeoResult)
                        .filter_by(site_id=site_id, date=date.today(),
                                   query=kw, engine='bing_copilot')
                        .first())
            if existing:
                existing.is_cited    = r['ai_cited']
                existing.raw_snippet = r.get('snippet', '')[:500]
            else:
                s.add(AeoResult(
                    site_id=site_id, date=date.today(), query=kw,
                    engine='bing_copilot',
                    is_cited=r['ai_cited'],
                    raw_snippet=r.get('snippet', '')[:500],
                ))
            s.commit()

        status = '✅ CITED' if r['ai_cited'] else ('📌 AI present' if r['ai_overview_present'] else '❌ No AI answer')
        print(f'    [{i+1}/{len(check_queries)}] {kw}: {status}')

        if i < len(check_queries) - 1:
            time.sleep(5)

    cited = sum(1 for r in results if r['ai_cited'])
    print(f'  Bing AEO: cited in {cited}/{len(results)} queries')
    return results


def log_manual_aeo(site_domain: str, query: str, engine: str,
                   is_cited: bool, citation_url: str = '') -> bool:
    """
    Log a manual AEO check result (for ChatGPT, Gemini, Perplexity).
    Called from the dashboard when user manually checks and enters result.
    """
    from core.db import get_session, Site, AeoResult
    try:
        with get_session() as s:
            site = s.query(Site).filter_by(domain=site_domain).first()
            if not site:
                return False
            existing = (s.query(AeoResult)
                        .filter_by(site_id=site.id, date=date.today(),
                                   query=query, engine=engine)
                        .first())
            if existing:
                existing.is_cited     = is_cited
                existing.citation_url = citation_url
            else:
                s.add(AeoResult(
                    site_id=site.id, date=date.today(), query=query,
                    engine=engine, is_cited=is_cited, citation_url=citation_url,
                ))
            s.commit()
        return True
    except Exception as e:
        print(f'  ⚠️ log_manual_aeo: {e}')
        return False


if __name__ == '__main__':
    run_aeo_tracker()
