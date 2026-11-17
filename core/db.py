"""
RankPilot — SQLite database schema + helpers.
Phase 1: SQLite (localhost). Phase 2: swap to PostgreSQL (Supabase).
"""
import os
from datetime import date, datetime
from sqlalchemy import (
    create_engine, Column, Integer, Float, String, Text,
    Date, DateTime, Boolean, JSON, ForeignKey, UniqueConstraint,
    func
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH  = os.path.join(BASE_DIR, 'data', 'rankpilot.db')
engine   = create_engine(f'sqlite:///{DB_PATH}', echo=False)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


# ── Sites ─────────────────────────────────────────────────────────────────────
class Site(Base):
    __tablename__ = 'sites'
    id          = Column(Integer, primary_key=True)
    domain      = Column(String, unique=True, nullable=False)   # example-legal.in
    gsc_property = Column(String)                                # https://example-legal.in/
    ga4_property = Column(String)                                # numeric GA4 property ID
    yt_channel   = Column(String)
    created_at  = Column(DateTime, default=datetime.utcnow)


# ── Keywords ──────────────────────────────────────────────────────────────────
class Keyword(Base):
    __tablename__ = 'keywords'
    id       = Column(Integer, primary_key=True)
    site_id  = Column(Integer, ForeignKey('sites.id'), nullable=False)
    keyword  = Column(String, nullable=False)
    country  = Column(String(2), default='IN')   # ISO 2-letter
    language = Column(String(5), default='en')
    cluster  = Column(String)                     # e.g. "property_dispute"
    intent   = Column(String)                     # commercial/informational/navigational
    priority = Column(Integer, default=50)        # 1=highest
    is_seed  = Column(Boolean, default=True)
    volume   = Column(Integer)                    # estimated monthly search volume
    __table_args__ = (UniqueConstraint('site_id', 'keyword', 'country'),)


# ── Rankings ──────────────────────────────────────────────────────────────────
class Ranking(Base):
    __tablename__ = 'rankings'
    id                  = Column(Integer, primary_key=True)
    keyword_id          = Column(Integer, ForeignKey('keywords.id'), nullable=False)
    date                = Column(Date, nullable=False, default=date.today)
    position            = Column(Integer)       # None = not in top 100
    url                 = Column(String)        # which URL of ours ranked
    serp_features       = Column(JSON)          # {"featured_snippet": false, "paa": true, ...}
    ai_overview_present = Column(Boolean, default=False)  # AI Overview exists for this query
    ai_cited            = Column(Boolean, default=False)  # our domain cited in AI Overview


# ── GSC Data ──────────────────────────────────────────────────────────────────
class GscQuery(Base):
    __tablename__ = 'gsc_queries'
    id          = Column(Integer, primary_key=True)
    site_id     = Column(Integer, ForeignKey('sites.id'), nullable=False)
    date        = Column(Date, nullable=False)
    query       = Column(String, nullable=False)
    country     = Column(String(2))
    device      = Column(String)
    page        = Column(String)
    impressions = Column(Integer, default=0)
    clicks      = Column(Integer, default=0)
    position    = Column(Float)
    intent      = Column(String)         # auto-classified
    # 1 = this row is a single day. 7 = a rolling 7-day total stored against its end
    # date, which is what every row written before 2026-09-01 holds. Summing those
    # across dates counts each day up to 7 times; filter window_days == 1 for any
    # total over a date range.
    window_days = Column(Integer, default=1)
    __table_args__ = (UniqueConstraint('site_id', 'date', 'query', 'country', 'device'),)


class GscPage(Base):
    __tablename__ = 'gsc_pages'
    id          = Column(Integer, primary_key=True)
    site_id     = Column(Integer, ForeignKey('sites.id'), nullable=False)
    date        = Column(Date, nullable=False)
    page        = Column(String, nullable=False)
    impressions = Column(Integer, default=0)
    clicks      = Column(Integer, default=0)
    position    = Column(Float)
    window_days = Column(Integer, default=1)   # see GscQuery.window_days
    __table_args__ = (UniqueConstraint('site_id', 'date', 'page'),)


# ── GA4 Data ──────────────────────────────────────────────────────────────────
class Ga4Session(Base):
    __tablename__ = 'ga4_sessions'
    id          = Column(Integer, primary_key=True)
    site_id     = Column(Integer, ForeignKey('sites.id'), nullable=False)
    date        = Column(Date, nullable=False)
    channel     = Column(String)
    country     = Column(String(2))
    sessions    = Column(Integer, default=0)
    conversions = Column(Integer, default=0)  # contact_form_submit + whatsapp_click + phone_click
    events      = Column(JSON)                # {"contact_form_submit": 3, "whatsapp_click": 12}
    # See GscQuery.window_days. Rows written before 2026-09-01 hold a rolling
    # 7-day total stamped with the run date, and carry the whole site's
    # conversions on every channel row — filter window_days == 1 to sum either.
    window_days = Column(Integer, default=1)


# ── Competitors ───────────────────────────────────────────────────────────────
class Competitor(Base):
    __tablename__ = 'competitors'
    id          = Column(Integer, primary_key=True)
    site_id     = Column(Integer, ForeignKey('sites.id'), nullable=False)
    domain      = Column(String, nullable=False)
    sitemap_url = Column(String)
    yt_channel  = Column(String)


class CompetitorUrl(Base):
    __tablename__ = 'competitor_urls'
    id              = Column(Integer, primary_key=True)
    competitor_id   = Column(Integer, ForeignKey('competitors.id'), nullable=False)
    url             = Column(String, nullable=False)
    title           = Column(String)
    first_seen      = Column(Date, default=date.today)
    last_seen       = Column(Date, default=date.today)
    content_hash    = Column(String)
    is_new          = Column(Boolean, default=True)   # flagged for first 7 days
    __table_args__  = (UniqueConstraint('competitor_id', 'url'),)


# ── Backlinks ─────────────────────────────────────────────────────────────────
class Backlink(Base):
    __tablename__ = 'backlinks'
    id          = Column(Integer, primary_key=True)
    site_id     = Column(Integer, ForeignKey('sites.id'), nullable=False)
    source_url  = Column(String, nullable=False)
    target_url  = Column(String)
    anchor_text = Column(String)
    source_domain = Column(String)
    first_seen  = Column(Date, default=date.today)
    last_seen   = Column(Date, default=date.today)
    status      = Column(String, default='live')     # live / lost
    __table_args__ = (UniqueConstraint('site_id', 'source_url', 'target_url'),)


# ── Keyword Opportunities ─────────────────────────────────────────────────────
class KeywordOpportunity(Base):
    __tablename__ = 'keyword_opportunities'
    id              = Column(Integer, primary_key=True)
    site_id         = Column(Integer, ForeignKey('sites.id'), nullable=False)
    keyword         = Column(String, nullable=False)
    source          = Column(String)         # autocomplete/paa/reddit/competitor/etc
    country         = Column(String(2), default='IN')
    est_volume      = Column(Integer)        # monthly search volume estimate
    kd_score        = Column(Integer)        # keyword difficulty 0-100
    intent          = Column(String)         # commercial/informational/etc
    visibility      = Column(String)         # invisible/near-invisible/striking/ranking
    competitor_ranks = Column(JSON)          # {"lawcrust.com": 3, "nrilegalservices.com": 1}
    status          = Column(String, default='new')   # new/reviewing/brief/published/dismissed
    discovered_at   = Column(Date, default=date.today)
    __table_args__ = (UniqueConstraint('site_id', 'keyword', 'country'),)


# ── Community Mentions ────────────────────────────────────────────────────────
class Mention(Base):
    __tablename__ = 'mentions'
    id           = Column(Integer, primary_key=True)
    site_id      = Column(Integer, ForeignKey('sites.id'), nullable=False)
    platform     = Column(String)        # reddit/quora/web
    source_url   = Column(String)
    title        = Column(String)
    snippet      = Column(Text)
    target       = Column(String)        # 'own' or competitor domain
    sentiment    = Column(String)        # positive/neutral/negative
    has_question = Column(Boolean, default=False)
    is_answered  = Column(Boolean, default=False)
    discovered_at = Column(DateTime, default=datetime.utcnow)


# ── Audit Issues ──────────────────────────────────────────────────────────────
class AuditIssue(Base):
    __tablename__ = 'audit_issues'
    id           = Column(Integer, primary_key=True)
    site_id      = Column(Integer, ForeignKey('sites.id'), nullable=False)
    detected_at  = Column(DateTime, default=datetime.utcnow)
    page_url     = Column(String)
    issue_type   = Column(String)        # missing_meta/broken_link/missing_schema/eeat/etc
    severity     = Column(String)        # critical/warning/info
    description  = Column(Text)
    remediation  = Column(Text)
    status       = Column(String, default='open')    # open/fixed/ignored


# ── AEO Results ───────────────────────────────────────────────────────────────
class AeoResult(Base):
    __tablename__ = 'aeo_results'
    id          = Column(Integer, primary_key=True)
    site_id     = Column(Integer, ForeignKey('sites.id'), nullable=False)
    date        = Column(Date, nullable=False, default=date.today)
    query       = Column(String, nullable=False)
    engine      = Column(String, nullable=False)   # google_aio / bing_copilot / manual_chatgpt / etc.
    is_cited    = Column(Boolean, default=False)
    citation_url = Column(String)                  # which page of ours was cited
    raw_snippet = Column(Text)                     # first 500 chars of AI answer
    __table_args__ = (UniqueConstraint('site_id', 'date', 'query', 'engine'),)


# ── Bing Search Performance ────────────────────────────────────────────────────
class BingQuery(Base):
    __tablename__ = 'bing_queries'
    id          = Column(Integer, primary_key=True)
    site_id     = Column(Integer, ForeignKey('sites.id'), nullable=False)
    date        = Column(Date, nullable=False)
    query       = Column(String, nullable=False)
    impressions = Column(Integer, default=0)
    clicks      = Column(Integer, default=0)
    ctr         = Column(Float)
    avg_position = Column(Float)
    __table_args__ = (UniqueConstraint('site_id', 'date', 'query'),)


# ── Technical Site Audit ──────────────────────────────────────────────────────
class SiteCrawlPage(Base):
    __tablename__ = 'site_crawl_pages'
    id                   = Column(Integer, primary_key=True)
    site_id              = Column(Integer, ForeignKey('sites.id'), nullable=False)
    crawled_at           = Column(DateTime, default=datetime.utcnow)
    url                  = Column(String, nullable=False)
    status_code          = Column(Integer)
    title                = Column(String)
    meta_desc            = Column(String)
    h1_count             = Column(Integer, default=0)
    h1_text              = Column(String)
    word_count           = Column(Integer, default=0)
    canonical_url        = Column(String)
    is_noindex           = Column(Boolean, default=False)
    has_schema           = Column(Boolean, default=False)
    image_count          = Column(Integer, default=0)
    images_missing_alt   = Column(Integer, default=0)
    internal_links_count = Column(Integer, default=0)
    issues               = Column(JSON)   # list of issue-type strings
    __table_args__       = (UniqueConstraint('site_id', 'url'),)


# ── PageSpeed / Core Web Vitals ────────────────────────────────────────────────
class PageSpeed(Base):
    __tablename__ = 'pagespeed'
    id          = Column(Integer, primary_key=True)
    site_id     = Column(Integer, ForeignKey('sites.id'), nullable=False)
    date        = Column(Date, nullable=False, default=date.today)
    page_url    = Column(String, nullable=False)
    strategy    = Column(String, default='mobile')  # mobile / desktop
    performance = Column(Integer)   # 0-100
    lcp         = Column(Float)     # seconds
    cls         = Column(Float)
    inp         = Column(Float)     # ms
    fcp         = Column(Float)     # seconds
    ttfb        = Column(Float)     # ms
    speed_index = Column(Float)
    __table_args__ = (UniqueConstraint('site_id', 'date', 'page_url', 'strategy'),)


# ── SERP Top-10 Analysis ───────────────────────────────────────────────────────
class SerpAnalysisResult(Base):
    __tablename__ = 'serp_analysis'
    id             = Column(Integer, primary_key=True)
    site_id        = Column(Integer, ForeignKey('sites.id'), nullable=False)
    keyword        = Column(String, nullable=False)
    analysed_at    = Column(Date, nullable=False, default=date.today)
    position       = Column(Integer)
    url            = Column(String)
    domain         = Column(String)
    title          = Column(String)
    word_count     = Column(Integer)
    backlink_count = Column(Integer)
    has_schema     = Column(Boolean, default=False)
    has_faq        = Column(Boolean, default=False)
    publish_date   = Column(String)
    is_our_domain  = Column(Boolean, default=False)
    __table_args__ = (UniqueConstraint('site_id', 'keyword', 'analysed_at', 'position'),)


# ── Visibility / Share of Voice ────────────────────────────────────────────────
class VisibilityScore(Base):
    __tablename__ = 'visibility_scores'
    id          = Column(Integer, primary_key=True)
    site_id     = Column(Integer, ForeignKey('sites.id'), nullable=False)
    date        = Column(Date, nullable=False)
    domain      = Column(String, nullable=False)
    score       = Column(Float)     # visibility % (0-100)
    traffic_est = Column(Integer)   # estimated monthly traffic
    __table_args__ = (UniqueConstraint('site_id', 'date', 'domain'),)


# ── Alerts ────────────────────────────────────────────────────────────────────
class Alert(Base):
    __tablename__ = 'alerts'
    id          = Column(Integer, primary_key=True)
    site_id     = Column(Integer, ForeignKey('sites.id'), nullable=False)
    created_at  = Column(DateTime, default=datetime.utcnow)
    alert_type  = Column(String)   # rank_drop/lost_backlink/competitor_page/pagespeed_drop/site_down
    severity    = Column(String)   # critical/warning/info
    message     = Column(Text)
    details     = Column(JSON)
    is_read     = Column(Boolean, default=False)
    is_emailed  = Column(Boolean, default=False)


# ── Weekly Report Log ─────────────────────────────────────────────────────────
class ReportLog(Base):
    __tablename__ = 'report_log'
    id          = Column(Integer, primary_key=True)
    site_id     = Column(Integer, ForeignKey('sites.id'), nullable=False)
    week_start  = Column(Date, nullable=False)
    report_path = Column(String)
    emailed_at  = Column(DateTime)
    summary     = Column(JSON)


# ── SERP Volatility (algo update detection) ───────────────────────────────────
class SerpVolatility(Base):
    __tablename__ = 'serp_volatility'
    id                = Column(Integer, primary_key=True)
    site_id           = Column(Integer, ForeignKey('sites.id'), nullable=False)
    date              = Column(Date, nullable=False, default=date.today)
    volatility_score  = Column(Float)   # mean absolute position delta; >5 = suspected update
    keywords_moved    = Column(Integer) # count that shifted 3+ positions
    avg_position_delta = Column(Float)
    suspected_update  = Column(Boolean, default=False)
    __table_args__ = (UniqueConstraint('site_id', 'date'),)


# ── AI Content Briefs ─────────────────────────────────────────────────────────
class ContentBrief(Base):
    __tablename__ = 'content_briefs'
    id               = Column(Integer, primary_key=True)
    site_id          = Column(Integer, ForeignKey('sites.id'), nullable=False)
    keyword          = Column(String, nullable=False)
    created_at       = Column(DateTime, default=datetime.utcnow)
    brief_text       = Column(Text)
    target_word_count = Column(Integer)
    serp_insights    = Column(JSON)   # {avg_wc, schema_pct, faq_pct, has_snippet}
    status           = Column(String, default='draft')  # draft/assigned/published
    opportunity_id   = Column(Integer, ForeignKey('keyword_opportunities.id'), nullable=True)
    __table_args__ = (UniqueConstraint('site_id', 'keyword'),)


# ── Content Refresh Queue ─────────────────────────────────────────────────────
class ContentRefreshItem(Base):
    __tablename__ = 'content_refresh_queue'
    id            = Column(Integer, primary_key=True)
    site_id       = Column(Integer, ForeignKey('sites.id'), nullable=False)
    page_url      = Column(String, nullable=False)
    keyword       = Column(String)
    refresh_score = Column(Float)   # 0-100, higher = more urgent
    reasons       = Column(JSON)    # list of signal strings
    detected_at   = Column(Date, default=date.today)
    status        = Column(String, default='pending')  # pending/in_progress/done


def init_db():
    """Create all tables."""
    os.makedirs(os.path.join(BASE_DIR, 'data'), exist_ok=True)
    Base.metadata.create_all(engine)
    migrate_db()
    print(f'✅ Database initialised: {DB_PATH}')

def migrate_db():
    """Safely add new columns to existing tables (idempotent)."""
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    migrations = [
        'ALTER TABLE rankings ADD COLUMN ai_overview_present BOOLEAN DEFAULT 0',
        'ALTER TABLE rankings ADD COLUMN ai_cited BOOLEAN DEFAULT 0',
        'ALTER TABLE rankings ADD COLUMN location TEXT DEFAULT "national"',
        'ALTER TABLE rankings ADD COLUMN device TEXT DEFAULT "desktop"',
        'ALTER TABLE alerts ADD COLUMN batch_id TEXT',
    ]
    for sql in migrations:
        try:
            c.execute(sql)
        except sqlite3.OperationalError:
            pass  # column already exists
    conn.commit()
    conn.close()
    Base.metadata.create_all(engine)

def get_session() -> Session:
    return SessionLocal()

def get_or_create_site(domain: str, **kwargs) -> Site:
    with SessionLocal() as s:
        site = s.query(Site).filter_by(domain=domain).first()
        if not site:
            site = Site(domain=domain, **kwargs)
            s.add(site); s.commit(); s.refresh(site)
        return site

if __name__ == '__main__':
    init_db()
