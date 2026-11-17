"""
RankPilot — AI Content Brief Generator (DeepSeek)
Pipeline: keyword → SERP analysis → content gap → competitor content → brief
Stores results in content_briefs table.

Rule 36 compliance: prompts never generate solicitation language.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import TARGET_DOMAIN
from core.db import get_session, Site, SerpAnalysisResult, ContentBrief, KeywordOpportunity
from utils.deepseek import chat, is_available
from utils.crawl import get_page_text


def _get_serp_intelligence(keyword: str, site_id: int) -> dict:
    """Pull SERP analysis data from DB for the keyword."""
    with get_session() as s:
        rows = (s.query(SerpAnalysisResult)
                .filter_by(site_id=site_id, keyword=keyword)
                .filter(SerpAnalysisResult.is_our_domain == False)
                .order_by(SerpAnalysisResult.position)
                .limit(10).all())
    if not rows:
        return {'avg_wc': 1500, 'schema_pct': 30, 'faq_pct': 20, 'has_snippet': False,
                'top_urls': [], 'note': 'No SERP data — run python run.py serp first'}
    wcs     = [r.word_count for r in rows if r.word_count]
    avg_wc  = int(sum(wcs) / len(wcs)) if wcs else 1500
    schema  = sum(1 for r in rows if r.has_schema)
    faq     = sum(1 for r in rows if r.has_faq)
    return {
        'avg_wc':       avg_wc,
        'schema_pct':   round(schema / len(rows) * 100),
        'faq_pct':      round(faq / len(rows) * 100),
        'has_snippet':  any(r.has_schema for r in rows[:1]),
        'top_urls':     [r.url for r in rows[:3] if r.url],
    }


def generate_brief(keyword: str, site_domain: str = TARGET_DOMAIN) -> str:
    """Generate a full content brief for a keyword using DeepSeek."""
    if not is_available():
        return '[Set DEEPSEEK_API_KEY in .env to generate content briefs]'

    with get_session() as s:
        site = s.query(Site).filter_by(domain=site_domain).first()
        if not site:
            return f'[Site {site_domain} not found in DB]'
        site_id = site.id

    serp = _get_serp_intelligence(keyword, site_id)

    # Fetch top 2 competitor page texts (truncated)
    comp_snippets = []
    for url in serp.get('top_urls', [])[:2]:
        text = get_page_text(url)
        if text:
            comp_snippets.append(f'URL: {url}\n{text[:1500]}')

    comp_context = '\n\n---\n\n'.join(comp_snippets) if comp_snippets else 'No competitor content fetched.'

    prompt = f"""You are an expert SEO content strategist for a legal information website.

Target keyword: {keyword}
Target domain: {site_domain}

SERP Intelligence (top 10 organic results):
- Average word count of top 10: {serp["avg_wc"]} words
- Pages with schema markup: {serp["schema_pct"]}%
- Pages with FAQ section: {serp["faq_pct"]}%
- Featured snippet present: {serp["has_snippet"]}

Top competitor content samples:
{comp_context}

Create a detailed content brief. Include:
1. Recommended page title (include keyword naturally, under 60 chars)
2. Meta description (under 155 chars, factual and descriptive)
3. Target word count with reasoning based on competitor avg
4. H2/H3 content outline — list each section with 2-3 key points to cover
5. FAQ section (5-7 specific questions users actually ask)
6. Schema markup to implement (FAQPage, Article, LegalService as appropriate)
7. Internal linking opportunities (pages on this site to link to/from)
8. Key legal facts, case citations, or statistics to include

Write in a professional, educational tone. Focus on legal accuracy and usefulness.
Do NOT include: "call us", "hire us", "contact for free consultation", "best lawyer",
"guaranteed results", "no.1", "top-rated", or any other promotional language.
This brief is for an educational legal information article, not an advertisement."""

    return chat(prompt, max_tokens=2500, temperature=0.4)


def generate_and_save(keyword: str, site_domain: str = TARGET_DOMAIN) -> dict:
    """Generate brief and save to content_briefs table."""
    with get_session() as s:
        site = s.query(Site).filter_by(domain=site_domain).first()
        if not site:
            return {'error': f'Site {site_domain} not found'}
        site_id = site.id

        # Check if brief already exists
        existing = s.query(ContentBrief).filter_by(
            site_id=site_id, keyword=keyword
        ).first()
        if existing and existing.brief_text:
            print(f'  ℹ️ Brief already exists for "{keyword}" — use status update to refresh')
            return {'status': 'exists', 'keyword': keyword}

    print(f'  Generating content brief for "{keyword}"...')
    brief_text = generate_brief(keyword, site_domain)

    if not brief_text:
        return {'error': 'DeepSeek API returned empty response'}

    serp = _get_serp_intelligence(keyword, site_id)

    with get_session() as s:
        site   = s.query(Site).filter_by(domain=site_domain).first()
        opp    = s.query(KeywordOpportunity).filter_by(
            site_id=site.id, keyword=keyword
        ).first()
        existing = s.query(ContentBrief).filter_by(
            site_id=site.id, keyword=keyword
        ).first()
        if existing:
            existing.brief_text        = brief_text
            existing.target_word_count = int(serp['avg_wc'] * 1.1)
            existing.serp_insights     = serp
            existing.status            = 'draft'
        else:
            s.add(ContentBrief(
                site_id=site.id, keyword=keyword,
                brief_text=brief_text,
                target_word_count=int(serp['avg_wc'] * 1.1),
                serp_insights=serp, status='draft',
                opportunity_id=opp.id if opp else None
            ))
        if opp:
            opp.status = 'brief'
        s.commit()

    print(f'  ✅ Brief saved for "{keyword}" ({len(brief_text)} chars)')
    return {'status': 'created', 'keyword': keyword, 'length': len(brief_text)}


def run_brief_batch(site_domain: str = TARGET_DOMAIN, max_briefs: int = 3):
    """Generate briefs for top commercial opportunities that don't have one yet."""
    with get_session() as s:
        site = s.query(Site).filter_by(domain=site_domain).first()
        if not site:
            return
        candidates = (s.query(KeywordOpportunity)
                      .filter_by(site_id=site.id, status='new')
                      .filter(KeywordOpportunity.intent.in_(['commercial', 'near-commercial']))
                      .order_by(KeywordOpportunity.est_volume.desc().nullslast())
                      .limit(max_briefs).all())
        kws = [c.keyword for c in candidates]

    if not kws:
        print('  ℹ️ No commercial opportunities to brief')
        return

    print(f'  Generating {len(kws)} content briefs...')
    for kw in kws:
        generate_and_save(kw, site_domain)


if __name__ == '__main__':
    import sys
    kw = sys.argv[1] if len(sys.argv) > 1 else 'nri property dispute lawyer india'
    result = generate_and_save(kw)
    print(result)
