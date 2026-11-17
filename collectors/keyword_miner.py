"""
RankPilot — Keyword Discovery Engine
Finds keywords that potential clients search where our site is INVISIBLE.
Sources: Google autocomplete, YouTube autocomplete, Bing autocomplete, Reddit questions.
"""
import os, sys, time, json, requests
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT, NRI_SUBREDDITS
from core.db import get_session, KeywordOpportunity, Site
from utils.logger import get_logger
log = get_logger(__name__)

HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; RankPilotBot/0.1)'}

SEED_MODIFIERS = [
    'nri lawyer', 'nri property lawyer', 'nri legal help', 'nri legal services',
    'nri property dispute', 'nri criminal lawyer', 'nri divorce lawyer',
    'power of attorney nri', '498a nri', 'nri inheritance', 'nri passport',
    'nri oci card', 'nri fir quashing', 'nri anticipatory bail',
    'nri proclaimed offender', 'nri look out circular', 'nri kabza',
]

COMMERCIAL_SIGNALS = [
    'lawyer', 'advocate', 'legal help', 'legal services', 'consult',
    'hire', 'attorney', 'legal advice', 'legal assistance', 'law firm'
]
NEAR_COMMERCIAL = [
    'property', 'dispute', 'inheritance', 'divorce', '498a', 'bail',
    'fir', 'passport', 'oci', 'power of attorney', 'proclaimed',
    'look out', 'kabza', 'partition', 'sell property', 'rent', 'eviction'
]

def classify_intent(query: str) -> str:
    q = query.lower()
    if any(s in q for s in COMMERCIAL_SIGNALS):
        return 'commercial'
    if 'nri' in q and any(s in q for s in NEAR_COMMERCIAL):
        return 'near-commercial'
    if q.startswith(('how', 'what', 'can', 'when', 'why', 'who', 'which', 'is ', 'are ')):
        return 'informational'
    return 'informational'

# ── Google Autocomplete ────────────────────────────────────────────────────────
def google_autocomplete(query: str, country: str = 'in') -> list[str]:
    """Fetch Google autocomplete suggestions (free, no key)."""
    url = 'https://suggestqueries.google.com/complete/search'
    params = {'client': 'firefox', 'q': query, 'hl': 'en', 'gl': country}
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            data = r.json()
            return data[1] if len(data) > 1 else []
    except:
        pass
    return []

def expand_with_autocomplete(seeds: list[str], countries: list[str] = None) -> list[dict]:
    """Expand seed keywords using Google autocomplete."""
    countries = countries or ['in', 'us', 'gb', 'ca', 'ae']
    discovered = {}

    for seed in seeds:
        # Expand with alphabet (a-z suffix)
        for char in 'abcdefghijklmnopqrstuvwxyz':
            query = f'{seed} {char}'
            suggestions = google_autocomplete(query, 'in')
            for sug in suggestions:
                sug = sug.strip().lower()
                if len(sug) > 5 and sug not in discovered:
                    discovered[sug] = {'source': 'google_autocomplete', 'country': 'IN'}
            time.sleep(0.2)

        # Check in target countries
        for country_code in countries:
            suggestions = google_autocomplete(seed, country_code)
            for sug in suggestions:
                sug = sug.strip().lower()
                if sug not in discovered:
                    discovered[sug] = {
                        'source': f'google_autocomplete_{country_code}',
                        'country': country_code.upper()
                    }
            time.sleep(0.15)

    return [{'keyword': kw, **meta} for kw, meta in discovered.items()]

# ── YouTube Autocomplete ───────────────────────────────────────────────────────
def youtube_autocomplete(query: str) -> list[str]:
    """YouTube search suggestions — people also search for NRI legal videos."""
    url = 'https://suggestqueries-clients6.youtube.com/complete/search'
    params = {'client': 'youtube', 'q': query, 'ds': 'yt', 'hl': 'en'}
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            data = json.loads(r.text.lstrip('window.google.ac.h(').rstrip(')'))
            if len(data) > 1:
                return [item[0] for item in data[1]]
    except:
        pass
    return []

# ── Bing Autocomplete ─────────────────────────────────────────────────────────
def bing_autocomplete(query: str) -> list[str]:
    """Bing autocomplete suggestions."""
    url = 'https://api.bing.com/qsonhs.aspx'
    params = {'q': query, 'mkt': 'en-IN'}
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            data = r.json()
            results = data.get('AS', {}).get('Results', [])
            suggestions = []
            for section in results:
                for item in section.get('Suggests', []):
                    suggestions.append(item.get('Txt', ''))
            return suggestions
    except:
        pass
    return []

