"""
RankPilot — Content Gap Analyser
Uses spaCy + TF-IDF to find topics that top-ranking competitors cover but we don't.
Tells us exactly what to add to each page to rank higher.
"""
import os, sys, re, requests
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import SERPER_KEY, VALUESERP_KEY, TARGET_DOMAIN
from core.db import get_session, Site, GscPage
from utils.crawl import get_page_text
from utils.logger import get_logger
log = get_logger(__name__)

def get_top10_urls(keyword: str, country: str = 'in') -> list[str]:
    """Get top 10 SERP URLs. Uses Serper → ValueSERP → empty."""
    if SERPER_KEY:
        try:
            r = requests.post(
                'https://google.serper.dev/search',
                headers={'X-API-KEY': SERPER_KEY, 'Content-Type': 'application/json'},
                json={'q': keyword, 'gl': country, 'num': 10},
                timeout=15
            )
            if r.status_code == 200:
                return [res.get('link', '') for res in r.json().get('organic', [])[:10]
                        if res.get('link')]
        except:
            pass
    if VALUESERP_KEY:
        try:
            r = requests.get('https://api.valueserp.com/search',
                             params={'api_key': VALUESERP_KEY, 'q': keyword,
                                     'gl': country, 'num': '10'}, timeout=20)
            if r.status_code == 200:
                return [res.get('link', '') for res in r.json().get('organic_results', [])[:10]
                        if res.get('link')]
        except:
            pass
    return []

def extract_key_phrases(text: str, top_n: int = 50) -> list[str]:
    """Extract important noun phrases using spaCy."""
    try:
        import spacy
        nlp = spacy.load('en_core_web_sm')
        doc = nlp(text[:5000])
        phrases = []
        # Noun chunks
        for chunk in doc.noun_chunks:
            phrase = chunk.text.lower().strip()
            if 3 < len(phrase) < 60 and not phrase.isdigit():
                phrases.append(phrase)
        # Named entities
        for ent in doc.ents:
            if ent.label_ in ('LAW', 'ORG', 'GPE', 'PERSON'):
                phrases.append(ent.text.lower().strip())
        return phrases
    except:
        # Fallback: simple term extraction without spaCy
        words = re.findall(r'\b[a-z]{4,}\b', text.lower())
        stopwords = {'that', 'this', 'with', 'have', 'from', 'they', 'been',
                     'more', 'will', 'also', 'when', 'what', 'your', 'their',
                     'than', 'some', 'into', 'which', 'after', 'about'}
        return [w for w in words if w not in stopwords]

def analyse_content_gap(our_page_url: str, keyword: str, country: str = 'in') -> dict:
    """
    Compare our page against top 10 competitors.
    Returns topics/phrases in competitor pages but missing from ours.
    """
    print(f'  Analysing content gap for: {keyword}')

    # Fetch competitor pages
    competitor_urls = get_top10_urls(keyword, country)
    if not competitor_urls:
        return {'missing_topics': [], 'our_coverage': 0, 'error': 'no_serp_data'}

    # Filter out our own domain
    our_domain = TARGET_DOMAIN.lower()
    competitor_urls = [u for u in competitor_urls if our_domain not in u.lower()][:5]

    print(f'    Analysing {len(competitor_urls)} competitor pages...')

    # Extract phrases from competitors
    competitor_phrases = Counter()
    for url in competitor_urls:
        text = get_page_text(url)
        if text:
            phrases = extract_key_phrases(text)
            for phrase in phrases:
                competitor_phrases[phrase] += 1

    # Extract phrases from our page
    our_text = get_page_text(our_page_url)
    our_phrases = set(extract_key_phrases(our_text)) if our_text else set()

    # Filter out lorem ipsum placeholder content that leaks from poorly-built competitor pages
    PLACEHOLDER_TOKENS = {'lorem', 'ipsum', 'consectetur', 'adipiscing', 'bibendum',
                          'ultricies', 'interdum', 'convallis', 'pretium', 'pellentesque',
                          'vestibulum', 'malesuada', 'faucibus', 'elementum', 'porttitor'}

    def _is_placeholder(phrase: str) -> bool:
        return any(tok in phrase.lower() for tok in PLACEHOLDER_TOKENS)

    # Find topics in 3+ competitor pages that we're missing
    threshold = min(3, len(competitor_urls) - 1)
    high_frequency = {phrase: count for phrase, count in competitor_phrases.items()
                      if count >= threshold and len(phrase) > 5 and not _is_placeholder(phrase)}

    missing = {phrase: count for phrase, count in high_frequency.items()
               if phrase not in our_phrases}

    # Sort by frequency (most common across competitors = most important)
    sorted_missing = sorted(missing.items(), key=lambda x: -x[1])[:20]

    coverage = len(our_phrases) / max(len(high_frequency), 1) * 100

    return {
        'keyword': keyword,
        'our_url': our_page_url,
        'competitors_checked': len(competitor_urls),
        'our_coverage_pct': round(coverage, 1),
        'missing_topics': [{'topic': t, 'competitor_coverage': f'{c}/{len(competitor_urls)}'}
                           for t, c in sorted_missing],
        'total_missing': len(missing)
    }

