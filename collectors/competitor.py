"""
RankPilot — Competitor Monitor
Fetches competitor sitemaps daily, detects new pages, diffs content.
New competitor page = alert in weekly report.
"""
import os, sys, hashlib, requests
from datetime import date
from xml.etree import ElementTree
from sqlalchemy.exc import IntegrityError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import COMPETITORS, TARGET_DOMAIN
from core.db import get_session, Competitor, CompetitorUrl, Site, AuditIssue, Keyword, KeywordOpportunity
from utils.crawl import get_page_title_and_hash

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (compatible; RankPilotBot/0.1; +https://rankpilot.io)',
}

def fetch_sitemap_urls(sitemap_url: str) -> list[str]:
    """Fetch all URLs from a sitemap (handles sitemap index too)."""
    try:
        r = requests.get(sitemap_url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return []
        root = ElementTree.fromstring(r.content)
        ns = {'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'}

        # Check if sitemap index (contains other sitemaps)
        sitemaps = root.findall('sm:sitemap/sm:loc', ns)
        if sitemaps:
            all_urls = []
            for sm in sitemaps[:10]:   # limit to first 10 sub-sitemaps
                all_urls.extend(fetch_sitemap_urls(sm.text.strip()))
            return all_urls

        # Regular sitemap
        return [loc.text.strip() for loc in root.findall('sm:url/sm:loc', ns)]
    except Exception as e:
        print(f'  ⚠️ Sitemap error {sitemap_url}: {e}')
        return []

_JUNK_PATTERNS = (
    '/tag/', '/category/', '/page/', '/author/', '/feed/',
    '/wp-', '/attachment/', '/?p=', '?p=', '?page_id=',
)

def _is_content_url(url: str) -> bool:
    """Return False for WordPress tag/category/utility pages that are not real content."""
    u = url.lower()
    for pat in _JUNK_PATTERNS:
        if pat in u:
            return False
    # Slug is the last non-empty path segment
    slug = u.rstrip('/').split('/')[-1].split('?')[0]
    # Skip slugs shorter than 4 chars (e.g. /wp/, /rss, /api, /en/)
    if len(slug) < 4:
        return False
    # Skip pure year numbers like /2023/, /2024/
    if slug.isdigit() and len(slug) == 4:
        return False
    return True


def get_page_title(url: str) -> str:
    title, _ = get_page_title_and_hash(url)
    return title

def content_hash(url: str) -> str:
    _, chash = get_page_title_and_hash(url)
    return chash

def _flag_content_change(session, comp: 'Competitor', cu: 'CompetitorUrl', new_hash: str):
    """Log a content-changed audit issue when a competitor page hash differs."""
    from core.db import Site
    site = session.query(Site).filter_by(id=comp.site_id).first()
    if not site:
        return
    print(f'    📝 Content changed: {cu.url}')
    session.add(AuditIssue(
        site_id=site.id,
        page_url=cu.url,
        issue_type='competitor_content_changed',
        severity='info',
        description=f'{comp.domain} updated: {cu.title or cu.url}',
        remediation='Review their updated page and check if it targets keywords you should be competing on.',
        status='open'
    ))


def _generate_counter_brief(comp_url: str, comp_title: str,
                            matching_keywords: list[str]) -> str:
    """Use DeepSeek to generate a counter-content strategy for a new competitor page."""
    try:
        from utils.deepseek import chat, is_available
        if not is_available() or not matching_keywords:
            return ''
        from utils.crawl import get_page_text
        page_text = get_page_text(comp_url) or ''
        prompt = (
            f'A competitor just published a new page targeting NRI legal clients.\n\n'
            f'Competitor URL: {comp_url}\n'
            f'Their title: {comp_title}\n'
            f'Keywords this page threatens: {", ".join(matching_keywords[:5])}\n\n'
            f'Their content (first 2000 chars):\n{page_text[:2000]}\n\n'
            f'In 150 words:\n'
            f'1. What angle are they taking?\n'
            f'2. What could we cover differently or more in-depth?\n'
            f'3. Which existing pages on our site could be updated to compete?\n\n'
            f'Do not include promotional language.'
        )
        return chat(prompt, max_tokens=250, temperature=0.3)
    except Exception:
        return ''


def _get_matching_keywords(url: str, title: str, site_id: int) -> list[str]:
    """Find tracked keywords or opportunities that this competitor URL might target."""
    slug_words = set(url.rstrip('/').split('/')[-1].lower().replace('-', ' ').split())
    title_words = set(title.lower().split()) if title else set()
    all_words   = slug_words | title_words
    matches     = []
    try:
        with get_session() as s:
            kws = s.query(Keyword).filter_by(site_id=site_id).all()
            for kw in kws:
                kw_words = set(kw.keyword.lower().split())
                if len(kw_words & all_words) >= 2:
                    matches.append(kw.keyword)
    except Exception:
        pass
    return matches[:5]


def run_competitor_monitor(site_domain: str = TARGET_DOMAIN) -> list[dict]:
    """
    Check all competitor sitemaps for new URLs.
    Returns list of new URLs discovered since last run.
    """
    with get_session() as s:
        site = s.query(Site).filter_by(domain=site_domain).first()
        if not site:
            return []
        site_id_val = site.id
        competitors = s.query(Competitor).filter_by(site_id=site.id).all()

    new_pages = []

    for comp in competitors:
        if not comp.sitemap_url:
            continue

        print(f'  Checking {comp.domain}...')
        urls = fetch_sitemap_urls(comp.sitemap_url)
        print(f'    {len(urls)} URLs in sitemap')

        with get_session() as s:
            known_urls = {cu.url for cu in
                          s.query(CompetitorUrl).filter_by(competitor_id=comp.id).all()}

        discovered = [u for u in urls if u not in known_urls and _is_content_url(u)]

        if discovered:
            print(f'    🆕 {len(discovered)} NEW pages found at {comp.domain}')

        # Store new URLs immediately without HTTP fetching — title/hash enriched in weekly run
        inserted_this_run: set[str] = set()
        with get_session() as s:
            for url in discovered:
                if url in inserted_this_run:
                    continue
                # Derive a readable title from the URL slug (free, instant)
                slug = url.rstrip('/').split('/')[-1].replace('-', ' ').replace('_', ' ').title()
                new_pages.append({
                    'competitor': comp.domain,
                    'url': url,
                    'title': slug,
                    'date': date.today()
                })
                try:
                    s.add(CompetitorUrl(
                        competitor_id=comp.id, url=url,
                        title=slug, first_seen=date.today(),
                        last_seen=date.today(), is_new=True,
                        content_hash=None
                    ))
                    s.flush()
                    inserted_this_run.add(url)
                except IntegrityError:
                    s.rollback()
            s.commit()

        # Generate counter-brief for new pages that match our keywords (first 3 only)
        counter_count = 0
        for p in new_pages[-len(discovered):]:
            if counter_count >= 3:
                break
            matching_kws = _get_matching_keywords(p['url'], p['title'], site_id_val)
            if matching_kws:
                brief = _generate_counter_brief(p['url'], p['title'], matching_kws)
                if brief:
                    with get_session() as s:
                        s.add(AuditIssue(
                            site_id=site_id_val,
                            page_url=p['url'],
                            issue_type='competitor_counter_brief',
                            severity='info',
                            description=f'{comp.domain} new page targets: {", ".join(matching_kws[:3])}',
                            remediation=brief,
                            status='open'
                        ))
                        s.commit()
                    counter_count += 1

        # Update last_seen for all known URLs (DB-only, no HTTP)
        url_set = set(urls)
        with get_session() as s:
            for cu in s.query(CompetitorUrl).filter_by(competitor_id=comp.id).all():
                cu.last_seen = date.today()
            s.commit()

    return new_pages

if __name__ == '__main__':
    new = run_competitor_monitor()
    if new:
        print(f'\n🚨 {len(new)} new competitor pages this week:')
        for p in new:
            print(f'  [{p["competitor"]}] {p["url"]}')
            if p["title"]: print(f'    Title: {p["title"]}')
    else:
        print('No new competitor pages detected.')
