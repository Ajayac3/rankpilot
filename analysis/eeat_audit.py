"""
RankPilot — E-E-A-T Audit
Checks Experience, Expertise, Authoritativeness, Trust signals on service pages.
Critical for legal/medical (YMYL) sites — Google penalises anonymous legal advice.
"""
import os, sys, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import TARGET_DOMAIN
from core.db import get_session, AuditIssue, Site
from utils.crawl import crawl_url
from utils.logger import get_logger
log = get_logger(__name__)

SERVICE_PAGES = [
    '/nri-property-dispute-lawyer/',
    '/criminal-litigation/',
    '/nri-divorce-lawyer-india/',
    '/498a-against-nri-husband/',
    '/family-litigation/',
    '/power-of-attorney-nri-india/',
    '/fir-quashing-for-nri/',
    '/nri-proclaimed-offender-legal-help/',
    '/passport-matters/',
    '/oci-matters/',
]

_SITE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         '..', 'complete_website')

def _local_html_for_url(url: str) -> str | None:
    """Return HTML from complete_website/ for a given URL path, or None if not found."""
    try:
        from urllib.parse import urlparse
        path = urlparse(url).path.strip('/')
        # Try <path>.html first, then <path>/index.html
        for candidate in [f'{path}.html', f'{path}/index.html', f'{path}']:
            local = os.path.normpath(os.path.join(_SITE_DIR, candidate))
            if os.path.isfile(local):
                with open(local, encoding='utf-8', errors='ignore') as f:
                    return f.read()
    except Exception:
        pass
    return None


def check_eeat_signals(url: str) -> dict:
    """Check a single page for E-E-A-T signals."""
    try:
        from bs4 import BeautifulSoup
        html_raw = _local_html_for_url(url)
        if html_raw is None:
            # Fall back to live fetch only if local file not found
            fetched = crawl_url(url, timeout=20)
            if not fetched['success']:
                return {'url': url, 'error': fetched.get('error', 'fetch failed'), 'score': 0, 'issues': []}
            html_raw = fetched['html']
        soup = BeautifulSoup(html_raw, 'html.parser')
        text = soup.get_text(separator=' ', strip=True).lower()
        html = str(soup).lower()
    except Exception as e:
        return {'url': url, 'error': str(e), 'score': 0, 'issues': []}

    issues = []
    score = 100

    # 1. Author byline — check structured data first, then semantic markup, then text proximity
    has_author = False

    # JSON-LD author: {"@type": "Person", "name": "..."}
    import json as _json
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            ld = _json.loads(script.string or '{}')
            if isinstance(ld, list):
                ld = ld[0] if ld else {}
            author = ld.get('author') or ld.get('creator') or {}
            if isinstance(author, list):
                author = author[0] if author else {}
            if author.get('name') or author.get('@type') == 'Person':
                has_author = True
                break
        except Exception:
            pass

    if not has_author:
        # Semantic markup: itemprop="author", rel="author", class containing "author"/"byline"
        author_elements = (
            soup.find(itemprop='author') or
            soup.find('a', rel='author') or
            soup.find(class_=lambda c: c and any(
                word in c.lower() for word in ('author', 'byline', 'contributor')
            ))
        )
        if author_elements:
            has_author = True

    if not has_author:
        # Fallback: credential keywords within the first <main>/<article>/<section> block
        main_block = soup.find('main') or soup.find('article') or soup.find('section')
        block_text = (main_block.get_text(separator=' ')[:3000].lower()
                      if main_block else text[:3000])
        credential_signals = ['adv.', 'll.b', 'll.m', 'bar council', 'enrolled advocate',
                               'senior advocate', 'high court advocate']
        if any(sig in block_text for sig in credential_signals):
            has_author = True

    if not has_author:
        issues.append({
            'type': 'missing_author',
            'severity': 'critical',
            'description': 'No verifiable author byline or structured data found — Google cannot attribute authorship',
            'fix': 'Add JSON-LD author schema (Person type) + visible byline with advocate name, LLB/LLM, Bar Council number'
        })
        score -= 25

    # 2. Last updated date visible
    date_patterns = [r'\d{1,2}\s+\w+\s+\d{4}', r'\d{4}-\d{2}-\d{2}',
                     'last updated', 'last reviewed', 'updated on', 'updated:']
    has_date = any(bool(re.search(p, html, re.I)) for p in date_patterns)
    if not has_date:
        issues.append({
            'type': 'missing_date',
            'severity': 'warning',
            'description': 'No last-updated date visible — Google values freshness for legal content',
            'fix': 'Add "Last updated: Month Year" near page title or top of content'
        })
        score -= 15

    # 3. Citations to legal sources
    citation_signals = ['section', 'act', 'bnss', 'crpc', 'ipc', 'civil procedure',
                        'transfer of property', 'high court', 'supreme court', 'judgment']
    citation_count = sum(1 for sig in citation_signals if sig in text)
    if citation_count < 3:
        issues.append({
            'type': 'low_citations',
            'severity': 'warning',
            'description': f'Only {citation_count} legal citations — top-ranking legal pages cite 5+ acts/sections',
            'fix': 'Add specific section references: e.g. "Section 82 BNSS (formerly 82 CrPC)", "Order 39 Rule 1 CPC"'
        })
        score -= 10

    # 4. Word count check (YMYL pages need substantial content)
    word_count = len(text.split())
    if word_count < 800:
        issues.append({
            'type': 'thin_content',
            'severity': 'critical',
            'description': f'Only {word_count} words — legal service pages need 1,000+ words for E-E-A-T',
            'fix': f'Expand to at least 1,200 words. Add: process explanation, FAQ section, case types, how we help'
        })
        score -= 20

    # 5. FAQ schema check
    has_faq_schema = '"FAQPage"' in html or '"faqpage"' in html
    if not has_faq_schema:
        issues.append({
            'type': 'missing_faq_schema',
            'severity': 'info',
            'description': 'No FAQPage JSON-LD schema — missing rich result opportunity',
            'fix': 'Add FAQPage schema with 4-5 common questions about this service'
        })
        score -= 5

    # 6. Contact/consultation CTA present
    cta_signals = ['whatsapp', 'consultation', 'call now', 'contact us', 'get in touch']
    has_cta = any(sig in text for sig in cta_signals)
    if not has_cta:
        issues.append({
            'type': 'missing_cta',
            'severity': 'warning',
            'description': 'No clear contact/consultation CTA found on page',
            'fix': 'Add WhatsApp CTA button and "Book Free Consultation" link'
        })
        score -= 10

    return {
        'url': url,
        'score': max(0, score),
        'word_count': word_count,
        'has_author': has_author,
        'has_date': has_date,
        'has_faq_schema': has_faq_schema,
        'citation_count': citation_count,
        'issues': issues
    }

