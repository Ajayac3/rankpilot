#!/usr/bin/env python3
"""
RankPilot — Professional SEO Platform
Usage:
  python run.py setup              # Init DB + load seed keywords
  python run.py collect            # GSC + GA4 + competitors + Bing WMT + GBP post
  python run.py rank               # Keyword rank tracking (Serper/ValueSERP + local + mobile)
  python run.py discover           # Keyword discovery (autocomplete + reddit)
  python run.py analyse            # Content gap + KD + cannibalization + E-E-A-T + SoV
  python run.py audit              # Full technical site audit (Screaming Frog equivalent)
  python run.py pagespeed          # Core Web Vitals via Google PSI API (free)
  python run.py serp               # SERP top-10 deep analysis for priority keywords
  python run.py alerts             # Run daily alert checks (rank drops, lost backlinks)
  python run.py aeo                # Google AI Overview + Bing Copilot (Playwright, ~5 min)
  python run.py llm                # Perplexity citation tracking (LLM visibility)
  python run.py brief <keyword>    # Generate AI content brief for a keyword (DeepSeek)
  python run.py classify           # AI intent classification for GSC queries (DeepSeek)
  python run.py volatility         # SERP volatility check (algo update detection)
  python run.py refresh            # Content refresh queue analysis
  python run.py report             # Generate weekly report with AI summary (DeepSeek)
  python run.py schema             # Generate JSON-LD schema for all service pages
  python run.py llmstxt            # Generate /llms.txt for AI search engines
  python run.py indexnow           # Submit recent pages to IndexNow
  python run.py explore <topic>    # Content Explorer: analyse top content for a topic
  python run.py full               # Run everything (full weekly job)
  python run.py dashboard          # Launch Streamlit dashboard

Options:
  --site <domain>                  # Override target domain (default: from .env)
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rich.console import Console
from rich.panel import Panel
from core.config import TARGET_DOMAIN

console = Console()

# Parse --site flag
_site_override = None
for _i, _arg in enumerate(sys.argv):
    if _arg == '--site' and _i + 1 < len(sys.argv):
        _site_override = sys.argv[_i + 1]
DOMAIN = _site_override or TARGET_DOMAIN

def setup():
    console.print(Panel('[bold]RankPilot Setup[/bold]'))
    from core.db import init_db
    init_db()
    from seed.load_keywords import load
    load()
    console.print('✅ Setup complete. Run: python run.py collect')

def collect():
    import time
    t0 = time.time()
    console.print(Panel(f'[bold]Collecting data for {DOMAIN}[/bold]'))

    console.print('\n[cyan]1/8 GSC data...[/cyan]')
    try:
        from collectors.gsc import fetch_comparison
        from core.config import GSC_PROPERTY
        data = fetch_comparison(GSC_PROPERTY)
        console.print(f'  ✅ {len(data["this"]["queries"])} queries fetched')
        # Save to DB
        _save_gsc_to_db(data)
    except Exception as e:
        import traceback
        console.print(f'  ⚠️ GSC: {e}')
        console.print(f'[dim]{traceback.format_exc()}[/dim]')

    console.print('\n[cyan]2/8 Competitor sitemaps...[/cyan]')
    try:
        from collectors.competitor import run_competitor_monitor
        new_pages = run_competitor_monitor(DOMAIN)
        console.print(f'  ✅ {len(new_pages)} new competitor pages detected')
    except Exception as e:
        console.print(f'  ⚠️ Competitor: {e}')

    console.print('\n[cyan]3/8 GA4 data...[/cyan]')
    try:
        from collectors.ga4 import fetch as ga4_fetch, fetch_daily as ga4_daily, save_daily_to_db as ga4_save_daily
        from core.config import GA4_PROPERTY_ID
        if GA4_PROPERTY_ID:
            ga4_data = ga4_fetch(GA4_PROPERTY_ID)
            console.print(f'  ✅ Sessions: {ga4_data["sessions"]["this"]}, Leads: {sum(ga4_data["this"].values())}')
            # Per-day rows, 30-day window: correct to sum, and it re-fills any day
            # an earlier run missed (six were missing across August).
            daily = ga4_daily(GA4_PROPERTY_ID, days=30)
            saved = ga4_save_daily(daily, DOMAIN)
            console.print(f'  ✅ GA4: {saved} day/channel rows saved over {len(daily)} days')
        else:
            console.print('  ⚠️ GA4_PROPERTY_ID not set in .env')
    except Exception as e:
        import traceback
        console.print(f'  ⚠️ GA4: {e}')
        console.print(f'[dim]{traceback.format_exc()}[/dim]')

    console.print('\n[cyan]4/8 Bing Webmaster Tools...[/cyan]')
    try:
        from collectors.bing_wmt import run_bing_wmt
        bdata = run_bing_wmt(DOMAIN)
        if bdata:
            console.print(f'  ✅ Bing: {bdata.get("total_clicks", 0)} clicks, {bdata.get("queries", 0)} queries')
    except Exception as e:
        console.print(f'  ⚠️ Bing WMT: {e}')

    console.print('\n[cyan]5/8 Google Business Profile post...[/cyan]')
    try:
        from collectors.gbp_poster import run_gbp
        gbp = run_gbp(DOMAIN)
        if not gbp.get('skipped'):
            console.print(f'  ✅ GBP post sent: {gbp.get("post_sent", False)}')
    except Exception as e:
        console.print(f'  ⚠️ GBP: {e}')

    console.print('\n[cyan]6/8 Backlinks...[/cyan]')
    try:
        from collectors.backlinks import run_backlink_monitor
        bl = run_backlink_monitor(DOMAIN)
        console.print(f'  ✅ Backlinks: {bl.get("total", 0)} live, {len(bl.get("new", []))} new')
    except Exception as e:
        console.print(f'  ⚠️ Backlinks: {e}')

    console.print('\n[cyan]7/8 Community mentions (Reddit)...[/cyan]')
    try:
        from collectors.community import run_community_monitor
        mentions = run_community_monitor(DOMAIN)
        console.print(f'  ✅ Community: {len(mentions)} answer opportunities found')
    except Exception as e:
        console.print(f'  ⚠️ Community: {e}')

    console.print('\n[cyan]8/8 Rank tracking + keyword volumes...[/cyan]')
    # Weekly (Mondays) only: daily × 7 countries × local × mobile burned the
    # 2,500/mo Serper quota by May 29 → 7 weeks of silent NULL positions.
    # ~100 calls every Monday fits the free tier; scorecard runs Monday 09:00.
    from datetime import date as _date
    if _date.today().weekday() == 0:
        try:
            from collectors.rank_tracker import run_rank_tracking
            r = run_rank_tracking(DOMAIN, priority_max=1)
            ranked = [x for x in r if x.get('position')]
            console.print(f'  ✅ Rank tracking: {len(ranked)}/{len(r)} keywords found')
        except Exception as e:
            console.print(f'  ⚠️ Rank tracking: {e}')
    else:
        console.print('  ⏭ Rank tracking: weekly (Mondays) — skipped to stay inside Serper free quota')
    try:
        from collectors.keyword_volume import run_keyword_volume
        vols = run_keyword_volume(DOMAIN, max_keywords=200)
        console.print(f'  ✅ Volumes: {vols.get("updated", 0)} keywords updated')
    except Exception as e:
        console.print(f'  ⚠️ Keyword volumes: {e}')

    console.print(f'\n[cyan]Done in {time.time()-t0:.0f}s.[/cyan]')

def quick():
    """Fast daily run: collect + report. ~5 min."""
    console.print(Panel(f'[bold green]RankPilot Quick Daily Run — {DOMAIN}[/bold green]'))
    collect()   # GSC + GA4 + competitors + Bing + backlinks + community + rank tracking
    # AEO tracking isolated: a Playwright crash must never kill the daily collect/report
    try:
        from collectors.aeo_tracker import run_aeo_tracker
        run_aeo_tracker(DOMAIN)
    except Exception as e:
        console.print(f'  ⚠️ AEO tracker: {e}')
    report()    # generate report


def rank():
    console.print(Panel('[bold]Rank Tracking[/bold]'))
    from collectors.rank_tracker import run_rank_tracking
    results = run_rank_tracking(DOMAIN, priority_max=2)
    if results:
        ranked = [r for r in results if r.get('position')]
        console.print(f'\n✅ {len(ranked)}/{len(results)} keywords found in top 100')

def discover():
    console.print(Panel('[bold]Keyword Discovery[/bold]'))
    from collectors.keyword_miner import run_keyword_discovery
    results = run_keyword_discovery(DOMAIN, save_to_db=True)
    console.print(f'\n✅ {len(results)} new keyword opportunities saved')

def analyse():
    console.print(Panel('[bold]SEO Analysis[/bold]'))

    console.print('[cyan]Content gap analysis...[/cyan]')
    try:
        from analysis.content_gap import run_content_gap
        run_content_gap(DOMAIN)
    except Exception as e:
        console.print(f'  ⚠️ Content gap: {e}')

    console.print('[cyan]Cannibalization detection...[/cyan]')
    try:
        from analysis.cannibalization import run_cannibalization_check
        run_cannibalization_check(DOMAIN)
    except Exception as e:
        console.print(f'  ⚠️ Cannibalization: {e}')

    console.print('[cyan]Domain authority check...[/cyan]')
    try:
        from analysis.domain_authority import check_domain_authority
        check_domain_authority(DOMAIN)
    except Exception as e:
        console.print(f'  ⚠️ Domain authority: {e}')

    console.print('[cyan]Backlink trend analysis...[/cyan]')
    try:
        from analysis.backlink_trends import run_backlink_trends
        run_backlink_trends(DOMAIN)
    except Exception as e:
        console.print(f'  ⚠️ Backlink trends: {e}')

    console.print('[cyan]E-E-A-T audit...[/cyan]')
    try:
        from analysis.eeat_audit import run_eeat_audit
        run_eeat_audit(DOMAIN)
    except Exception as e:
        console.print(f'  ⚠️ E-E-A-T audit: {e}')

    console.print('[cyan]CommonCrawl competitor backlinks...[/cyan]')
    try:
        from collectors.commoncrawl import run_cc_backlink_discovery
        cc = run_cc_backlink_discovery(DOMAIN)
        console.print(f'  ✅ CommonCrawl: {cc.get("found", 0)} links found, {cc.get("saved", 0)} new saved')
    except Exception as e:
        console.print(f'  ⚠️ CommonCrawl: {e}')

    console.print('[cyan]Share of Voice...[/cyan]')
    try:
        from analysis.share_of_voice import calculate_share_of_voice
        sov = calculate_share_of_voice(DOMAIN)
        console.print(f'  ✅ SoV: {sov.get("our_score", 0):.1f}% | Est traffic: {sov.get("our_traffic", 0):,}/month')
    except Exception as e:
        console.print(f'  ⚠️ Share of Voice: {e}')

    console.print('[cyan]Traffic estimation...[/cyan]')
    try:
        from analysis.traffic_estimator import run_traffic_estimator
        run_traffic_estimator(DOMAIN)
    except Exception as e:
        console.print(f'  ⚠️ Traffic estimator: {e}')

    console.print('[cyan]Link gap analysis...[/cyan]')
    try:
        from analysis.link_gap import run_link_gap
        gaps = run_link_gap(DOMAIN, max_competitors=3)
        console.print(f'  ✅ Link gap: {len(gaps)} backlink opportunities found')
    except Exception as e:
        console.print(f'  ⚠️ Link gap: {e}')

    console.print('[cyan]Keyword volume update...[/cyan]')
    try:
        from collectors.keyword_volume import run_keyword_volume
        kv = run_keyword_volume(DOMAIN)
        console.print(f'  ✅ Volume: {kv.get("updated", 0)} keywords updated')
    except Exception as e:
        console.print(f'  ⚠️ Keyword volume: {e}')

def report():
    console.print(Panel('[bold]Generating Weekly Report[/bold]'))
    try:
        from report.builder import build_and_send
        from collectors.gsc import fetch_comparison
        from core.config import GSC_PROPERTY
        try:
            gsc_live = fetch_comparison(GSC_PROPERTY)
        except Exception:
            gsc_live = None
        build_and_send(DOMAIN, gsc_data=gsc_live)
    except Exception as e:
        console.print(f'  ⚠️ Report: {e}')

def audit():
    """Full technical site audit — Screaming Frog equivalent."""
    console.print(Panel('[bold]Technical Site Audit[/bold]'))
    from audit.site_crawler import run_site_audit
    result = run_site_audit(DOMAIN)
    console.print(f'✅ {result.get("pages_audited", 0)} pages | '
                  f'Critical: {result.get("critical", 0)} | '
                  f'Warnings: {result.get("warnings", 0)}')


def pagespeed():
    """Core Web Vitals audit via Google PageSpeed Insights API (free)."""
    console.print(Panel('[bold]PageSpeed / Core Web Vitals[/bold]'))
    from collectors.pagespeed import run_pagespeed_audit
    run_pagespeed_audit(DOMAIN)


def serp():
    """SERP top-10 deep analysis for priority keywords."""
    console.print(Panel('[bold]SERP Top-10 Analyser[/bold]'))
    from analysis.serp_analyzer import run_serp_analyser
    run_serp_analyser(DOMAIN, max_keywords=5)


def alerts():
    """Daily alert checks: rank drops, lost backlinks, competitor pages, site down."""
    console.print(Panel('[bold]Alert Engine[/bold]'))
    from alerts.alert_engine import run_alerts
    result = run_alerts(DOMAIN)
    total = result.get('total', 0)
    console.print(f'✅ {total} alert(s) detected | Site up: {result.get("site_up", "?")}')


def explore(topic: str = None):
    """Content Explorer — analyse top content for a topic."""
    console.print(Panel('[bold]Content Explorer[/bold]'))
    if not topic:
        console.print('[yellow]Usage: python run.py explore "your topic"[/yellow]')
        return
    from analysis.content_explorer_v2 import explore_topic
    explore_topic(topic)


def aeo():
    """AI Overview + Bing Copilot AEO check (slow — uses Playwright)."""
    console.print(Panel('[bold]AEO Tracker — AI Overview + Bing Copilot[/bold]'))
    console.print('[yellow]⚠️  This uses Playwright with 12s delays — takes ~5 min[/yellow]')
    try:
        from collectors.ai_overview import run_ai_overview_check
        results = run_ai_overview_check(DOMAIN)
        cited = sum(1 for r in results if r.get('ai_cited'))
        present = sum(1 for r in results if r.get('ai_overview_present'))
        console.print(f'\n✅ Google AIO: {present}/{len(results)} keywords have AI Overview, cited in {cited}')
    except Exception as e:
        console.print(f'  ⚠️ AI Overview: {e}')

    try:
        from collectors.aeo_tracker import run_aeo_tracker
        run_aeo_tracker(DOMAIN)
    except Exception as e:
        console.print(f'  ⚠️ Bing AEO: {e}')


def schema():
    """Generate JSON-LD schema markup for all service pages."""
    console.print(Panel('[bold]Schema Generator[/bold]'))
    from utils.schema_generator import generate_all_schemas
    generate_all_schemas()


def llmstxt():
    """Generate /llms.txt for AI search engine citation optimization."""
    console.print(Panel('[bold]llms.txt Generator[/bold]'))
    from utils.llmstxt_generator import generate_llmstxt
    generate_llmstxt(DOMAIN)


def indexnow():
    """Submit recently updated pages to IndexNow (Bing/Yandex/DuckDuckGo)."""
    console.print(Panel('[bold]IndexNow — URL Submission[/bold]'))
    from utils.indexnow import submit_recent_pages
    submit_recent_pages(DOMAIN)


def llm():
    """Perplexity LLM citation tracking — checks if site is cited in AI answers."""
    console.print(Panel('[bold]LLM Visibility — Perplexity Citation Check[/bold]'))
    from collectors.llm_visibility import run_llm_visibility
    results = run_llm_visibility(DOMAIN)
    if results:
        cited = sum(1 for r in results if r.get('is_cited'))
        console.print(f'\n✅ Cited in {cited}/{len(results)} Perplexity answers')


def brief(keyword: str = None):
    """Generate AI content brief for a keyword using DeepSeek."""
    console.print(Panel('[bold]AI Content Brief Generator (DeepSeek)[/bold]'))
    if not keyword:
        console.print('[yellow]Usage: python run.py brief "your keyword"[/yellow]')
        return
    from analysis.ai_brief_generator import generate_and_save
    result = generate_and_save(keyword, DOMAIN)
    console.print(f'\n✅ {result}')


def brief_batch():
    """Generate briefs for top 3 commercial keyword opportunities."""
    console.print(Panel('[bold]AI Brief Batch — Top 3 Opportunities[/bold]'))
    from analysis.ai_brief_generator import run_brief_batch
    run_brief_batch(DOMAIN, max_briefs=3)


def classify():
    """AI intent classification for all unclassified GSC queries (DeepSeek)."""
    console.print(Panel('[bold]AI Intent Classifier (DeepSeek)[/bold]'))
    from analysis.intent_classifier import classify_and_save
    from core.db import get_session, Site
    with get_session() as s:
        site = s.query(Site).filter_by(domain=DOMAIN).first()
        if site:
            classify_and_save(site.id)


def volatility():
    """SERP volatility index — detect Google algorithm updates."""
    console.print(Panel('[bold]SERP Volatility Index[/bold]'))
    from collectors.serp_volatility import calculate_volatility
    result = calculate_volatility(DOMAIN)
    if result:
        console.print(f'\n✅ Volatility score: {result.get("score", 0):.1f} | '
                      f'Suspected update: {result.get("suspected_update", False)}')


def refresh():
    """Content refresh queue — identify pages needing an update."""
    console.print(Panel('[bold]Content Refresh Queue[/bold]'))
    from analysis.content_refresh import run_content_refresh_analysis
    results = run_content_refresh_analysis(DOMAIN)
    console.print(f'\n✅ {len(results)} pages in refresh queue')


def full():
    """Full weekly run — runs every single module in order."""
    console.print(Panel(f'[bold green]RankPilot Full Weekly Run — {DOMAIN}[/bold green]'))

    # ── Step 1: Collect all data ──────────────────────────────────────────────
    console.print('\n[bold cyan]STEP 1: Data Collection[/bold cyan]')
    collect()       # GSC, GA4, Competitors, Bing, GBP, Backlinks, Community

    # ── Step 2: Rank tracking ─────────────────────────────────────────────────
    console.print('\n[bold cyan]STEP 2: Rank Tracking[/bold cyan]')
    rank()          # All keywords + local cities + mobile

    # ── Step 3: Keyword discovery ─────────────────────────────────────────────
    console.print('\n[bold cyan]STEP 3: Keyword Discovery[/bold cyan]')
    discover()      # Google/YouTube/Bing autocomplete + Reddit

    # ── Step 4: Deep analysis ─────────────────────────────────────────────────
    console.print('\n[bold cyan]STEP 4: SEO Analysis[/bold cyan]')
    analyse()       # Content gap, KD, E-E-A-T, SoV, Link gap, Traffic est.

    # ── Step 5: Technical audits ──────────────────────────────────────────────
    console.print('\n[bold cyan]STEP 5: Technical Audits[/bold cyan]')
    for fn, name in [(audit, 'site audit'), (pagespeed, 'pagespeed/CWV'),
                     (serp, 'serp analysis')]:
        try:
            fn()
        except Exception as e:
            console.print(f'  ⚠️ {name}: {e}')

    # ── Step 6: Alert checks ──────────────────────────────────────────────────
    console.print('\n[bold cyan]STEP 6: Alerts[/bold cyan]')
    try:
        alerts()
    except Exception as e:
        console.print(f'  ⚠️ alerts: {e}')

    # ── Step 7: SERP volatility ───────────────────────────────────────────────
    console.print('\n[bold cyan]STEP 7: SERP Volatility[/bold cyan]')
    try:
        volatility()
    except Exception as e:
        console.print(f'  ⚠️ volatility: {e}')

    # ── Step 8: AI features ───────────────────────────────────────────────────
    console.print('\n[bold cyan]STEP 8: AI Features[/bold cyan]')
    for fn, name in [(classify, 'intent classification'),
                     (brief_batch, 'content briefs'),
                     (refresh, 'content refresh queue'),
                     (llm, 'LLM visibility')]:
        try:
            fn()
        except Exception as e:
            console.print(f'  ⚠️ {name}: {e}')

    # ── Step 9: Generate report ───────────────────────────────────────────────
    console.print('\n[bold cyan]STEP 9: Generate Report[/bold cyan]')
    report()        # TXT + PDF with AI executive summary

    # ── Step 10: Post-report utilities ────────────────────────────────────────
    console.print('\n[bold cyan]STEP 10: Post-Report Utilities[/bold cyan]')
    for fn, name in [(schema, 'schema markup'),
                     (llmstxt, 'llms.txt'),
                     (indexnow, 'IndexNow submission')]:
        try:
            fn()
        except Exception as e:
            console.print(f'  ⚠️ {name}: {e}')

    console.print(Panel('[bold green]✅ Full weekly run complete[/bold green]'))

def dashboard():
    console.print('Launching dashboard...')
    os.system('streamlit run dashboard/app.py')

def _save_gsc_period(s, site_id: int, period_data: dict, period_key: str, window_days: int = 7):
    """Save one GSC period (queries + pages) with the period's actual end date.

    window_days records what the row actually covers so later sums can exclude the
    rolling-window rows written before 2026-09-01. Pass 1 for true single days.
    """
    from datetime import datetime
    from core.db import GscQuery, GscPage
    try:
        period_date = datetime.strptime(period_data['end'], '%Y-%m-%d').date()
    except Exception:
        from datetime import date
        period_date = date.today()

    for query, v in period_data.get('queries', {}).items():
        # country/device are never set on insert (NULL), so filtering country=''/device=''
        # never matched and every run re-inserted the row — dedupe on the real key
        existing = s.query(GscQuery).filter_by(
            site_id=site_id, date=period_date, query=query
        ).first()
        if existing:
            existing.clicks      = v['clicks']
            existing.impressions = v['impressions']
            existing.position    = v['position']
            existing.window_days = window_days
            if v.get('page'):
                existing.page = v['page']
        else:
            s.add(GscQuery(
                site_id=site_id, date=period_date, query=query,
                clicks=v['clicks'], impressions=v['impressions'],
                position=v['position'], page=v.get('page'),
                window_days=window_days
            ))

    for page, v in period_data.get('pages', {}).items():
        existing = s.query(GscPage).filter_by(
            site_id=site_id, date=period_date, page=page
        ).first()
        if existing:
            existing.clicks      = v['clicks']
            existing.impressions = v['impressions']
            existing.position    = v['position']
            existing.window_days = window_days
        else:
            s.add(GscPage(
                site_id=site_id, date=period_date, page=page,
                clicks=v['clicks'], impressions=v['impressions'],
                position=v['position'], window_days=window_days
            ))
    s.commit()


def _save_gsc_to_db(data: dict):
    """Persist GSC as one row per day.

    Only the per-day rows are written now. The 7-day 'this'/'prev' aggregates are
    still returned for the weekly report, but storing them against a single date
    is what produced the ~7x inflation in every historical total, so they no
    longer reach the database.
    """
    from core.db import get_session, Site
    with get_session() as s:
        site = s.query(Site).filter_by(domain=DOMAIN).first()
        if not site: return
        daily = data.get('daily') or {}
        for day_date in sorted(daily):
            _save_gsc_period(s, site.id, daily[day_date], day_date, window_days=1)
        if not daily:
            console.print('  ⚠️ GSC: no per-day rows returned — nothing written')


def _import_backlinks():
    """Import backlinks from Ahrefs CSV export."""
    import os
    csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'ahrefs_backlinks.csv')
    from collectors.backlinks import import_ahrefs_csv
    result = import_ahrefs_csv(csv_path, DOMAIN)
    console.print(f'✅ Imported {result["imported"]} backlinks from Ahrefs CSV')


def backfill_gsc():
    """Backfill 16 months of historical GSC data into DB."""
    console.print(Panel('[bold]GSC Historical Backfill — 16 months[/bold]'))
    from collectors.gsc import _service, _query, _date_range
    from core.config import GSC_PROPERTY
    from core.db import get_session, Site
    from datetime import timedelta, datetime

    with get_session() as s:
        site = s.query(Site).filter_by(domain=DOMAIN).first()
        if not site:
            console.print('[red]Site not found in DB. Run setup first.[/red]')
            return

    try:
        svc = _service()
    except Exception as e:
        console.print(f'[red]GSC auth failed: {e}[/red]')
        return

    # Fetch in 28-day chunks going back 16 months
    today   = datetime.now().date()
    chunks  = []
    end     = today - timedelta(days=3)   # GSC data is final ~3 days after
    for _ in range(18):                   # 18 × 28 days ≈ 16 months
        start = end - timedelta(days=27)
        chunks.append((start, end))
        end = start - timedelta(days=1)

    console.print(f'  Fetching {len(chunks)} periods (28-day chunks)...')
    from core.db import get_session, Site, GscQuery, GscPage
    saved_total = 0

    for start, end in chunks:
        start_str = start.strftime('%Y-%m-%d')
        end_str   = end.strftime('%Y-%m-%d')
        try:
            from googleapiclient.errors import HttpError
            queries_rows = svc.searchanalytics().query(
                siteUrl=GSC_PROPERTY,
                body={'startDate': start_str, 'endDate': end_str,
                      'dimensions': ['query'], 'rowLimit': 5000, 'dataState': 'final'}
            ).execute().get('rows', [])

            pages_rows = svc.searchanalytics().query(
                siteUrl=GSC_PROPERTY,
                body={'startDate': start_str, 'endDate': end_str,
                      'dimensions': ['page'], 'rowLimit': 5000, 'dataState': 'final'}
            ).execute().get('rows', [])

            period_data = {
                'end': end_str,
                'queries': {r['keys'][0].lower(): {
                    'clicks': r['clicks'], 'impressions': r['impressions'],
                    'position': round(r['position'], 2)
                } for r in queries_rows},
                'pages': {r['keys'][0]: {
                    'clicks': r['clicks'], 'impressions': r['impressions'],
                    'position': round(r['position'], 2)
                } for r in pages_rows},
            }

            with get_session() as s:
                site = s.query(Site).filter_by(domain=DOMAIN).first()
                _save_gsc_period(s, site.id, period_data, 'backfill')

            saved_total += len(queries_rows) + len(pages_rows)
            console.print(f'  ✅ {start_str} → {end_str}: {len(queries_rows)} queries, {len(pages_rows)} pages')

        except Exception as e:
            console.print(f'  ⚠️ {start_str} → {end_str}: {e}')

    console.print(f'\n✅ Backfill complete — {saved_total} rows saved')

if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'help'
    commands = {
        'setup':      setup,
        'backfill':   backfill_gsc,
        'import-backlinks': lambda: _import_backlinks(),
        'collect':    collect,
        'rank':       rank,
        'discover':   discover,
        'analyse':    analyse,
        'report':     report,
        'audit':      audit,
        'pagespeed':  pagespeed,
        'serp':       serp,
        'alerts':     alerts,
        'aeo':        aeo,
        'llm':        llm,
        'brief':      lambda: brief(sys.argv[2] if len(sys.argv) > 2 else None),
        'briefs':     brief_batch,
        'classify':   classify,
        'volatility': volatility,
        'refresh':    refresh,
        'schema':     schema,
        'llmstxt':    llmstxt,
        'indexnow':   indexnow,
        'quick':      quick,
        'full':       full,
        'dashboard':  dashboard,
        'explore':    lambda: explore(sys.argv[2] if len(sys.argv) > 2 else None),
    }
    if cmd in commands:
        commands[cmd]()
    else:
        print(__doc__)
