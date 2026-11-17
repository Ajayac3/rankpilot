"""
RankPilot — SERP Top-10 Deep Analyser
For any keyword: fetches top 10 URLs, measures word count, schema, backlinks, content age.
Answers: "What does it take to outrank position 1?"
"""
import os, sys, re, requests, time
from datetime import date
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import TARGET_DOMAIN, VALUESERP_KEY
from core.db import get_session, Site, SerpAnalysisResult, Keyword, Ranking
from utils.logger import get_logger
log = get_logger(__name__)

HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; RankPilotBot/0.1)'}

# NRI legal commercial keywords to analyse SERP for
PRIORITY_KEYWORDS = [
    'nri property dispute lawyer',
    '498a nri husband',
    'nri divorce lawyer india',
    'nri criminal lawyer india',
    'nri legal services delhi',
    'power of attorney for nri india',
    'nri lawyer delhi',
    'anticipatory bail for nri',
    'fir quashing for nri',
    'oci card renewal india',
]


def get_top10_urls(keyword: str, country: str = 'in') -> list[dict]:
    """Get top 10 SERP results with position, URL, title. Serper → ValueSERP fallback."""
    from core.config import SERPER_KEY
    if SERPER_KEY:
        try:
            r = requests.post(
                'https://google.serper.dev/search',
                headers={'X-API-KEY': SERPER_KEY, 'Content-Type': 'application/json'},
                json={'q': keyword, 'gl': country, 'num': 10},
                timeout=15
            )
            if r.status_code == 200:
                return [
                    {'position': i + 1,
                     'url': res.get('link', ''),
                     'title': res.get('title', ''),
                     'domain': res.get('link', '').split('/')[2].replace('www.', '')}
                    for i, res in enumerate(r.json().get('organic', [])[:10])
                    if res.get('link')
                ]
        except Exception as e:
            print(f'  ⚠️ Serper fetch {keyword}: {e}')

    if VALUESERP_KEY:
        try:
            r = requests.get('https://api.valueserp.com/search',
                             params={'api_key': VALUESERP_KEY, 'q': keyword,
                                     'gl': country, 'hl': 'en', 'num': '10'}, timeout=20)
            if r.status_code == 200:
                return [
                    {'position': i + 1,
                     'url': res.get('link', ''),
                     'title': res.get('title', ''),
                     'domain': res.get('displayed_link', '').split('/')[0]}
                    for i, res in enumerate(r.json().get('organic_results', [])[:10])
                    if res.get('link')
                ]
        except Exception as e:
            print(f'  ⚠️ ValueSERP fetch {keyword}: {e}')
    return []


def _word_count(html: str) -> int:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')
    for tag in soup.find_all(['script', 'style', 'nav', 'header', 'footer']):
        tag.decompose()
    return len(re.findall(r'\b\w+\b', soup.get_text()))


def _has_schema(html: str) -> tuple[bool, bool]:
    """Returns (has_any_schema, has_faq_schema)."""
    has_any = 'application/ld+json' in html
    has_faq = '"FAQPage"' in html
    return has_any, has_faq


def _publish_date(html: str) -> str:
    """Try to extract publication date from page HTML."""
    patterns = [
        r'"datePublished"\s*:\s*"([^"]+)"',
        r'<meta[^>]+property="article:published_time"[^>]+content="([^"]+)"',
        r'<time[^>]+datetime="([^"]+)"',
    ]
    for p in patterns:
        m = re.search(p, html, re.I)
        if m:
            return m.group(1)[:10]
    return ''


def _backlink_count(domain: str) -> int:
    """Estimate backlink count via OpenLinkProfiler (free)."""
    try:
        r = requests.get(
            'https://www.openlinkprofiler.org/api/getBacklinks',
            params={'url': domain, 'limit': 1, 'target': 'domain'},
            headers=HEADERS, timeout=15
        )
        if r.status_code == 200:
            data = r.json()
            return data.get('total_backlinks', 0)
    except Exception:
        pass
    return 0