def _get_top_pages(site_domain: str) -> list[tuple[str, str]]:
    """Get top-clicked pages from DB with inferred keyword from URL slug."""
    try:
        from sqlalchemy import func
        with get_session() as s:
            site = s.query(Site).filter_by(domain=site_domain).first()
            if not site:
                return []
            # Aggregate clicks per page (multiple date rows exist for the same page)
            rows = (s.query(GscPage.page, func.sum(GscPage.clicks).label('total_clicks'))
                    .filter_by(site_id=site.id)
                    .group_by(GscPage.page)
                    .order_by(func.sum(GscPage.clicks).desc())
                    .limit(10).all())
            result = []
            for page, _ in rows:
                url = page if page.startswith('http') else f'https://{site_domain}{page}'
                slug = page.rstrip('/').split('/')[-1].replace('-', ' ').strip()
                if slug:
                    result.append((url, slug))
            return result
    except Exception:
        return []


def run_content_gap(site_domain: str = TARGET_DOMAIN) -> list[dict]:
    """Run content gap analysis on top pages (from GSC data or defaults)."""
    pages_to_analyse = _get_top_pages(site_domain)
    if not pages_to_analyse:
        pages_to_analyse = [
            (f'https://{site_domain}/nri-property-dispute-lawyer/', 'nri property dispute lawyer'),
            (f'https://{site_domain}/nri-divorce-lawyer-india/', 'nri divorce lawyer india'),
            (f'https://{site_domain}/498a-against-nri-husband/', '498a nri husband'),
            (f'https://{site_domain}/criminal-litigation/', 'nri criminal lawyer india'),
            (f'https://{site_domain}/power-of-attorney-nri-india/', 'power of attorney for nri'),
        ]

    results = []
    for url, keyword in pages_to_analyse[:5]:
        gap = analyse_content_gap(url, keyword)
        results.append(gap)
        if gap.get('missing_topics'):
            print(f'    ⚠️ {keyword}: {gap["total_missing"]} missing topics')
            for item in gap['missing_topics'][:5]:
                print(f'       Add: "{item["topic"]}" ({item["competitor_coverage"]} competitors)')

    return results

if __name__ == '__main__':
    result = analyse_content_gap(
        f'https://{TARGET_DOMAIN}/nri-property-dispute-lawyer/',
        'nri property dispute lawyer',
        'in'
    )
    print(f'\nContent coverage: {result["our_coverage_pct"]}%')
    print(f'Missing topics ({result["total_missing"]}):')
    for item in result['missing_topics'][:10]:
        print(f'  + "{item["topic"]}" ({item["competitor_coverage"]} competitors use this)')
