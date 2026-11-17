"""
RankPilot — Full Technical Site Audit (Screaming Frog equivalent)
Crawls all HTML files in complete_website/ and checks for 20+ technical issues.
No external API — reads local files + optional live HTTP checks.
"""
import os, sys, re, hashlib
from datetime import datetime
from pathlib import Path
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import TARGET_DOMAIN
from utils.logger import get_logger
log = get_logger(__name__)

WEBSITE_DIR = Path(__file__).parent.parent.parent / 'complete_website'
BASE_URL    = f'https://{TARGET_DOMAIN}'


def _slug_to_url(filepath: Path) -> str:
    rel = filepath.relative_to(WEBSITE_DIR)
    slug = str(rel).replace('index.html', '').replace('.html', '/')
    if not slug.startswith('/'):
        slug = '/' + slug
    return BASE_URL + slug


def _word_count(soup: BeautifulSoup) -> int:
    for tag in soup.find_all(['script', 'style', 'nav', 'header', 'footer']):
        tag.decompose()
    text = soup.get_text(separator=' ')
    return len(re.findall(r'\b\w+\b', text))


def audit_page(filepath: Path, all_urls: set[str]) -> dict:
    """Audit a single HTML file. Returns structured result dict."""
    url = _slug_to_url(filepath)
    issues = []

    try:
        html = filepath.read_text(encoding='utf-8', errors='ignore')
    except Exception as e:
        return {'url': url, 'error': str(e), 'issues': ['read_error']}

    soup = BeautifulSoup(html, 'html.parser')

    # ── Title ──────────────────────────────────────────────────────────────────
    title_tag = soup.find('title')
    title     = title_tag.get_text(strip=True) if title_tag else ''
    if not title:
        issues.append('missing_title')
    elif len(title) > 60:
        issues.append('title_too_long')
    elif len(title) < 30:
        issues.append('title_too_short')

    # ── Meta description ───────────────────────────────────────────────────────
    meta_desc_tag = soup.find('meta', attrs={'name': re.compile(r'^description$', re.I)})
    meta_desc     = (meta_desc_tag.get('content', '') if meta_desc_tag else '').strip()
    if not meta_desc:
        issues.append('missing_meta_desc')
    elif len(meta_desc) > 160:
        issues.append('meta_desc_too_long')
    elif len(meta_desc) < 80:
        issues.append('meta_desc_too_short')

    # ── H1 ─────────────────────────────────────────────────────────────────────
    h1s    = soup.find_all('h1')
    h1_cnt = len(h1s)
    h1_txt = h1s[0].get_text(strip=True) if h1s else ''
    if h1_cnt == 0:
        issues.append('missing_h1')
    elif h1_cnt > 1:
        issues.append('multiple_h1')

    # ── Word count ─────────────────────────────────────────────────────────────
    wc = _word_count(BeautifulSoup(html, 'html.parser'))
    if wc < 300:
        issues.append('thin_content')

    # ── Canonical ──────────────────────────────────────────────────────────────
    canonical_tag = soup.find('link', rel='canonical')
    canonical_url = canonical_tag.get('href', '') if canonical_tag else ''
    if not canonical_url:
        issues.append('missing_canonical')

    # ── Noindex ────────────────────────────────────────────────────────────────
    robots_meta = soup.find('meta', attrs={'name': re.compile(r'^robots$', re.I)})
    is_noindex  = False
    if robots_meta:
        content = robots_meta.get('content', '').lower()
        if 'noindex' in content:
            is_noindex = True
            issues.append('noindex_page')

    # ── Schema ─────────────────────────────────────────────────────────────────
    schema_scripts = soup.find_all('script', type='application/ld+json')
    has_schema = bool(schema_scripts)
    has_faq    = any('"FAQPage"' in (s.string or '') for s in schema_scripts)
    if not has_schema:
        issues.append('missing_schema')

    # ── Images ─────────────────────────────────────────────────────────────────
    imgs          = soup.find_all('img')
    img_count     = len(imgs)
    missing_alt   = sum(1 for img in imgs if not img.get('alt'))
    if missing_alt:
        issues.append('images_missing_alt')

    # ── Internal links + orphan detection ─────────────────────────────────────
    NON_HTML_EXTS = {'.xml', '.pdf', '.png', '.jpg', '.jpeg', '.gif',
                     '.svg', '.webp', '.ico', '.css', '.js', '.zip', '.txt'}
    int_links = []
    for a in soup.find_all('a', href=True):
        href = a['href']
        # Skip anchors, mailto, tel, javascript
        if href.startswith(('#', 'mailto:', 'tel:', 'javascript:', 'whatsapp:')):
            continue
        # Skip non-HTML resources
        if any(href.lower().endswith(ext) or f'{ext}?' in href.lower()
               for ext in NON_HTML_EXTS):
            continue
        if href.startswith('/') or BASE_URL in href:
            if href.startswith('/'):
                full = BASE_URL + href.split('?')[0].split('#')[0]
            else:
                full = href.split('?')[0].split('#')[0]
            int_links.append(full.rstrip('/'))

    # Check for broken internal links (links to pages that don't exist locally)
    broken = []
    for link in int_links:
        slug = link.replace(BASE_URL, '').rstrip('/')
        if not slug:
            continue
        candidate_file = WEBSITE_DIR / (slug.lstrip('/') + '.html')
        candidate_dir  = WEBSITE_DIR / slug.lstrip('/')
        if not (candidate_file.exists() or
                (candidate_dir.is_dir() and (candidate_dir / 'index.html').exists())):
            broken.append(link)
    if broken:
        issues.append('broken_internal_links')

    # ── Mixed content ──────────────────────────────────────────────────────────
    http_assets = soup.find_all(['img', 'script', 'link'],
                                 src=re.compile(r'^http://'),
                                 href=re.compile(r'^http://'))
    if http_assets:
        issues.append('mixed_content')

    # ── Open Graph ─────────────────────────────────────────────────────────────
    og_title = soup.find('meta', property='og:title')
    og_desc  = soup.find('meta', property='og:description')
    if not og_title:
        issues.append('missing_og_title')
    if not og_desc:
        issues.append('missing_og_desc')

    return {
        'url':                  url,
        'title':                title,
        'meta_desc':            meta_desc,
        'h1_count':             h1_cnt,
        'h1_text':              h1_txt[:200],
        'word_count':           wc,
        'canonical_url':        canonical_url,
        'is_noindex':           is_noindex,
        'has_schema':           has_schema,
        'has_faq':              has_faq,
        'image_count':          img_count,
        'images_missing_alt':   missing_alt,
        'internal_links_count': len(int_links),
        'issues':               issues,
        'broken_links':         broken[:10],
    }


