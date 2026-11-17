"""
RankPilot — AI Intent Classifier (DeepSeek)
Classifies keyword intent in batches of 20.
Falls back to rule-based classifier if DEEPSEEK_API_KEY not set.
Intent labels: commercial / near-commercial / informational / navigational
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

COMMERCIAL_SIGNALS = ['lawyer', 'advocate', 'legal help', 'legal services', 'consult',
                      'hire', 'attorney', 'legal advice', 'legal assistance', 'law firm']
NEAR_COMMERCIAL    = ['property', 'dispute', 'inheritance', 'divorce', '498a', 'bail',
                      'fir', 'passport', 'oci', 'power of attorney', 'proclaimed',
                      'look out', 'kabza', 'partition', 'sell property', 'rent', 'eviction']


def _rule_based(query: str) -> str:
    q = query.lower()
    if any(s in q for s in COMMERCIAL_SIGNALS):
        return 'commercial'
    if 'nri' in q and any(s in q for s in NEAR_COMMERCIAL):
        return 'near-commercial'
    if q.startswith(('how', 'what', 'can', 'when', 'why', 'who', 'which', 'is ', 'are ')):
        return 'informational'
    return 'informational'


def classify_batch(keywords: list[str]) -> dict[str, str]:
    """
    Classify intent for a list of keywords using DeepSeek.
    Returns {keyword: intent_label}. Falls back to rule-based if no API key.
    """
    from utils.deepseek import chat, is_available
    if not is_available() or not keywords:
        return {kw: _rule_based(kw) for kw in keywords}

    results = {}
    for i in range(0, len(keywords), 20):
        batch = keywords[i:i + 20]
        batch_str = '\n'.join(f'{j+1}. {kw}' for j, kw in enumerate(batch))
        prompt = (
            'Classify each search query intent for an NRI (Non-Resident Indian) legal services firm.\n'
            'Intent options:\n'
            '  commercial     — person is ready to hire a lawyer\n'
            '  near-commercial — person has a legal problem, likely needs a lawyer soon\n'
            '  informational  — person is learning about a legal topic\n'
            '  navigational   — person is searching for a specific website or brand\n\n'
            f'Queries:\n{batch_str}\n\n'
            'Respond with ONLY a JSON object: {"1": "commercial", "2": "informational", ...}'
        )
        response = chat(prompt, max_tokens=150, temperature=0.1)
        if response:
            try:
                raw = json.loads(response)
                for k, v in raw.items():
                    idx = int(k) - 1
                    if 0 <= idx < len(batch):
                        results[batch[idx]] = v
            except Exception:
                pass

    # Fill any missed keywords with rule-based
    for kw in keywords:
        if kw not in results:
            results[kw] = _rule_based(kw)

    return results


def classify_and_save(site_id: int, limit: int = 200):
    """Backfill intent on gsc_queries and keyword_opportunities where intent is NULL."""
    from core.db import get_session, GscQuery, KeywordOpportunity

    with get_session() as s:
        gsc_nulls = (s.query(GscQuery)
                     .filter_by(site_id=site_id)
                     .filter(GscQuery.intent == None)
                     .limit(limit).all())
        opp_nulls = (s.query(KeywordOpportunity)
                     .filter_by(site_id=site_id)
                     .filter(KeywordOpportunity.intent == None)
                     .limit(limit).all())

    if not gsc_nulls and not opp_nulls:
        print('  ✅ All keywords already classified')
        return

    all_kws = [q.query for q in gsc_nulls] + [o.keyword for o in opp_nulls]
    print(f'  Classifying {len(all_kws)} keywords with DeepSeek...')
    classifications = classify_batch(all_kws)

    with get_session() as s:
        for q in gsc_nulls:
            obj = s.query(GscQuery).get(q.id)
            if obj:
                obj.intent = classifications.get(q.query, 'informational')
        for o in opp_nulls:
            obj = s.query(KeywordOpportunity).get(o.id)
            if obj:
                obj.intent = classifications.get(o.keyword, 'informational')
        s.commit()

    print(f'  ✅ Classified {len(classifications)} keywords')


if __name__ == '__main__':
    test = ['nri property lawyer india', 'how to file fir against nri husband',
            'example legal firm delhi', 'can nri sell property in india']
    results = classify_batch(test)
    for kw, intent in results.items():
        print(f'  {intent:20s} {kw}')
