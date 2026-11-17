"""
RankPilot — Google Business Profile API
Automate GBP posts for NRI legal updates + fetch review data.
Free API — no per-call billing, just quota management.

Setup:
  1. Google Cloud Console → enable "My Business Business Information API"
     and "My Business Q&A API" and "My Business Lodging API"
  2. OAuth via existing credentials (same account as GSC/GA4)
  3. Set GBP_LOCATION_ID in .env (format: accounts/ACCOUNT_ID/locations/LOCATION_ID)
     Find it at: https://mybusiness.googleapis.com/v4/accounts
"""
import os, sys
from datetime import date
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import TARGET_DOMAIN, GBP_LOCATION_ID

# NRI legal topics for weekly GBP posts
NRI_POST_TOPICS = [
    ('NRI Property Rights — Know the Law',
     'NRIs can file a civil suit for property possession in India even while residing abroad '
     'through a registered Power of Attorney. The limitation period for property suits is '
     'typically 12 years. Learn more about your rights under Indian property law.',
     '/nri-property-dispute-lawyer/'),
    ('498A & NRI Husbands — Legal Overview',
     'NRI husbands facing 498A cases can apply for anticipatory bail from Indian courts. '
     'Recent Supreme Court judgments have strengthened procedural safeguards. '
     'Read our detailed guide on the law and your rights.',
     '/498a-against-nri-husband/'),
    ('OCI Card — Property Rights Explained',
     'OCI cardholders have the same property purchase rights as Indian citizens for residential '
     'and commercial property, except agricultural land and plantation property. '
     'Read the full legal position on OCI and property rights in India.',
     '/all-you-need-to-know-about-oci-card/'),
    ('Power of Attorney for NRIs — How It Works',
     'NRIs can manage property, bank accounts and legal matters in India remotely with a properly '
     'executed and registered Power of Attorney. Read our guide on how to execute a valid POA '
     'from abroad and what it can and cannot authorise.',
     '/power-of-attorney-nri-india/'),
]


def _get_gbp_service():
    """Build authenticated Google Business Profile API service."""
    try:
        NRI_SEO_ENGINE = os.path.join(os.path.dirname(__file__), '../../../nri_seo/seo_engine')
        sys.path.insert(0, os.path.abspath(NRI_SEO_ENGINE))
        from auth_setup import get_credentials
        from googleapiclient.discovery import build

        creds = get_credentials(
            extra_scopes=['https://www.googleapis.com/auth/business.manage']
        )
        return build('mybusinesspostings', 'v1', credentials=creds, cache_discovery=False)
    except Exception as e:
        print(f'  ⚠️ GBP auth: {e}')
        return None


def post_update(title: str, text: str, page_path: str = '',
                location_id: str = None) -> bool:
    """
    Post a local post to Google Business Profile.
    Returns True on success.
    """
    loc = location_id or GBP_LOCATION_ID
    if not loc:
        print('  ⚠️ GBP: GBP_LOCATION_ID not set in .env')
        print('     Find it at: https://mybusiness.googleapis.com/v4/accounts')
        return False

    svc = _get_gbp_service()
    if not svc:
        return False

    call_to_action = {}
    if page_path:
        call_to_action = {
            'actionType': 'LEARN_MORE',
            'url': f'https://{TARGET_DOMAIN}{page_path}',
        }

    body = {
        'languageCode': 'en',
        'summary': f'{title}\n\n{text}',
        'callToAction': call_to_action,
        'topicType': 'STANDARD',
    }
    try:
        svc.locations().localPosts().create(parent=loc, body=body).execute()
        print(f'  ✅ GBP post created: {title}')
        return True
    except Exception as e:
        print(f'  ⚠️ GBP post failed: {e}')
        return False


def fetch_reviews(location_id: str = None) -> list[dict]:
    """Fetch recent Google Business Profile reviews."""
    loc = location_id or GBP_LOCATION_ID
    if not loc:
        return []

    try:
        NRI_SEO_ENGINE = os.path.join(os.path.dirname(__file__), '../../../nri_seo/seo_engine')
        sys.path.insert(0, os.path.abspath(NRI_SEO_ENGINE))
        from auth_setup import get_credentials
        from googleapiclient.discovery import build

        creds = get_credentials(
            extra_scopes=['https://www.googleapis.com/auth/business.manage']
        )
        svc = build('mybusiness', 'v4', credentials=creds, cache_discovery=False)
        resp = svc.accounts().locations().reviews().list(parent=loc).execute()
        reviews = []
        for r in resp.get('reviews', []):
            reviews.append({
                'reviewer':  r.get('reviewer', {}).get('displayName', 'Anonymous'),
                'rating':    r.get('starRating', ''),
                'comment':   r.get('comment', ''),
                'time':      r.get('createTime', ''),
                'replied':   bool(r.get('reviewReply')),
            })
        return reviews
    except Exception as e:
        print(f'  ⚠️ GBP reviews: {e}')
        return []


def post_weekly_update(location_id: str = None) -> bool:
    """Post one rotating NRI legal topic update. Called in weekly run."""
    from datetime import datetime
    # Rotate through topics based on week number
    week_num = datetime.now().isocalendar()[1]
    topic = NRI_POST_TOPICS[week_num % len(NRI_POST_TOPICS)]
    title, text, path = topic
    return post_update(title, text, path, location_id)


def run_gbp(site_domain: str = TARGET_DOMAIN) -> dict:
    """Main entry point called by run.py."""
    if not GBP_LOCATION_ID:
        print('  ℹ️ GBP: GBP_LOCATION_ID not configured — skipping')
        print('     To enable: set GBP_LOCATION_ID in .env')
        return {'skipped': True}

    print(f'  Google Business Profile update for {site_domain}...')
    posted = post_weekly_update()
    reviews = fetch_reviews()

    return {
        'post_sent': posted,
        'reviews':   len(reviews),
        'avg_rating': (sum(
            {'ONE': 1, 'TWO': 2, 'THREE': 3, 'FOUR': 4, 'FIVE': 5}.get(r['rating'], 0)
            for r in reviews
        ) / max(len(reviews), 1)) if reviews else 0,
    }


if __name__ == '__main__':
    result = run_gbp()
    print(result)
