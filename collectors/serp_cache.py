"""
RankPilot — SERP Result Cache
Uses SQLite as cache (Redis optional — better for production).
Caches SERP results to avoid redundant API/Playwright calls.
Multi-tenant: same keyword checked by multiple tenants = one check.
"""
import os, sys, json, sqlite3
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CACHE_DB   = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'serp_cache.db')
CACHE_TTL  = timedelta(hours=20)   # SERP doesn't change much in 20 hours

def _get_conn():
    conn = sqlite3.connect(CACHE_DB)
    conn.execute('''CREATE TABLE IF NOT EXISTS serp_cache (
        cache_key TEXT PRIMARY KEY,
        result    TEXT,
        cached_at TEXT
    )''')
    conn.commit()
    return conn

def get(keyword: str, domain: str, country: str) -> dict | None:
    """Return cached result if fresh, else None."""
    key = f'{keyword.lower()}::{country.upper()}'   # domain-agnostic cache
    cutoff = (datetime.utcnow() - CACHE_TTL).isoformat()
    try:
        conn = _get_conn()
        row = conn.execute(
            'SELECT result FROM serp_cache WHERE cache_key=? AND cached_at>?',
            (key, cutoff)
        ).fetchone()
        conn.close()
        if row:
            data = json.loads(row[0])
            # Filter result for this specific domain
            full_serp = data.get('full_serp', [])
            for item in full_serp:
                if domain.lower().replace('www.', '') in item.get('url', '').lower():
                    return {'position': item['position'], 'url': item['url'],
                            'serp_features': data.get('serp_features', {}),
                            'from_cache': True}
            return {'position': None, 'url': None,
                    'serp_features': data.get('serp_features', {}),
                    'from_cache': True}
    except:
        pass
    return None

def set(keyword: str, country: str, full_serp: list, serp_features: dict):
    """Cache full SERP (all 100 results) for this keyword × country."""
    key  = f'{keyword.lower()}::{country.upper()}'
    data = json.dumps({'full_serp': full_serp, 'serp_features': serp_features})
    try:
        conn = _get_conn()
        conn.execute('INSERT OR REPLACE INTO serp_cache VALUES (?, ?, ?)',
                     (key, data, datetime.utcnow().isoformat()))
        conn.commit()
        conn.close()
    except:
        pass

def clear_expired():
    """Remove expired entries."""
    cutoff = (datetime.utcnow() - CACHE_TTL).isoformat()
    try:
        conn = _get_conn()
        deleted = conn.execute('DELETE FROM serp_cache WHERE cached_at < ?', (cutoff,)).rowcount
        conn.commit()
        conn.close()
        return deleted
    except:
        return 0

def stats() -> dict:
    try:
        conn = _get_conn()
        total   = conn.execute('SELECT COUNT(*) FROM serp_cache').fetchone()[0]
        cutoff  = (datetime.utcnow() - CACHE_TTL).isoformat()
        fresh   = conn.execute('SELECT COUNT(*) FROM serp_cache WHERE cached_at>?', (cutoff,)).fetchone()[0]
        conn.close()
        return {'total': total, 'fresh': fresh, 'expired': total - fresh}
    except:
        return {}
