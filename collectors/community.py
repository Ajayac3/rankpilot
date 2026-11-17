"""
RankPilot — Community Monitor
Scans Reddit for NRI legal questions that are answer opportunities.
"""
import os, sys, requests
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT, NRI_SUBREDDITS, TARGET_DOMAIN
from core.db import get_session, Mention, Site

LEGAL_KEYWORDS = [
    'property', 'lawyer', 'legal', 'court', 'police', 'nri', 'inheritance',
    'divorce', '498a', 'bail', 'passport', 'oci', 'poa', 'power of attorney',
    'proclaimed', 'fir', 'kabza', 'partition', 'advocate', 'suit', 'judgment'
]

def is_answer_opportunity(title: str) -> bool:
    """Is this post a question we could answer?"""
    t = title.lower()
    is_question = t.endswith('?') or any(t.startswith(w) for w in
                  ['what', 'how', 'can', 'is', 'are', 'when', 'why', 'where',
                   'should', 'need', 'help', 'advice', 'anyone'])
    has_legal = any(kw in t for kw in LEGAL_KEYWORDS)
    return is_question and has_legal

def scan_reddit(limit_per_sub: int = 25) -> list[dict]:
    """Scan NRI subreddits for legal questions."""
    if not REDDIT_CLIENT_ID:
        # Fallback: use Reddit's public JSON API (no auth needed, limited)
        return scan_reddit_public(limit_per_sub)

    try:
        import praw
        reddit = praw.Reddit(
            client_id=REDDIT_CLIENT_ID,
            client_secret=REDDIT_CLIENT_SECRET,
            user_agent=REDDIT_USER_AGENT
        )
        results = []
        for sub_name in NRI_SUBREDDITS:
            try:
                subreddit = reddit.subreddit(sub_name)
                for post in subreddit.new(limit=limit_per_sub):
                    title = post.title.strip()
                    if any(kw in title.lower() for kw in LEGAL_KEYWORDS):
                        results.append({
                            'platform': f'reddit',
                            'source_url': f'https://reddit.com{post.permalink}',
                            'title': title[:200],
                            'snippet': (post.selftext or '')[:500],
                            'score': post.score,
                            'subreddit': sub_name,
                            'has_question': is_answer_opportunity(title),
                            'created_utc': post.created_utc
                        })
            except Exception as e:
                print(f'    ⚠️ r/{sub_name}: {e}')
        return results
    except Exception as e:
        print(f'  ⚠️ Reddit (praw): {e}')
        return scan_reddit_public(limit_per_sub)

def scan_reddit_public(limit_per_sub: int = 10) -> list[dict]:
    """Use Reddit's public JSON endpoint (no auth)."""
    results = []
    headers = {'User-Agent': REDDIT_USER_AGENT}

    for sub_name in NRI_SUBREDDITS[:5]:
        try:
            url = f'https://www.reddit.com/r/{sub_name}/new.json'
            r = requests.get(url, headers=headers, params={'limit': limit_per_sub}, timeout=10)
            if r.status_code != 200:
                continue
            posts = r.json().get('data', {}).get('children', [])
            for post_data in posts:
                post = post_data['data']
                title = post.get('title', '').strip()
                if any(kw in title.lower() for kw in LEGAL_KEYWORDS):
                    results.append({
                        'platform': 'reddit',
                        'source_url': f'https://reddit.com{post.get("permalink", "")}',
                        'title': title[:200],
                        'snippet': (post.get('selftext', '') or '')[:500],
                        'score': post.get('score', 0),
                        'subreddit': sub_name,
                        'has_question': is_answer_opportunity(title),
                        'created_utc': post.get('created_utc', 0)
                    })
        except Exception as e:
            print(f'    ⚠️ r/{sub_name} public: {e}')

    return results

def run_community_monitor(site_domain: str = TARGET_DOMAIN) -> list[dict]:
    """Scan communities, save new mentions, return answer opportunities."""
    with get_session() as s:
        site = s.query(Site).filter_by(domain=site_domain).first()
        if not site:
            return []
        existing_urls = {m.source_url for m in s.query(Mention).filter_by(site_id=site.id).all()}

    print('  Scanning Reddit for NRI legal questions...')
    posts = scan_reddit(limit_per_sub=25)
    print(f'    Found {len(posts)} relevant posts')

    new_mentions = []
    answer_opportunities = []

    with get_session() as s:
        site = s.query(Site).filter_by(domain=site_domain).first()
        for post in posts:
            if post['source_url'] in existing_urls:
                continue
            mention = Mention(
                site_id=site.id,
                platform='reddit',
                source_url=post['source_url'],
                title=post.get('title', ''),
                snippet=post.get('snippet', ''),
                target='opportunity',
                sentiment='neutral',
                has_question=post.get('has_question', False),
                is_answered=False,
                discovered_at=datetime.now(timezone.utc)
            )
            s.add(mention)
            new_mentions.append(post)
            if post.get('has_question'):
                answer_opportunities.append(post)
        s.commit()

    print(f'    {len(answer_opportunities)} answer opportunities found')
    return answer_opportunities

if __name__ == '__main__':
    opps = run_community_monitor()
    print(f'\nAnswer Opportunities ({len(opps)}):')
    for opp in opps[:5]:
        print(f'  [{opp["subreddit"]}] {opp["title"][:80]}')
        print(f'    {opp["source_url"]}')