def analyse_serp(keyword: str, site_domain: str = TARGET_DOMAIN,
                 country: str = 'in') -> list[dict]:
    """Analyse top 10 SERP results for a keyword."""
    print(f'  Analysing SERP: {keyword}')
    results = get_top10_urls(keyword, country)
    if not results:
        print('  ⚠️ No SERP data (check VALUESERP_KEY)')
        return []

    analysed = []
    our_clean = site_domain.lower().replace('www.', '')

    for res in results:
        url       = res['url']
        pos       = res['position']
        is_ours   = our_clean in url.lower()

        html = ''
        try:
            r    = requests.get(url, headers=HEADERS, timeout=12)
            html = r.text
        except Exception:
            pass

        wc         = _word_count(html) if html else 0
        has_sc, faq = _has_schema(html) if html else (False, False)
        pub_date   = _publish_date(html) if html else ''

        # Only check backlinks for top 3 (OLP rate limits)
        bl_count = 0
        if pos <= 3 and not is_ours:
            bl_count = _backlink_count(res.get('domain', ''))
            time.sleep(1)

        item = {
            'position':       pos,
            'url':            url,
            'domain':         res.get('domain', ''),
            'title':          res.get('title', ''),
            'word_count':     wc,
            'backlink_count': bl_count,
            'has_schema':     has_sc,
            'has_faq':        faq,
            'publish_date':   pub_date,
            'is_our_domain':  is_ours,
        }
        analysed.append(item)

        status = '⭐ OUR PAGE' if is_ours else f'pos {pos}'
        print(f'    {status}: {wc} words, schema={has_sc}, faq={faq}, links={bl_count}')
        time.sleep(0.5)

    return analysed


def save_serp_analysis(keyword: str, results: list[dict], site_id: int):
    """Save SERP analysis to DB."""
    with get_session() as s:
        for r in results:
            existing = s.query(SerpAnalysisResult).filter_by(
                site_id=site_id, keyword=keyword,
                analysed_at=date.today(), position=r['position']
            ).first()
            data = dict(
                site_id=site_id, keyword=keyword,
                analysed_at=date.today(),
                position=r['position'],
                url=r['url'][:500],
                domain=r['domain'][:100],
                title=r['title'][:255],
                word_count=r['word_count'],
                backlink_count=r['backlink_count'],
                has_schema=r['has_schema'],
                has_faq=r['has_faq'],
                publish_date=r['publish_date'][:20],
                is_our_domain=r['is_our_domain'],
            )
            if existing:
                for k, v in data.items():
                    setattr(existing, k, v)
            else:
                s.add(SerpAnalysisResult(**data))
        s.commit()


def run_serp_analyser(site_domain: str = TARGET_DOMAIN,
                      keywords: list[str] = None,
                      max_keywords: int = 5) -> dict:
    """Run SERP analysis for top priority keywords."""
    with get_session() as s:
        site = s.query(Site).filter_by(domain=site_domain).first()
        if not site:
            return {}
        site_id = site.id

    kws = (keywords or PRIORITY_KEYWORDS)[:max_keywords]
    all_results = {}

    for kw in kws:
        results = analyse_serp(kw, site_domain)
        if results:
            save_serp_analysis(kw, results, site_id)
            all_results[kw] = results
        time.sleep(2)

    # Print "what you need to rank" summary
    print('\n  📊 What it takes to rank:')
    for kw, res in all_results.items():
        top3 = [r for r in res if r['position'] <= 3]
        if top3:
            avg_wc = int(sum(r['word_count'] for r in top3) / len(top3))
            schemas = sum(1 for r in top3 if r['has_schema'])
            faqs    = sum(1 for r in top3 if r['has_faq'])
            print(f'    {kw[:40]}: {avg_wc}+ words, {schemas}/3 have schema, {faqs}/3 have FAQ')

    return all_results


if __name__ == '__main__':
    run_serp_analyser(max_keywords=3)
