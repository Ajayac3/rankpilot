"""
RankPilot — Core Web Vitals / PageSpeed Insights
Uses Google PageSpeed Insights API (free, no auth for < 25 req/100s).
Tracks: Performance Score, LCP, CLS, INP, FCP, TTFB per page.
"""
import os, sys, requests, time
from datetime import date
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import TARGET_DOMAIN, GOOGLE_PSI_API_KEY
from core.db import get_session, Site, PageSpeed, AuditIssue
from utils.logger import get_logger
log = get_logger(__name__)

PSI_URL = 'https://www.googleapis.com/pagespeedonline/v5/runPagespeed'

# Top service pages to track (add more as needed)
TOP_PAGES = [
    '/',
    '/nri-property-dispute-lawyer/',
    '/498a-against-nri-husband/',
    '/nri-divorce-lawyer-india/',
    '/criminal-litigation/',
    '/power-of-attorney-nri-india/',
    '/all-you-need-to-know-about-oci-card/',
    '/anticipatory-bail-can-be-granted/',
    '/all-you-need-to-know-about-fir/',
    '/contact-us/',
]


def _parse_psi_response(data: dict, strategy: str) -> dict:
    """Parse Google PSI API response into clean metrics dict."""
    cats    = data.get('lighthouseResult', {}).get('categories', {})
    audits  = data.get('lighthouseResult', {}).get('audits', {})

    def _val(key: str, field: str = 'numericValue') -> float | None:
        a = audits.get(key, {})
        return a.get(field)

    perf_score = cats.get('performance', {}).get('score')
    if perf_score is not None:
        perf_score = int(perf_score * 100)

    return {
        'strategy':    strategy,
        'performance': perf_score,
        'lcp':         _val('largest-contentful-paint'),     # ms → convert to s below
        'cls':         _val('cumulative-layout-shift'),
        'inp':         _val('interaction-to-next-paint'),     # ms
        'fcp':         _val('first-contentful-paint'),        # ms
        'ttfb':        _val('server-response-time'),          # ms
        'speed_index': _val('speed-index'),                   # ms
    }


def fetch_pagespeed(url: str, strategy: str = 'mobile') -> dict | None:
    """Fetch PageSpeed data for a single URL with retry on 429."""
    params = {'url': url, 'strategy': strategy, 'category': 'performance'}
    if GOOGLE_PSI_API_KEY:
        params['key'] = GOOGLE_PSI_API_KEY
    for attempt in range(3):
        try:
            r = requests.get(PSI_URL, params=params, timeout=60)
            if r.status_code == 200:
                return _parse_psi_response(r.json(), strategy)
            if r.status_code == 429:
                wait = (attempt + 1) * 30
                print(f'  ⏳ PSI rate limited — waiting {wait}s...', flush=True)
                time.sleep(wait)
                continue
            if r.status_code in (500, 502, 503):
                wait = (attempt + 1) * 5
                print(f'  ⏳ PSI {r.status_code} — retrying in {wait}s...', flush=True)
                time.sleep(wait)
                continue
            log.warning('PSI %s %s: HTTP %s', strategy, url, r.status_code)
            print(f'  ⚠️ PSI {strategy} {url}: HTTP {r.status_code}', flush=True)
            return None
        except requests.exceptions.Timeout:
            log.warning('PSI timeout attempt %d/3: %s', attempt + 1, url)
            print(f'  ⏳ PSI timeout — retrying ({attempt+1}/3)...', flush=True)
            time.sleep((attempt + 1) * 5)
            continue
        except Exception as e:
            log.error('PSI %s %s: %s', strategy, url, e)
            print(f'  ⚠️ PSI {strategy} {url}: {e}', flush=True)
            return None
    return None


def run_pagespeed_audit(site_domain: str = TARGET_DOMAIN,
                        pages: list[str] = None,
                        strategies: list[str] = ('mobile', 'desktop')) -> list[dict]:
    """
    Run PageSpeed for all top pages.
    Delays 2s between requests to stay within free rate limit.
    """
    base_url  = f'https://{site_domain}'
    page_list = pages or TOP_PAGES
    results   = []

    with get_session() as s:
        site = s.query(Site).filter_by(domain=site_domain).first()
        if not site:
            print('  ⚠️ Site not in DB. Run: python run.py setup')
            return []
        site_id = site.id

    total = len(page_list) * len(strategies)
    done  = 0
    print(f'  PageSpeed audit: {len(page_list)} pages × {len(strategies)} strategies ({total} requests)')

    for page_path in page_list:
        page_url = base_url + page_path
        for strategy in strategies:
            done += 1
            print(f'  [{done}/{total}] {strategy}: {page_path}', end='  ', flush=True)
            data = fetch_pagespeed(page_url, strategy)
            if not data:
                print('FAILED', flush=True)
                continue

            score = data.get('performance') or 0
            lcp_s = (data.get('lcp') or 0) / 1000  # ms to seconds
            cls_v = data.get('cls') or 0
            inp_m = data.get('inp') or 0            # ms
            fcp_s = (data.get('fcp') or 0) / 1000
            ttfb_m = data.get('ttfb') or 0
            si    = data.get('speed_index') or 0

            print(f'Score={score} LCP={lcp_s:.1f}s CLS={cls_v:.3f} INP={inp_m:.0f}ms', flush=True)
            results.append({**data, 'page_url': page_url, 'lcp': lcp_s, 'fcp': fcp_s})

            with get_session() as s:
                existing = s.query(PageSpeed).filter_by(
                    site_id=site_id, date=date.today(),
                    page_url=page_url, strategy=strategy
                ).first()
                row_data = dict(
                    site_id=site_id, date=date.today(),
                    page_url=page_url, strategy=strategy,
                    performance=score, lcp=lcp_s, cls=cls_v,
                    inp=inp_m, fcp=fcp_s, ttfb=ttfb_m, speed_index=si / 1000,
                )
                if existing:
                    for k, v in row_data.items():
                        setattr(existing, k, v)
                else:
                    s.add(PageSpeed(**row_data))

                # Flag critical issues
                if strategy == 'mobile':
                    if score < 50:
                        s.add(AuditIssue(
                            site_id=site_id, page_url=page_url,
                            issue_type='pagespeed_critical',
                            severity='critical',
                            description=f'Mobile performance score {score}/100 — very slow',
                            remediation='Optimise images, remove unused JS/CSS, enable caching',
                            status='open'
                        ))
                    if lcp_s > 4.0:
                        s.add(AuditIssue(
                            site_id=site_id, page_url=page_url,
                            issue_type='lcp_slow',
                            severity='warning',
                            description=f'LCP {lcp_s:.1f}s (target: < 2.5s)',
                            remediation='Preload hero image, use next-gen formats (WebP), reduce server response time',
                            status='open'
                        ))
                    if cls_v > 0.1:
                        s.add(AuditIssue(
                            site_id=site_id, page_url=page_url,
                            issue_type='cls_high',
                            severity='warning',
                            description=f'CLS {cls_v:.3f} (target: < 0.1) — layout shifts hurt UX',
                            remediation='Set explicit width/height on images and embeds',
                            status='open'
                        ))
                s.commit()

            time.sleep(8)  # anonymous PSI quota: ~10 req/min safe

    poor = sum(1 for r in results if (r.get('performance') or 0) < 50 and r.get('strategy') == 'mobile')
    print(f'\n  ✅ PageSpeed complete: {len(results)//2} pages | {poor} with critical scores')
    return results


if __name__ == '__main__':
    run_pagespeed_audit()
