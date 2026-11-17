"""
RankPilot — LLM Citation Tracker
Checks if the site is cited in Perplexity AI responses (online search model).
Saves to aeo_results table with engine='perplexity'.
Requires PERPLEXITY_API_KEY (~$0.0001/query).
"""
import os, sys, requests
from datetime import date
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import TARGET_DOMAIN, PERPLEXITY_API_KEY
from core.db import get_session, Site, AeoResult, Keyword

# Priority queries to check citation for
DEFAULT_QUERIES = [
    'nri property dispute lawyer india',
    'nri divorce lawyer delhi',
    'power of attorney nri india',
    '498a nri husband defense',
    'nri fir quashing india',
]


def check_perplexity_citation(query: str, domain: str) -> dict:
    """Check if domain is cited in Perplexity's AI answer for a query."""
    if not PERPLEXITY_API_KEY:
        return {'engine': 'perplexity', 'is_cited': False, 'skipped': True,
                'reason': 'PERPLEXITY_API_KEY not set'}
    try:
        r = requests.post(
            'https://api.perplexity.ai/chat/completions',
            headers={
                'Authorization': f'Bearer {PERPLEXITY_API_KEY}',
                'Content-Type': 'application/json',
            },
            json={
                'model': 'sonar',
                'messages': [{'role': 'user', 'content': query}],
                'return_citations': True,
            },
            timeout=30
        )
        if r.status_code != 200:
            print(f'  ⚠️ Perplexity API: HTTP {r.status_code}')
            return {'engine': 'perplexity', 'is_cited': False}

        data        = r.json()
        citations   = data.get('citations', [])
        clean       = domain.lower().replace('www.', '')
        is_cited    = any(clean in str(c).lower() for c in citations)
        citation_url = next((str(c) for c in citations if clean in str(c).lower()), '')
        snippet     = ''
        if data.get('choices'):
            snippet = data['choices'][0].get('message', {}).get('content', '')[:500]

        return {
            'engine':       'perplexity',
            'is_cited':     is_cited,
            'citation_url': citation_url,
            'raw_snippet':  snippet,
            'total_citations': len(citations),
        }
    except Exception as e:
        print(f'  ⚠️ Perplexity error for "{query}": {e}')
        return {'engine': 'perplexity', 'is_cited': False}


def run_llm_visibility(site_domain: str = TARGET_DOMAIN,
                       queries: list[str] = None) -> list[dict]:
    """
    Run LLM citation checks for priority queries.
    Saves results to aeo_results table.
    """
    if not PERPLEXITY_API_KEY:
        print('  ℹ️ PERPLEXITY_API_KEY not set — skipping LLM visibility check')
        print('     Get API key at: perplexity.ai/settings/api')
        return []

    with get_session() as s:
        site = s.query(Site).filter_by(domain=site_domain).first()
        if not site:
            return []
        site_id = site.id

    # Use provided queries or top keywords from DB
    if not queries:
        with get_session() as s:
            kws = (s.query(Keyword)
                   .filter_by(site_id=site_id)
                   .filter(Keyword.priority <= 1)
                   .limit(5).all())
            queries = [kw.keyword for kw in kws] if kws else DEFAULT_QUERIES

    print(f'  Checking {len(queries)} queries in Perplexity...')
    results = []
    today   = date.today()

    for query in queries:
        result = check_perplexity_citation(query, site_domain)
        cited  = '✅ CITED' if result.get('is_cited') else '❌ not cited'
        print(f'    "{query}" → {cited}')

        with get_session() as s:
            existing = s.query(AeoResult).filter_by(
                site_id=site_id, date=today, query=query, engine='perplexity'
            ).first()
            if existing:
                existing.is_cited     = result.get('is_cited', False)
                existing.citation_url = result.get('citation_url', '')
                existing.raw_snippet  = result.get('raw_snippet', '')
            else:
                s.add(AeoResult(
                    site_id=site_id, date=today, query=query,
                    engine='perplexity',
                    is_cited=result.get('is_cited', False),
                    citation_url=result.get('citation_url', ''),
                    raw_snippet=result.get('raw_snippet', ''),
                ))
            s.commit()

        results.append({'query': query, **result})

    cited_count = sum(1 for r in results if r.get('is_cited'))
    print(f'  ✅ Cited in {cited_count}/{len(results)} Perplexity answers')
    return results


if __name__ == '__main__':
    results = run_llm_visibility()
    for r in results:
        print(f'  {r["query"]}: {"CITED" if r["is_cited"] else "not cited"}')