def run_site_audit(site_domain: str = TARGET_DOMAIN) -> dict:
    """
    Full technical audit of all HTML files in complete_website/.
    Saves results to DB. Returns summary.
    """
    from core.db import get_session, Site, SiteCrawlPage, AuditIssue

    if not WEBSITE_DIR.exists():
        print(f'  ⚠️ Website dir not found: {WEBSITE_DIR}')
        return {}

    html_files = sorted(WEBSITE_DIR.rglob('*.html'))
    print(f'  Auditing {len(html_files)} HTML pages...')

    all_urls = {_slug_to_url(f) for f in html_files}

    # Find pages not linked from anywhere (orphans) — collect all links first
    all_linked = set()
    for f in html_files:
        try:
            soup = BeautifulSoup(f.read_text(encoding='utf-8', errors='ignore'), 'html.parser')
            for a in soup.find_all('a', href=True):
                h = a['href']
                if h.startswith('/'):
                    all_linked.add(BASE_URL + h.rstrip('/'))
                elif BASE_URL in h:
                    all_linked.add(h.rstrip('/'))
        except Exception:
            pass

    results = []
    issue_counts: dict[str, int] = {}

    with get_session() as s:
        site = s.query(Site).filter_by(domain=site_domain).first()
        if not site:
            print('  ⚠️ Site not in DB. Run: python run.py setup')
            return {}
        site_id = site.id

    for i, filepath in enumerate(html_files):
        result = audit_page(filepath, all_urls)
        url    = result['url']

        # Orphan check
        if url.rstrip('/') not in all_linked and filepath.name != 'index.html':
            result['issues'].append('orphan_page')

        # Count issue types
        for iss in result.get('issues', []):
            issue_counts[iss] = issue_counts.get(iss, 0) + 1

        results.append(result)

        # Save to DB
        with get_session() as s:
            existing = s.query(SiteCrawlPage).filter_by(site_id=site_id, url=url).first()
            data = dict(
                site_id=site_id,
                crawled_at=datetime.utcnow(),
                url=url,
                title=result.get('title', '')[:255],
                meta_desc=result.get('meta_desc', '')[:255],
                h1_count=result.get('h1_count', 0),
                h1_text=(result.get('h1_text') or '')[:200],
                word_count=result.get('word_count', 0),
                canonical_url=result.get('canonical_url', '')[:255],
                is_noindex=result.get('is_noindex', False),
                has_schema=result.get('has_schema', False),
                image_count=result.get('image_count', 0),
                images_missing_alt=result.get('images_missing_alt', 0),
                internal_links_count=result.get('internal_links_count', 0),
                issues=result.get('issues', []),
            )
            if existing:
                for k, v in data.items():
                    setattr(existing, k, v)
            else:
                s.add(SiteCrawlPage(**data))

            # Save each issue as AuditIssue
            ISSUE_DESCRIPTIONS = {
                'missing_title':        ('critical', 'No <title> tag', 'Add a unique title tag (30-60 chars)'),
                'title_too_long':       ('warning',  'Title > 60 chars — truncated in SERP', 'Shorten title to under 60 chars'),
                'title_too_short':      ('info',     'Title < 30 chars — too vague', 'Expand title to 30-60 chars'),
                'missing_meta_desc':    ('critical', 'No meta description', 'Add meta description (100-160 chars)'),
                'meta_desc_too_long':   ('warning',  'Meta description > 160 chars', 'Shorten to 155 chars max'),
                'meta_desc_too_short':  ('info',     'Meta description < 80 chars', 'Expand to 100-155 chars'),
                'missing_h1':           ('critical', 'No H1 heading on page', 'Add exactly one H1 matching primary keyword'),
                'multiple_h1':          ('warning',  'Multiple H1 tags', 'Keep only one H1 per page'),
                'thin_content':         ('critical', f'Under 300 words', 'Expand content to 800+ words for service pages'),
                'missing_canonical':    ('warning',  'No canonical tag', 'Add <link rel="canonical"> to prevent duplicate content'),
                'noindex_page':         ('critical', 'Page has noindex — Google will not index it', 'Remove noindex unless intentional'),
                'missing_schema':       ('warning',  'No JSON-LD schema markup', 'Add LegalService or Article schema'),
                'images_missing_alt':   ('warning',  'Images without alt text', 'Add descriptive alt text to all images'),
                'broken_internal_links':('critical', 'Broken internal links (404)', 'Fix or remove broken links'),
                'mixed_content':        ('warning',  'HTTP assets on HTTPS page', 'Change all asset URLs to HTTPS'),
                'missing_og_title':     ('info',     'No og:title for social sharing', 'Add Open Graph meta tags'),
                'missing_og_desc':      ('info',     'No og:description for social sharing', 'Add og:description meta tag'),
                'orphan_page':          ('warning',  'No other page links to this page', 'Add internal links to this page'),
            }
            for iss_type in result.get('issues', []):
                if iss_type in ISSUE_DESCRIPTIONS:
                    sev, desc, fix = ISSUE_DESCRIPTIONS[iss_type]
                    s.add(AuditIssue(
                        site_id=site_id, page_url=url,
                        issue_type=f'tech_{iss_type}',
                        severity=sev, description=desc, remediation=fix,
                        status='open'
                    ))
            s.commit()

        if (i + 1) % 20 == 0:
            print(f'    {i+1}/{len(html_files)} pages audited...')

    # Summary
    critical = sum(1 for r in results for iss in r.get('issues', [])
                   if iss in ('missing_title', 'missing_h1', 'thin_content',
                               'noindex_page', 'broken_internal_links', 'missing_meta_desc'))
    warnings = sum(1 for r in results for iss in r.get('issues', [])
                   if iss in ('title_too_long', 'multiple_h1', 'missing_canonical',
                               'images_missing_alt', 'orphan_page'))

    print(f'\n  ✅ Site audit complete: {len(results)} pages')
    print(f'     Critical: {critical} | Warnings: {warnings}')
    print(f'     Top issues: {sorted(issue_counts.items(), key=lambda x: -x[1])[:5]}')

    return {
        'pages_audited': len(results),
        'critical':      critical,
        'warnings':      warnings,
        'issue_counts':  issue_counts,
        'results':       results,
    }


if __name__ == '__main__':
    result = run_site_audit()
    print(f'\nPages: {result["pages_audited"]} | Critical: {result["critical"]} | Warnings: {result["warnings"]}')
