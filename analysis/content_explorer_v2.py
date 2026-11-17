"""
RankPilot — Content Explorer v2
Find the best-performing content on any topic: word count, backlinks, estimated traffic.
Tells you what to create and how long it should be to outrank competitors.
"""
import os, sys, re, requests, time
from datetime import date
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import TARGET_DOMAIN, VALUESERP_KEY

HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; RankPilotBot/0.1)'}

CTR_CURVE = {1: 0.285, 2: 0.157, 3: 0.110, 4: 0.080, 5: 0.072,
             6: 0.052, 7: 0.042, 8: 0.035, 9: 0.030, 10: 0.025}


def search_topic(topic: str, country: str = 'in', num: int = 20) -> list[dict]:
    """Get top SERP results for a topic."""
    if not VALUESERP_KEY:
        return []
    params = {'api_key': VALUESERP_KEY, 'q': topic,
              'gl': country, 'hl': 'en', 'num': str(num), 'output': 'json'}
    try:
        r = requests.get('https://api.valueserp.com/search', params=params, timeout=20)
        if r.status_code == 200:
            return [{'position': i + 1, 'url': res.get('link', ''),
                     'title': res.get('title', ''),
                     'snippet': res.get('snippet', ''),
                     'domain': res.get('displayed_link', '').split('/')[0]}
                    for i, res in enumerate(r.json().get('organic_results', []))
                    if res.get('link')]
    except Exception as e:
        print(f'  ⚠️ Content explorer search: {e}')
    return []


def analyse_content_page(url: str) -> dict:
    """Fetch a page and measure key content metrics."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=12)
        html = r.text
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')
        for tag in soup.find_all(['script', 'style', 'nav', 'header', 'footer']):
            tag.decompose()
        text = soup.get_text(separator=' ')
        word_count = len(re.findall(r'\b\w+\b', text))

        title_tag = soup.find('title')
        h1_tag    = soup.find('h1')
        has_schema = 'application/ld+json' in html
        has_faq    = '"FAQPage"' in html
        has_video  = bool(soup.find(['video', 'iframe']))

        # Images with alt text
        imgs = soup.find_all('img')
        imgs_with_alt = sum(1 for img in imgs if img.get('alt'))

        return {
            'word_count':   word_count,
            'title':        (title_tag.get_text(strip=True) if title_tag else '')[:150],
            'h1':           (h1_tag.get_text(strip=True) if h1_tag else '')[:150],
            'has_schema':   has_schema,
            'has_faq':      has_faq,
            'has_video':    has_video,
            'image_count':  len(imgs),
            'imgs_with_alt': imgs_with_alt,
        }
    except Exception as e:
        return {'error': str(e), 'word_count': 0}


def _get_backlinks(domain: str) -> int:
    """Quick backlink count from OpenLinkProfiler."""
    try:
        r = requests.get(
            'https://www.openlinkprofiler.org/api/getBacklinks',
            params={'url': domain, 'limit': 1, 'target': 'domain'},
            headers=HEADERS, timeout=12
        )
        if r.status_code == 200:
            return r.json().get('total_backlinks', 0)
    except Exception:
        pass
    return 0


def explore_topic(topic: str, country: str = 'in',
                  analyse_pages: int = 10) -> list[dict]:
    """
    Full content exploration for a topic.
    Returns list of content items with metrics, sorted by estimated value.
    """
    print(f'  Content Explorer: {topic}')
    results = search_topic(topic, country)
    if not results:
        return []

    explored = []
    for res in results[:analyse_pages]:
        url = res['url']
        print(f'    Analysing pos {res["position"]}: {url[:60]}')

        page_data = analyse_content_page(url)
        bl_count  = _get_backlinks(res.get('domain', '')) if res['position'] <= 5 else 0

        ctr_est    = CTR_CURVE.get(res['position'], 0.01)
        value_score = int(page_data.get('word_count', 0) * 0.1 + bl_count * 5 + ctr_est * 1000)

        explored.append({
            'position':    res['position'],
            'url':         url,
            'domain':      res['domain'],
            'title':       page_data.get('title') or res.get('title', ''),
            'word_count':  page_data.get('word_count', 0),
            'backlinks':   bl_count,
            'has_schema':  page_data.get('has_schema', False),
            'has_faq':     page_data.get('has_faq', False),
            'has_video':   page_data.get('has_video', False),
            'value_score': value_score,
        })
        time.sleep(0.5)

    explored.sort(key=lambda x: -x['value_score'])

    # Summary
    top3 = explored[:3]
    if top3:
        avg_wc    = int(sum(e['word_count'] for e in top3) / len(top3))
        need_bl   = max(e['backlinks'] for e in top3)
        need_faq  = any(e['has_faq'] for e in top3)
        need_sch  = any(e['has_schema'] for e in top3)
        print(f'\n  📋 To rank in top 3 for "{topic}":')
        print(f'     Word count: {avg_wc}+ words')
        print(f'     Backlinks:  {need_bl}+ from relevant domains')
        print(f'     FAQ schema: {"Required ✅" if need_faq else "Optional"}')
        print(f'     Schema:     {"Required ✅" if need_sch else "Optional"}')

    return explored


def run_content_explorer(site_domain: str = TARGET_DOMAIN,
                         topics: list[str] = None) -> dict:
    """Explore multiple topics and return consolidated findings."""
    default_topics = [
        'nri property dispute lawyer',
        '498a nri husband',
        'nri legal services india',
        'power of attorney nri india',
        'oci card india',
    ]
    explore_topics = topics or default_topics
    results = {}
    for topic in explore_topics[:5]:
        findings = explore_topic(topic)
        results[topic] = findings
        time.sleep(2)
    return results


if __name__ == '__main__':
    import sys
    topic = sys.argv[1] if len(sys.argv) > 1 else 'nri property lawyer india'
    findings = explore_topic(topic)
    print(f'\nTop content for "{topic}":')
    for item in findings[:5]:
        print(f'  pos {item["position"]}: {item["word_count"]} words, '
              f'{item["backlinks"]} backlinks — {item["url"][:60]}')
