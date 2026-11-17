"""
RankPilot — GSC-only Content Gap Detector

Surfaces queries that Google is already showing the site for (has impressions)
but where no dedicated page exists targeting that query. Zero external API calls.
"""
import os, re, sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.db import get_session, Site, GscQuery
from sqlalchemy import func as _func
from utils.logger import get_logger

log = get_logger(__name__)

# Words that carry no meaning for matching purposes
_STOPWORDS = {
    'a', 'an', 'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
    'of', 'with', 'by', 'from', 'as', 'is', 'are', 'was', 'were', 'be',
    'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
    'would', 'could', 'should', 'may', 'might', 'can', 'how', 'what',
    'when', 'where', 'who', 'which', 'that', 'this', 'these', 'those',
    'my', 'your', 'his', 'her', 'its', 'our', 'their', 'i', 'you', 'he',
    'she', 'it', 'we', 'they', 'me', 'him', 'us', 'them', 'about', 'after',
    'against', 'between', 'into', 'through', 'during', 'before', 'under',
    'india', 'indian', 'nri', 'legal',  # too broad to be discriminating
}


def _extract_keywords(text: str) -> set[str]:
    words = re.findall(r'[a-z]+', text.lower())
    return {w for w in words if len(w) >= 3 and w not in _STOPWORDS}


def _build_page_index(site_root: str) -> list[dict]:
    """Build list of {slug, title, keywords} from complete_website/ HTML files."""
    pages = []
    root = Path(site_root)
    if not root.exists():
        return pages

    for html_file in root.glob('*.html'):
        slug = html_file.stem  # e.g. "nri-property-dispute-lawyer"
        # Parse title from file (just grab the first <title> tag)
        try:
            content = html_file.read_text(encoding='utf-8', errors='ignore')
            title_match = re.search(r'<title[^>]*>(.*?)</title>', content, re.IGNORECASE | re.DOTALL)
            title = title_match.group(1).strip() if title_match else ''
        except Exception:
            title = ''

        slug_words = set(slug.replace('-', ' ').split())
        title_words = _extract_keywords(title)
        keywords = slug_words | title_words
        pages.append({'slug': slug, 'title': title, 'keywords': keywords})

    return pages


def _match_score(query_keywords: set[str], page: dict) -> float:
    """Return fraction of query keywords found in page slug+title. 0.0–1.0."""
    if not query_keywords:
        return 0.0
    matched = query_keywords & page['keywords']
    return len(matched) / len(query_keywords)


def detect_content_gaps(
    site_domain: str = None,
    min_impressions: int = 50,
    match_threshold: float = 0.55,
    top_n: int = 30,
) -> list[dict]:
    """
    Find GSC queries with significant impressions that no existing page covers.

    Args:
        site_domain: domain string, or None to use first site in DB
        min_impressions: minimum aggregated impressions to consider a query
        match_threshold: minimum keyword overlap to consider a page a "match"
        top_n: maximum number of gaps to return

    Returns:
        List of gap dicts sorted by opportunity score (impressions × avg_position_gap).
    """
    site_root = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        'complete_website'
    )
    pages = _build_page_index(site_root)
    log.info(f'Content gap: indexed {len(pages)} pages from {site_root}')

    if not pages:
        log.warning('No pages indexed — check site_root path')
        return []

    with get_session() as s:
        if site_domain:
            site = s.query(Site).filter_by(domain=site_domain).first()
        else:
            site = s.query(Site).first()

        if not site:
            log.warning('No site found in DB')
            return []

        latest_date = s.query(_func.max(GscQuery.date)).filter_by(site_id=site.id).scalar()
        if not latest_date:
            log.warning('No GSC query data in DB')
            return []

        # Aggregate across all dimensions (device/country) for the latest date
        rows = s.query(
            GscQuery.query,
            _func.sum(GscQuery.impressions).label('total_impressions'),
            _func.sum(GscQuery.clicks).label('total_clicks'),
            (
                _func.sum(GscQuery.position * GscQuery.impressions) /
                _func.sum(GscQuery.impressions)
            ).label('avg_position'),
        ).filter(
            GscQuery.site_id == site.id,
            GscQuery.date == latest_date,
        ).group_by(GscQuery.query).all()

    gaps = []
    for row in rows:
        if (row.total_impressions or 0) < min_impressions:
            continue

        query_kw = _extract_keywords(row.query)
        if not query_kw:
            continue

        # Check if any existing page matches the query well enough
        best_score = max((_match_score(query_kw, p) for p in pages), default=0.0)

        if best_score < match_threshold:
            # No page covers this query — it's a gap
            position = float(row.avg_position or 50)
            # Opportunity: high impressions + position far from top = bigger gap to exploit
            position_gap = max(0, 20 - position)
            opportunity = round((row.total_impressions or 0) * position_gap, 1)
            gaps.append({
                'query': row.query,
                'impressions': int(row.total_impressions or 0),
                'clicks': int(row.total_clicks or 0),
                'avg_position': round(position, 1),
                'ctr_pct': round(
                    (row.total_clicks or 0) / (row.total_impressions or 1) * 100, 2
                ),
                'best_page_match_score': round(best_score, 2),
                'opportunity_score': opportunity,
            })

    # Sort by opportunity descending
    gaps.sort(key=lambda x: -x['opportunity_score'])
    return gaps[:top_n]


def print_gaps(gaps: list[dict]) -> None:
    if not gaps:
        print('No content gaps detected.')
        return
    print(f'\n{"="*70}')
    print(f'CONTENT GAPS — {len(gaps)} queries with no matching page')
    print(f'{"="*70}')
    print(f'{"Query":<40} {"Impr":>6} {"Pos":>6} {"CTR":>6} {"Score":>8}')
    print('-' * 70)
    for g in gaps:
        print(
            f'{g["query"][:40]:<40} {g["impressions"]:>6} '
            f'{g["avg_position"]:>6.1f} {g["ctr_pct"]:>5.1f}% {g["opportunity_score"]:>8.0f}'
        )


if __name__ == '__main__':
    gaps = detect_content_gaps(min_impressions=20, top_n=30)
    print_gaps(gaps)
