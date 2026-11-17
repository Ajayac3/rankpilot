"""
RankPilot — Configuration.
All secrets loaded from .env file. Never hardcoded.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent.parent
load_dotenv(BASE_DIR / '.env')

def env(key: str, default: str = '') -> str:
    return os.environ.get(key, default)

# ── Site being analysed ───────────────────────────────────────────────────────
TARGET_DOMAIN    = env('TARGET_DOMAIN', 'example-legal.in')
GSC_PROPERTY     = env('GSC_PROPERTY',  'https://example-legal.in/')
GA4_PROPERTY_ID  = env('GA4_PROPERTY_ID', '')

# ── Google OAuth (reused from existing seo_engine setup) ─────────────────────
GOOGLE_OAUTH_TOKEN_PATH  = env('GOOGLE_OAUTH_TOKEN_PATH',
                                str(BASE_DIR.parent / 'seo_engine/oauth_token.json'))
GOOGLE_OAUTH_CLIENT_PATH = env('GOOGLE_OAUTH_CLIENT_PATH',
                                str(BASE_DIR.parent / 'seo_engine/oauth_client.json'))
# Service account never expires — preferred over user tokens (7-day expiry while
# the OAuth consent screen is in Testing mode). Grant it access in GA4/GSC admin.
GOOGLE_SERVICE_ACCOUNT_PATH = env('GOOGLE_SERVICE_ACCOUNT_PATH',
                                str(BASE_DIR.parent / 'seo_engine/service-account.json'))

# ── SERP APIs ─────────────────────────────────────────────────────────────────
SERPER_KEY       = env('SERPER_KEY', '')          # serper.dev — 2,500 free/month (primary)
VALUESERP_KEY    = env('VALUESERP_KEY', '')       # valueserp.com (fallback)
SCRAPINGDOG_KEY  = env('SCRAPINGDOG_KEY', '')     # scrapingdog.com (fallback)

# ── DataForSEO ────────────────────────────────────────────────────────────────
DATAFORSEO_LOGIN    = env('DATAFORSEO_LOGIN', '')
DATAFORSEO_PASSWORD = env('DATAFORSEO_PASSWORD', '')

# ── Moz Free API ─────────────────────────────────────────────────────────────
MOZ_ACCESS_ID  = env('MOZ_ACCESS_ID', '')   # moz.com — 50 rows/month free
MOZ_SECRET_KEY = env('MOZ_SECRET_KEY', '')

# ── Reddit API ────────────────────────────────────────────────────────────────
REDDIT_CLIENT_ID     = env('REDDIT_CLIENT_ID', '')
REDDIT_CLIENT_SECRET = env('REDDIT_CLIENT_SECRET', '')
REDDIT_USER_AGENT    = env('REDDIT_USER_AGENT', 'RankPilot/0.1')

# ── AI APIs ──────────────────────────────────────────────────────────────────
DEEPSEEK_API_KEY   = env('DEEPSEEK_API_KEY', '')    # platform.deepseek.com — primary AI
PERPLEXITY_API_KEY = env('PERPLEXITY_API_KEY', '')  # perplexity.ai — LLM citation tracking

# ── Email / SMTP ──────────────────────────────────────────────────────────────
SMTP_USER         = env('SMTP_USER', '')
SMTP_PASS         = env('SMTP_PASS', '')
REPORT_RECIPIENTS = env('REPORT_RECIPIENTS', 'owner@example.com').split(',')

# ── Firm Details (replaces hardcoded values in schema/llmstxt generators) ─────
FIRM_NAME  = env('FIRM_NAME',  'Example Legal Firm')
FIRM_EMAIL = env('FIRM_EMAIL', 'info@example-legal.in')
FIRM_PHONE = env('FIRM_PHONE', '+1-415-555-0100')

# ── Competitors ───────────────────────────────────────────────────────────────
COMPETITORS = [
    {'domain': 'nrilegalservices.com',  'sitemap': 'https://www.nrilegalservices.com/sitemap.xml'},
    {'domain': 'legalhelpnri.com',      'sitemap': 'https://legalhelpnri.com/sitemap.xml'},
    {'domain': 'lawcrust.com',          'sitemap': 'https://lawcrust.com/sitemap.xml'},
    {'domain': 'sheokandlegal.com',     'sitemap': 'https://sheokandlegal.com/sitemap.xml'},
    {'domain': 'nrilegalworld.com',     'sitemap': 'https://nrilegalworld.com/sitemap.xml'},
    {'domain': 'rklegaladvisors.com',   'sitemap': 'https://rklegaladvisors.com/sitemap.xml'},
]

# ── Bing Webmaster Tools ──────────────────────────────────────────────────────
BING_WMT_API_KEY  = env('BING_WMT_API_KEY', '')

# ── IndexNow ──────────────────────────────────────────────────────────────────
INDEXNOW_KEY      = env('INDEXNOW_KEY', '')

# ── Google Business Profile ───────────────────────────────────────────────────
GBP_LOCATION_ID   = env('GBP_LOCATION_ID', '')

# ── Google APIs ───────────────────────────────────────────────────────────────
GOOGLE_PSI_API_KEY = env('GOOGLE_PSI_API_KEY', '')   # PageSpeed Insights — free 25K/day

# ── Feature flags ─────────────────────────────────────────────────────────────
TRACK_MOBILE          = env('TRACK_MOBILE', 'false').lower() == 'true'
ALERT_COOLDOWN_HOURS  = int(env('ALERT_COOLDOWN_HOURS', '20'))

# ── Local rank tracking targets ───────────────────────────────────────────────
LOCAL_RANK_TARGETS = [
    ('Delhi, India',            'IN'),
    ('New Delhi, India',             'IN'),
    ('London, United Kingdom',       'GB'),
    ('Dubai, United Arab Emirates',  'AE'),
]

# ── Reddit subreddits to monitor ──────────────────────────────────────────────
NRI_SUBREDDITS = [
    'NRI', 'IndianImmigrants', 'USIndian', 'CanadianIndians',
    'AusIndian', 'IndiansInEurope', 'IndiansInUAE', 'UKIndian',
    'india', 'LegalAdviceIndia'
]