# ── Reddit Question Mining ────────────────────────────────────────────────────
def mine_reddit_questions(subreddits: list[str] = None, limit: int = 100) -> list[dict]:
    """Mine Reddit for NRI legal questions."""
    subreddits = subreddits or NRI_SUBREDDITS
    questions = []

    if not REDDIT_CLIENT_ID or not REDDIT_CLIENT_SECRET:
        print('  ⚠️ Reddit API keys not set. Add REDDIT_CLIENT_ID + REDDIT_CLIENT_SECRET to .env')
        return questions

    try:
        import praw
        reddit = praw.Reddit(
            client_id=REDDIT_CLIENT_ID,
            client_secret=REDDIT_CLIENT_SECRET,
            user_agent=REDDIT_USER_AGENT
        )
        for sub_name in subreddits[:5]:   # limit to 5 subreddits
            try:
                subreddit = reddit.subreddit(sub_name)
                for post in subreddit.search('india legal', sort='new', limit=limit//5):
                    title = post.title.strip()
                    if any(word in title.lower() for word in
                           ['property', 'lawyer', 'legal', 'nri', 'court', 'police',
                            'inheritance', 'divorce', '498', 'bail', 'passport', 'oci']):
                        questions.append({
                            'keyword': title[:100],
                            'source': f'reddit_r/{sub_name}',
                            'url': f'https://reddit.com{post.permalink}',
                            'score': post.score,
                            'country': 'US'
                        })
                time.sleep(1)
            except Exception as e:
                print(f'  ⚠️ Reddit r/{sub_name}: {e}')
    except ImportError:
        print('  ⚠️ praw not installed: pip install praw')
    except Exception as e:
        print(f'  ⚠️ Reddit error: {e}')

    return questions

# ── Competitor URL Slug Mining ────────────────────────────────────────────────
def mine_competitor_slugs() -> list[dict]:
    """Extract keywords from competitor URL slugs."""
    from core.db import CompetitorUrl, Competitor
    keywords = []

    with get_session() as s:
        comp_urls = (s.query(CompetitorUrl.url, Competitor.domain)
                     .join(Competitor)
                     .all())

    for url, domain in comp_urls:
        # Extract slug: /nri-property-dispute-lawyer-usa/ → "nri property dispute lawyer usa"
        slug = url.rstrip('/').split('/')[-1]
        keyword = slug.replace('-', ' ').replace('_', ' ').strip()
        if len(keyword) > 5 and 'nri' in keyword.lower():
            keywords.append({
                'keyword': keyword,
                'source': f'competitor_slug_{domain}',
                'country': 'IN'
            })

    return keywords

# ── Main Discovery Run ────────────────────────────────────────────────────────
def run_keyword_discovery(site_domain: str, save_to_db: bool = True) -> list[dict]:
    """
    Full keyword discovery pipeline.
    Returns list of new opportunities not already in DB.
    """
    with get_session() as s:
        site = s.query(Site).filter_by(domain=site_domain).first()
        if not site:
            print(f'Site {site_domain} not found'); return []
        existing = {r.keyword.lower() for r in
                    s.query(KeywordOpportunity).filter_by(site_id=site.id).all()}

    all_discovered = []

    print('  Mining Google autocomplete...')
    ac_results = expand_with_autocomplete(SEED_MODIFIERS[:5])  # limit in Phase 1
    all_discovered.extend(ac_results)
    print(f'    Found {len(ac_results)} autocomplete suggestions')

    print('  Mining YouTube autocomplete...')
    for seed in SEED_MODIFIERS[:5]:
        for sug in youtube_autocomplete(seed):
            sug = sug.strip().lower()
            if sug and len(sug) > 5:
                all_discovered.append({'keyword': sug, 'source': 'youtube_autocomplete', 'country': 'IN'})
        time.sleep(0.3)

    print('  Mining competitor URL slugs...')
    slug_results = mine_competitor_slugs()
    all_discovered.extend(slug_results)
    print(f'    Found {len(slug_results)} slug-based keywords')

    print('  Mining Reddit questions...')
    reddit_results = mine_reddit_questions(limit=50)
    all_discovered.extend(reddit_results)
    print(f'    Found {len(reddit_results)} Reddit questions')

    # Deduplicate + filter
    seen = set()
    new_opportunities = []
    for item in all_discovered:
        kw = item['keyword'].lower().strip()
        if kw in seen or kw in existing or len(kw) < 5:
            continue
        seen.add(kw)
        intent = classify_intent(kw)
        if intent in ('commercial', 'near-commercial'):
            new_opportunities.append({
                'keyword': kw,
                'source': item.get('source', 'unknown'),
                'country': item.get('country', 'IN'),
                'intent': intent
            })

    print(f'\n  ✅ {len(new_opportunities)} new commercial/near-commercial keyword opportunities found')

    if save_to_db:
        with get_session() as s:
            for opp in new_opportunities:
                s.add(KeywordOpportunity(
                    site_id=site.id,
                    keyword=opp['keyword'],
                    source=opp['source'],
                    country=opp['country'],
                    intent=opp['intent'],
                    visibility='invisible',
                    discovered_at=date.today()
                ))
            s.commit()
        print(f'  Saved to keyword_opportunities table')

    return new_opportunities

if __name__ == '__main__':
    from core.config import TARGET_DOMAIN
    results = run_keyword_discovery(TARGET_DOMAIN, save_to_db=False)
    print('\nTop 20 discovered keywords:')
    for kw in results[:20]:
        print(f'  [{kw["intent"]}] {kw["keyword"]} ({kw["source"]})')
