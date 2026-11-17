"""
RankPilot — Content Explorer
Semantic search over indexed content. Better than Ahrefs Content Explorer because:
1. Semantic search (finds related content, not just keyword match)
2. Auto content brief generation via Claude API
3. Topic cluster discovery via HDBSCAN
Generic — works for any niche.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import ANTHROPIC_API_KEY

COLLECTION = 'content_pages'

def _qdrant():
    from qdrant_client import QdrantClient
    try:
        client = QdrantClient(host='localhost', port=6333, timeout=5)
        client.get_collections()
        return client
    except:
        return QdrantClient(location=':memory:')

def _embedder():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer('all-MiniLM-L6-v2')

def search(query: str, limit: int = 20, min_word_count: int = 300,
           min_backlinks: int = 0, domains: list = None) -> list[dict]:
    """
    Semantic search over indexed content.
    Returns pages most relevant to the query — even without exact keyword match.

    Example: search("property problems India NRI") finds:
      - articles about "land kabza"
      - articles about "illegal occupation"
      - articles about "encroachment"
      even if those exact words aren't in the query.
    """
    from qdrant_client.models import Filter, FieldCondition, Range, MatchAny

    client  = _qdrant()
    model   = _embedder()
    vector  = model.encode(query).tolist()

    # Build filters
    must_conditions = []
    if min_word_count > 0:
        must_conditions.append(FieldCondition(key='word_count', range=Range(gte=min_word_count)))
    if min_backlinks > 0:
        must_conditions.append(FieldCondition(key='backlink_count', range=Range(gte=min_backlinks)))
    if domains:
        must_conditions.append(FieldCondition(key='domain', match=MatchAny(any=domains)))

    query_filter = Filter(must=must_conditions) if must_conditions else None

    try:
        # Support both old (search) and new (query) Qdrant client APIs
        search_fn = getattr(client, 'query', None) or getattr(client, 'search', None)
        if hasattr(client, 'query'):
            from qdrant_client.models import Query
            raw = client.query(collection_name=COLLECTION, query=vector,
                               query_filter=query_filter, limit=limit, with_payload=True)
            results = [type('R', (), {'payload': r.payload, 'score': r.score})() for r in raw]
        else:
            results = client.search(collection_name=COLLECTION, query_vector=vector,
                                    query_filter=query_filter, limit=limit,
                                    with_payload=True, score_threshold=0.3)
        return [{'url': r.payload['url'],
                 'domain': r.payload.get('domain', ''),
                 'title': r.payload.get('title', ''),
                 'word_count': r.payload.get('word_count', 0),
                 'backlinks': r.payload.get('backlink_count', 0),
                 'has_faq': r.payload.get('has_faq', False),
                 'score': round(r.score, 3),
                 'snippet': r.payload.get('snippet', '')[:300]}
                for r in results]
    except Exception as e:
        print(f'  ⚠️ Qdrant search error: {e}')
        return []

def find_content_gaps(our_domain: str, topic: str, competitor_domains: list = None) -> list[dict]:
    """
    Find topics competitors cover but we don't.
    Works for ANY niche — pure ML, no hardcoded topic knowledge.
    """
    model = _embedder()

    # Get competitor coverage
    comp_results = search(topic, limit=50, domains=competitor_domains)
    our_results  = search(topic, limit=50, domains=[our_domain])

    if not comp_results:
        return []

    # Cluster competitor content by sub-topic
    import numpy as np
    comp_texts   = [f'{r["title"]} {r["snippet"]}' for r in comp_results]
    comp_vectors = model.encode(comp_texts)

    # HDBSCAN clustering — discovers sub-topics automatically
    try:
        from hdbscan import HDBSCAN
        clusterer = HDBSCAN(min_cluster_size=2, min_samples=1, metric='euclidean')
        labels    = clusterer.fit_predict(comp_vectors)
    except:
        # Fallback: simple k-means
        from sklearn.cluster import KMeans
        n_clusters = min(5, len(comp_results) // 2)
        labels = KMeans(n_clusters=max(2, n_clusters), random_state=42).fit_predict(comp_vectors)

    # Get our coverage vectors
    our_texts   = [f'{r["title"]} {r["snippet"]}' for r in our_results]
    our_vectors = model.encode(our_texts) if our_texts else np.zeros((1, 384))

    gaps = []
    unique_labels = set(labels) - {-1}   # -1 = noise in HDBSCAN

    for label in unique_labels:
        cluster_items = [comp_results[i] for i, l in enumerate(labels) if l == label]
        if not cluster_items: continue

        # Find centroid of this cluster
        cluster_vecs = np.array([comp_vectors[i] for i, l in enumerate(labels) if l == label])
        centroid = cluster_vecs.mean(axis=0)

        # Check if we have coverage for this sub-topic
        if len(our_vectors) > 0 and our_vectors.shape[0] > 0:
            from sklearn.metrics.pairwise import cosine_similarity
            our_similarities = cosine_similarity([centroid], our_vectors)[0]
            max_our_similarity = our_similarities.max()
        else:
            max_our_similarity = 0

        # Gap = competitors cover it, we don't
        if max_our_similarity < 0.6:
            # Generate cluster label from most common title words
            all_words = ' '.join(r['title'] for r in cluster_items).lower().split()
            from collections import Counter
            stopwords = {'the', 'a', 'an', 'and', 'or', 'in', 'of', 'to', 'for', 'is', 'are', 'can', 'how'}
            topic_words = [w for w in all_words if w not in stopwords and len(w) > 3]
            if topic_words:
                cluster_topic = Counter(topic_words).most_common(3)
                topic_label = ' '.join(w for w, c in cluster_topic)
            else:
                topic_label = cluster_items[0]['title'][:50]

            gaps.append({
                'gap_topic':     topic_label,
                'our_coverage':  round(max_our_similarity * 100),
                'competitor_pages': len(cluster_items),
                'example_url':   cluster_items[0]['url'],
                'avg_word_count': int(sum(r['word_count'] for r in cluster_items) / len(cluster_items)),
                'recommendation': f'Create content covering: {topic_label}',
            })

    return sorted(gaps, key=lambda x: x['our_coverage'])

def generate_content_brief(keyword: str, top_articles: list[dict] = None) -> str:
    """
    Generate a comprehensive content brief using Claude API.
    Works for any niche — Claude adapts to the topic automatically.
    """
    if not ANTHROPIC_API_KEY:
        return f'[Set ANTHROPIC_API_KEY in .env to generate content briefs]\nKeyword: {keyword}'

    # Get top articles if not provided
    if not top_articles:
        top_articles = search(keyword, limit=10)

    # Build context for Claude
    articles_context = '\n'.join([
        f'{i+1}. Title: {a["title"]}\n   URL: {a["url"]}\n   Words: {a["word_count"]}\n   FAQ: {a["has_faq"]}'
        for i, a in enumerate(top_articles[:10])
    ])

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        message = client.messages.create(
            model='claude-haiku-4-5-20251001',   # cheapest model, sufficient for briefs
            max_tokens=1500,
            messages=[{
                'role': 'user',
                'content': f'''You are an expert SEO content strategist.

Target keyword: "{keyword}"

Here are the top 10 ranking articles for this keyword:
{articles_context}

Generate a comprehensive content brief to outrank all of these. Include:
1. Recommended H1 title (include the target keyword)
2. Meta description (150-160 chars)
3. Recommended word count
4. H2 structure (6-8 sections)
5. Must-cover topics (what all top articles cover + what none cover = your gap)
6. 5 FAQ questions to answer (People Also Ask format)
7. What makes the average competitor article weak (your opportunity)
8. Suggested internal links to include

Be specific and actionable. Format as a structured brief.'''
            }]
        )
        return message.content[0].text
    except Exception as e:
        return f'[Brief generation failed: {e}]\nKeyword: {keyword}'

def discover_topic_clusters(site_domain: str = None) -> list[dict]:
    """
    Automatically discover topic clusters from indexed content.
    No predefined categories. Works for ANY niche.
    Returns list of discovered topic groups with coverage analysis.
    """
    from qdrant_client.models import Filter, FieldCondition, MatchAny
    import numpy as np

    client = _qdrant()

    # Fetch all indexed content
    try:
        results = client.scroll(
            collection_name=COLLECTION,
            limit=1000,
            with_vectors=True,
            with_payload=True
        )
        points = results[0]
    except Exception as e:
        print(f'  ⚠️ Qdrant scroll error: {e}')
        return []

    if len(points) < 10:
        return []

    vectors = np.array([p.vector for p in points])
    payloads = [p.payload for p in points]

    # HDBSCAN discovers natural topic clusters
    try:
        from hdbscan import HDBSCAN
        clusterer = HDBSCAN(min_cluster_size=3, min_samples=2)
        labels    = clusterer.fit_predict(vectors)
    except:
        from sklearn.cluster import KMeans
        n = min(20, len(points) // 5)
        labels = KMeans(n_clusters=max(3, n), random_state=42).fit_predict(vectors)

    clusters = []
    for label in set(labels) - {-1}:
        items = [payloads[i] for i, l in enumerate(labels) if l == label]
        domains_in_cluster = set(p.get('domain', '') for p in items)

        # Topic label from most common title words
        all_words = ' '.join(p.get('title', '') for p in items).lower().split()
        stopwords = {'the', 'a', 'an', 'and', 'or', 'in', 'of', 'to', 'for', 'is', 'are', 'can'}
        topic_words = [w for w in all_words if w not in stopwords and len(w) > 3]
        from collections import Counter
        label_words = Counter(topic_words).most_common(4)
        topic_label = ' '.join(w for w, c in label_words) if label_words else f'topic_{label}'

        our_coverage = (site_domain in domains_in_cluster) if site_domain else None

        clusters.append({
            'topic':        topic_label,
            'page_count':   len(items),
            'domains':      list(domains_in_cluster),
            'we_cover':     our_coverage,
            'avg_words':    int(sum(p.get('word_count', 0) for p in items) / len(items)),
            'example_url':  items[0].get('url', '') if items else '',
        })

    return sorted(clusters, key=lambda x: -x['page_count'])

if __name__ == '__main__':
    # Test semantic search
    print('=== Semantic Content Search Test ===')
    results = search('NRI property problems India', limit=5)
    if results:
        for r in results:
            print(f'  [{r["score"]:.2f}] {r["title"][:60]} — {r["domain"]}')
    else:
        print('  No content indexed yet. Run: python analysis/content_indexer.py')

    print('\n=== Topic Cluster Discovery ===')
    clusters = discover_topic_clusters()
    if clusters:
        for c in clusters[:5]:
            print(f'  [{c["page_count"]} pages] {c["topic"]} — {", ".join(list(c["domains"])[:3])}')
    else:
        print('  No clusters yet. Index more content first.')
