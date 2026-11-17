"""
RankPilot — Content Indexer
Builds a semantic content index from competitor pages + SERP results.
Stores in Qdrant (vector DB) for instant semantic search.
Generic — works for any niche.
"""
import os, sys, hashlib, requests, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import TARGET_DOMAIN

HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; RankPilotBot/0.1)'}
COLLECTION = 'content_pages'

def _qdrant():
    from qdrant_client import QdrantClient
    # Try local Qdrant first (Docker/binary), fall back to in-memory
    try:
        client = QdrantClient(host='localhost', port=6333, timeout=5)
        client.get_collections()   # test connection
        return client
    except:
        # In-memory mode for local development (no Docker needed)
        return QdrantClient(location=':memory:')

def _embedder():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer('all-MiniLM-L6-v2')

def init_collection():
    """Create Qdrant collection if it doesn't exist."""
    from qdrant_client.models import Distance, VectorParams
    client = _qdrant()
    existing = [c.name for c in client.get_collections().collections]
    if COLLECTION not in existing:
        client.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=384, distance=Distance.COSINE)
        )
        print(f'  ✅ Qdrant collection "{COLLECTION}" created')
    return client

def extract_page_content(url: str) -> dict:
    """Fetch a page and extract its key content fields."""
    try:
        from bs4 import BeautifulSoup
        r = requests.get(url, headers=HEADERS, timeout=12, allow_redirects=True)
        if r.status_code != 200:
            return {}
        soup = BeautifulSoup(r.text, 'html.parser')

        # Remove noise
        for tag in soup.find_all(['nav', 'header', 'footer', 'script', 'style', 'aside', 'ads']):
            tag.decompose()

        title = (soup.find('title') or soup.new_tag('')).get_text(strip=True)[:200]
        h1    = (soup.find('h1')    or soup.new_tag('')).get_text(strip=True)[:200]
        meta_desc = ''
        meta = soup.find('meta', attrs={'name': 'description'})
        if meta: meta_desc = meta.get('content', '')[:300]

        # Main content text
        main = soup.find('main') or soup.find('article') or soup.find(id='main-content') or soup.find('body')
        content_text = main.get_text(separator=' ', strip=True)[:5000] if main else ''
        word_count   = len(content_text.split())

        # Count quality signals
        h2_count  = len(soup.find_all('h2'))
        h3_count  = len(soup.find_all('h3'))
        faq       = bool(soup.find(string=lambda t: t and 'faq' in t.lower()))
        has_table = bool(soup.find('table'))

        # Schema
        schemas = [s.get_text() for s in soup.find_all('script', type='application/ld+json')]
        schema_types = []
        import re
        for s in schemas:
            matches = re.findall(r'"@type"\s*:\s*"([^"]+)"', s)
            schema_types.extend(matches)

        # Content to embed (title + H1 + first 500 chars of main content)
        embed_text = f'{title} {h1} {content_text[:500]}'

        return {
            'url': url,
            'domain': url.split('/')[2].replace('www.', ''),
            'title': title,
            'h1': h1,
            'meta_description': meta_desc,
            'word_count': word_count,
            'h2_count': h2_count,
            'h3_count': h3_count,
            'has_faq': faq,
            'has_table': has_table,
            'schema_types': schema_types,
            'content_snippet': content_text[:1000],
            'embed_text': embed_text,
            'content_hash': hashlib.md5(content_text.encode()).hexdigest()
        }
    except Exception as e:
        return {'url': url, 'error': str(e)}

def index_pages(pages: list[dict], source_label: str = 'competitor'):
    """
    Index a list of pages into Qdrant.
    pages = [{'url': ..., 'title': ..., 'word_count': ..., ...}]
    """
    from qdrant_client.models import PointStruct
    client  = init_collection()
    model   = _embedder()
    indexed = 0

    # Check existing IDs to avoid duplicates
    try:
        existing_count = client.count(collection_name=COLLECTION).count
    except:
        existing_count = 0

    batch_size = 50
    valid_pages = [p for p in pages if p.get('embed_text') or p.get('title')]

    for i in range(0, len(valid_pages), batch_size):
        batch = valid_pages[i:i+batch_size]
        texts  = [p.get('embed_text', p.get('title', '')) for p in batch]
        vectors = model.encode(texts).tolist()

        points = []
        for j, (page, vector) in enumerate(zip(batch, vectors)):
            uid = int(hashlib.md5(page['url'].encode()).hexdigest()[:8], 16)
            points.append(PointStruct(
                id=uid,
                vector=vector,
                payload={
                    'url':          page.get('url', ''),
                    'domain':       page.get('domain', ''),
                    'title':        page.get('title', ''),
                    'h1':           page.get('h1', ''),
                    'word_count':   page.get('word_count', 0),
                    'h2_count':     page.get('h2_count', 0),
                    'has_faq':      page.get('has_faq', False),
                    'has_table':    page.get('has_table', False),
                    'schema_types': page.get('schema_types', []),
                    'backlink_count': page.get('backlink_count', 0),
                    'source':       source_label,
                    'snippet':      page.get('content_snippet', '')[:500],
                }
            ))

        try:
            client.upsert(collection_name=COLLECTION, points=points, wait=True)
            indexed += len(points)
        except Exception as e:
            print(f'    ⚠️ Qdrant upsert error: {e}')

    print(f'  ✅ Indexed {indexed} pages into Qdrant (total: {existing_count + indexed})')
    return indexed

def index_competitor_pages(site_domain: str = TARGET_DOMAIN) -> int:
    """Fetch + index all competitor pages from the DB."""
    from core.db import get_session, Site, Competitor, CompetitorUrl

    with get_session() as s:
        site = s.query(Site).filter_by(domain=site_domain).first()
        if not site: return 0
        comp_urls = (s.query(CompetitorUrl.url, CompetitorUrl.title)
                     .join(Competitor)
                     .filter(Competitor.site_id == site.id)
                     .all())

    print(f'  Indexing {len(comp_urls)} competitor pages...')
    pages = []
    for url, title in comp_urls[:500]:   # limit to 500 in Phase 1
        if not url.endswith('.xml') and not url.endswith('.pdf'):
            content = extract_page_content(url)
            if content.get('word_count', 0) > 100:
                pages.append(content)
            time.sleep(0.3)

    return index_pages(pages, source_label='competitor')

def index_serp_pages(keyword: str, country: str = 'IN') -> int:
    """Fetch + index top 10 SERP pages for a keyword."""
    from collectors.rank_tracker import get_top10_urls
    urls = get_top10_urls(keyword, country)
    pages = []
    for url in urls:
        content = extract_page_content(url)
        if content.get('word_count', 0) > 100:
            content['keyword'] = keyword
            pages.append(content)
        time.sleep(0.5)
    return index_pages(pages, source_label=f'serp:{keyword}')

if __name__ == '__main__':
    init_collection()
    # Quick test: index a few pages
    test_pages = [
        extract_page_content('https://nrilegalservices.com/nri-property-dispute/'),
        extract_page_content('https://legalhelpnri.com/property/'),
    ]
    valid = [p for p in test_pages if p.get('word_count', 0) > 100]
    if valid:
        indexed = index_pages(valid)
        print(f'Test: indexed {indexed} pages')