def run_eeat_audit(site_domain: str = TARGET_DOMAIN) -> list[dict]:
    """Audit all service pages for E-E-A-T signals."""
    base_url = f'https://{site_domain}'
    results = []

    print(f'  Running E-E-A-T audit on {len(SERVICE_PAGES)} pages...')

    for page_path in SERVICE_PAGES:
        url = base_url + page_path
        result = check_eeat_signals(url)
        results.append(result)

        score = result.get('score', 0)
        marker = '🔴' if score < 60 else ('🟡' if score < 80 else '✅')
        print(f'    {marker} {page_path} — Score: {score}/100 ({len(result.get("issues", []))} issues)')

        # Save issues to DB
        with get_session() as s:
            site = s.query(Site).filter_by(domain=site_domain).first()
            if site:
                for issue in result.get('issues', []):
                    s.add(AuditIssue(
                        site_id=site.id,
                        page_url=url,
                        issue_type=f'eeat_{issue["type"]}',
                        severity=issue['severity'],
                        description=issue['description'],
                        remediation=issue['fix'],
                        status='open'
                    ))
                s.commit()

    # Summary
    avg_score = sum(r.get('score', 0) for r in results) / len(results) if results else 0
    critical = sum(1 for r in results for i in r.get('issues', []) if i['severity'] == 'critical')
    print(f'\n  E-E-A-T Summary: Avg score {avg_score:.0f}/100 | {critical} critical issues')

    return results

if __name__ == '__main__':
    results = run_eeat_audit()
    print('\nPages needing attention:')
    for r in sorted(results, key=lambda x: x.get('score', 0))[:5]:
        path = r['url'].replace(f'https://{TARGET_DOMAIN}', '')
        print(f'  {path} — {r.get("score", 0)}/100')
        for issue in r.get('issues', [])[:2]:
            print(f'    → {issue["description"]}')
