"""
RankPilot — Streamlit Dashboard
Run: streamlit run dashboard/app.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
from datetime import date, timedelta

st.set_page_config(
    page_title='RankPilot — SEO Dashboard',
    page_icon='🚀',
    layout='wide',
    initial_sidebar_state='expanded'
)

from core.db import (get_session, Site, Keyword, Ranking, GscQuery, GscPage,
                     Competitor, CompetitorUrl, Backlink, KeywordOpportunity,
                     Mention, AuditIssue, AeoResult, BingQuery,
                     SiteCrawlPage, PageSpeed, SerpAnalysisResult,
                     VisibilityScore, Alert)
from core.config import TARGET_DOMAIN

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title('🚀 RankPilot')
    st.caption('SEO Intelligence Platform')

    with get_session() as s:
        sites = s.query(Site).all()
        domains = [s.domain for s in sites]

    domain = st.selectbox('Site', domains, index=0 if domains else 0)
    page = st.radio('Navigation', [
        '📊 Overview', '🎯 Keywords', '🏆 Rankings',
        '🕵️ Competitors', '🔗 Backlinks', '📡 Opportunities',
        '💬 Community', '🔧 Audit', '🤖 AI Visibility',
        '🔍 Site Audit', '⚡ PageSpeed', '📊 SERP Analysis',
        '🚨 Alerts', '📄 Reports'
    ])

# ── Load site ─────────────────────────────────────────────────────────────────
with get_session() as s:
    site = s.query(Site).filter_by(domain=domain).first()
    site_id = site.id if site else None

if not site_id:
    st.error(f'Site {domain} not found. Run: python run.py setup')
    st.stop()

# ── OVERVIEW ──────────────────────────────────────────────────────────────────
if '📊 Overview' in page:
    st.title(f'📊 Overview — {domain}')

    with get_session() as s:
        total_kws = s.query(Keyword).filter_by(site_id=site_id).count()
        ranked    = s.query(Ranking).filter_by().join(Keyword).filter(
            Keyword.site_id == site_id
        ).filter(Ranking.date == date.today()).count()
        top10     = s.query(Ranking).join(Keyword).filter(
            Keyword.site_id == site_id,
            Ranking.date == date.today(),
            Ranking.position <= 10
        ).count()
        new_opps    = s.query(KeywordOpportunity).filter_by(site_id=site_id, status='new').count()
        backlinks   = s.query(Backlink).filter_by(site_id=site_id, status='live').count()
        new_comp    = s.query(CompetitorUrl).join(Competitor).filter(
            Competitor.site_id == site_id,
            CompetitorUrl.is_new == True
        ).count()
        open_issues = s.query(AuditIssue).filter_by(site_id=site_id, status='open').count()
        aio_cited   = s.query(AeoResult).filter_by(site_id=site_id, is_cited=True).count()
        aio_total   = s.query(AeoResult).filter_by(site_id=site_id).count()
        bing_clicks = sum(
            r.clicks for r in s.query(BingQuery).filter_by(site_id=site_id).all()
            if r.date == date.today()
        )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric('Tracked Keywords', total_kws)
    c2.metric('Top 10 Rankings', top10)
    c3.metric('New Opportunities', new_opps, help='Invisible keywords discovered')
    c4.metric('New Competitor Pages', new_comp, delta_color='inverse')

    c5, c6, c7, c8 = st.columns(4)
    c5.metric('Backlinks (live)', backlinks)
    c6.metric('Open Audit Issues', open_issues, delta_color='inverse')
    c7.metric('AI Citations', f'{aio_cited}/{aio_total}' if aio_total else 'Run aeo',
              help='Queries where we are cited in AI Overviews/Bing Copilot')
    c8.metric('Bing Clicks Today', bing_clicks)

    # Recent report
    st.subheader('Latest Weekly Report')
    reports_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'reports')
    if os.path.exists(reports_dir):
        reports = sorted(os.listdir(reports_dir), reverse=True)
        if reports:
            report_path = os.path.join(reports_dir, reports[0])
            with open(report_path) as f:
                st.text(f.read())
        else:
            st.info('No reports yet. Run: python run.py report')
    else:
        st.info('Run python run.py report to generate your first report')

# ── KEYWORDS ──────────────────────────────────────────────────────────────────
elif '🎯 Keywords' in page:
    st.title(f'🎯 Keyword Tracking — {domain}')

    with get_session() as s:
        keywords = (s.query(Keyword)
                    .filter_by(site_id=site_id)
                    .order_by(Keyword.priority, Keyword.keyword)
                    .all())

    cluster_filter = st.selectbox('Cluster', ['All'] + list({k.cluster for k in keywords if k.cluster}))
    intent_filter  = st.selectbox('Intent',  ['All', 'commercial', 'near-commercial', 'informational'])

    # Bulk-load all rankings in 2 queries instead of 1 per keyword
    today    = date.today()
    week_ago = today - timedelta(days=7)
    with get_session() as s:
        today_ranks = {
            r.keyword_id: r for r in
            s.query(Ranking).join(Keyword)
             .filter(Keyword.site_id == site_id, Ranking.date == today).all()
        }
        week_ranks = {
            r.keyword_id: r for r in
            s.query(Ranking).join(Keyword)
             .filter(Keyword.site_id == site_id, Ranking.date == week_ago).all()
        }

    kw_data = []
    for kw in keywords:
        if cluster_filter != 'All' and kw.cluster != cluster_filter: continue
        if intent_filter  != 'All' and kw.intent  != intent_filter:  continue

        latest  = today_ranks.get(kw.id)
        prev_7d = week_ranks.get(kw.id)
        pos      = latest.position if latest else None
        pos_prev = prev_7d.position if prev_7d else None
        change   = round(pos - pos_prev, 1) if pos and pos_prev else None

        kw_data.append({
            'Keyword': kw.keyword,
            'Country': kw.country,
            'Cluster': kw.cluster or '',
            'Intent':  kw.intent or '',
            'Priority': kw.priority,
            'Position': pos or '-',
            '7-day change': change or '-',
            'URL': (latest.url or '').replace(f'https://{domain}', '')[:40] if latest else ''
        })

    if kw_data:
        import pandas as pd
        df = pd.DataFrame(kw_data)
        st.dataframe(df, use_container_width=True)
    else:
        st.info('No keywords match filter. Run: python run.py setup')

# ── RANKINGS ──────────────────────────────────────────────────────────────────
elif '🏆 Rankings' in page:
    st.title(f'🏆 Ranking History — {domain}')

    days_back = st.slider('Days to show', 7, 90, 30)

    with get_session() as s:
        recent_rankings = (s.query(Ranking, Keyword.keyword, Keyword.country)
                           .join(Keyword)
                           .filter(Keyword.site_id == site_id)
                           .filter(Ranking.date >= date.today() - timedelta(days=days_back))
                           .order_by(Ranking.position)
                           .limit(200).all())

    if recent_rankings:
        import pandas as pd
        data = [{'Keyword': kw, 'Country': co, 'Position': r.position or 'NR',
                 'Date': str(r.date), 'URL': (r.url or '').replace(f'https://{domain}', '')[:50],
                 'SERP Features': ', '.join(
                     k for k, v in (r.serp_features or {}).items() if v
                 ) or 'none'}
                for r, kw, co in recent_rankings]
        st.dataframe(pd.DataFrame(data), use_container_width=True)

        # SERP features trend chart
        st.subheader('SERP Feature Prevalence')
        feature_keys = ['featured_snippet', 'paa', 'video_pack', 'local_pack', 'sitelinks']
        feat_rows = []
        for r, kw, co in recent_rankings:
            feats = r.serp_features or {}
            feat_rows.append({'Date': r.date, **{k: int(bool(feats.get(k))) for k in feature_keys}})

        if feat_rows:
            feat_df = pd.DataFrame(feat_rows)
            feat_df['Date'] = pd.to_datetime(feat_df['Date'])
            daily = feat_df.groupby('Date')[feature_keys].sum().reset_index()
            daily = daily.set_index('Date')
            if not daily.empty and daily.values.sum() > 0:
                st.line_chart(daily)
                st.caption('Count of keywords with each SERP feature per day')
            else:
                st.info('No SERP feature data yet — requires rank tracking with VALUESERP_KEY')
    else:
        st.info('No ranking data yet. Add VALUESERP_KEY to .env and run: python run.py rank')

# ── COMPETITORS ───────────────────────────────────────────────────────────────
elif '🕵️ Competitors' in page:
    st.title(f'🕵️ Competitor Monitor — {domain}')

    with get_session() as s:
        competitors = s.query(Competitor).filter_by(site_id=site_id).all()

    for comp in competitors:
        with st.expander(f'🔍 {comp.domain}', expanded=False):
            with get_session() as s:
                urls = (s.query(CompetitorUrl)
                        .filter_by(competitor_id=comp.id)
                        .order_by(CompetitorUrl.first_seen.desc())
                        .limit(20).all())
                new_urls = [u for u in urls if u.is_new]

            st.write(f'**Total pages indexed:** {len(urls)}')
            if new_urls:
                st.warning(f'🆕 {len(new_urls)} NEW pages this week')
                for u in new_urls[:5]:
                    st.write(f'- [{u.title or u.url}]({u.url})')

# ── BACKLINKS ─────────────────────────────────────────────────────────────────
elif '🔗 Backlinks' in page:
    st.title(f'🔗 Backlink Monitor — {domain}')

    with get_session() as s:
        all_bl = s.query(Backlink).filter_by(site_id=site_id).order_by(Backlink.first_seen.desc()).all()
        live   = [b for b in all_bl if b.status == 'live']
        lost   = [b for b in all_bl if b.status == 'lost']

    col1, col2, col3 = st.columns(3)
    col1.metric('Live Backlinks', len(live))
    col2.metric('Lost Backlinks', len(lost), delta=-len(lost) if lost else 0, delta_color='inverse')

    # Weekly trend chart
    from analysis.backlink_trends import get_weekly_backlink_trends, get_backlink_ranking_correlation
    trends = get_weekly_backlink_trends(domain, weeks=12)
    if trends and any(t['gained'] + t['lost'] > 0 for t in trends):
        import pandas as pd
        trend_df = pd.DataFrame([{
            'Week': str(t['week']), 'Gained': t['gained'],
            'Lost': -t['lost'], 'Net': t['net']
        } for t in trends]).set_index('Week')
        st.subheader('Weekly Backlink Trends')
        st.bar_chart(trend_df[['Gained', 'Lost']])

        corr = get_backlink_ranking_correlation(domain, weeks=8)
        if corr and any(c['avg_position_change'] is not None for c in corr):
            st.subheader('Net Backlinks vs Avg Ranking Position')
            corr_df = pd.DataFrame([{
                'Week': str(c['week']),
                'Net Backlinks': c['net_backlinks'],
                'Avg Position': c['avg_position'],
            } for c in corr]).set_index('Week')
            st.line_chart(corr_df)
            st.caption('Lower position = higher rank. Watch for backlink gains correlating with position drops.')
    else:
        col3.metric('Trend', 'No data yet')

    if all_bl:
        import pandas as pd
        st.subheader('All Backlinks')
        data = [{'Source Domain': b.source_domain, 'Anchor': b.anchor_text or '',
                 'Target': (b.target_url or '').replace(f'https://{domain}', '')[:50],
                 'Status': b.status, 'First Seen': str(b.first_seen)}
                for b in all_bl[:100]]
        st.dataframe(pd.DataFrame(data), use_container_width=True)
    else:
        st.info('No backlink data yet. Run: python run.py collect')

# ── OPPORTUNITIES ─────────────────────────────────────────────────────────────
elif '📡 Opportunities' in page:
    st.title(f'📡 Keyword Opportunities — {domain}')
    st.caption('Keywords where you have zero visibility — these are your growth targets')

    status_filter = st.selectbox('Status', ['new', 'reviewing', 'brief_created', 'published', 'dismissed'])

    with get_session() as s:
        opps = (s.query(KeywordOpportunity)
                .filter_by(site_id=site_id, status=status_filter)
                .order_by(KeywordOpportunity.discovered_at.desc())
                .limit(100).all())

    if opps:
        import pandas as pd
        data = [{'Keyword': o.keyword, 'Intent': o.intent or '',
                 'KD Score': o.kd_score or '-', 'Volume Est': o.est_volume or '-',
                 'Source': o.source or '', 'Country': o.country,
                 'Discovered': str(o.discovered_at)}
                for o in opps]
        df = pd.DataFrame(data)
        st.dataframe(df, use_container_width=True)

        # Action buttons
        st.subheader('Quick Actions')
        if st.button('🚀 Run Keyword Discovery Now'):
            with st.spinner('Discovering keywords...'):
                from collectors.keyword_miner import run_keyword_discovery
                new = run_keyword_discovery(domain)
                st.success(f'Found {len(new)} new keyword opportunities!')
    else:
        st.info(f'No {status_filter} opportunities. Run: python run.py discover')

# ── COMMUNITY ─────────────────────────────────────────────────────────────────
elif '💬 Community' in page:
    st.title(f'💬 Community Opportunities — {domain}')
    st.caption('NRI legal questions on Reddit/Quora where you could provide expert answers')

    with get_session() as s:
        mentions = (s.query(Mention)
                    .filter_by(site_id=site_id, is_answered=False)
                    .order_by(Mention.discovered_at.desc())
                    .limit(30).all())

    filter_questions = st.checkbox('Show only unanswered questions', value=True)
    shown = [m for m in mentions if (not filter_questions or m.has_question)]

    for m in shown[:20]:
        with st.expander(f'[{m.platform.upper()}] {m.title[:80]}', expanded=False):
            st.write(m.snippet or 'No preview available')
            if m.source_url:
                st.write(f'[View on {m.platform}]({m.source_url})')
            if st.button(f'Mark Answered', key=f'answered_{m.id}'):
                with get_session() as s:
                    mention = s.query(Mention).get(m.id)
                    if mention:
                        mention.is_answered = True; s.commit()
                st.success('Marked as answered!')

    if not shown:
        st.info('No community mentions yet. Run: python run.py collect')

# ── AUDIT ─────────────────────────────────────────────────────────────────────
elif '🔧 Audit' in page:
    st.title(f'🔧 SEO Audit — {domain}')

    with get_session() as s:
        issues = (s.query(AuditIssue)
                  .filter_by(site_id=site_id)
                  .order_by(AuditIssue.detected_at.desc())
                  .limit(200).all())

    sev_filter = st.selectbox('Severity', ['all', 'critical', 'warning', 'info'])
    status_f   = st.selectbox('Status', ['open', 'fixed', 'ignored'])

    filtered = [i for i in issues
                if (sev_filter == 'all' or i.severity == sev_filter)
                and i.status == status_f]

    crit  = sum(1 for i in issues if i.severity == 'critical' and i.status == 'open')
    warn  = sum(1 for i in issues if i.severity == 'warning'  and i.status == 'open')
    info  = sum(1 for i in issues if i.severity == 'info'     and i.status == 'open')

    c1, c2, c3 = st.columns(3)
    c1.metric('Critical Issues', crit, delta_color='inverse')
    c2.metric('Warnings', warn, delta_color='inverse')
    c3.metric('Info', info)

    for issue in filtered[:50]:
        icon = '🔴' if issue.severity == 'critical' else ('🟡' if issue.severity == 'warning' else 'ℹ️')
        with st.expander(f'{icon} {issue.issue_type} — {(issue.page_url or "").replace(f"https://{domain}", "")[:60]}'):
            st.write(f'**Problem:** {issue.description}')
            st.write(f'**Fix:** {issue.remediation}')
            st.write(f'**Detected:** {issue.detected_at}')
            if st.button('Mark Fixed', key=f'fix_{issue.id}'):
                with get_session() as s:
                    i = s.query(AuditIssue).get(issue.id)
                    if i: i.status = 'fixed'; s.commit()
                st.success('Marked as fixed!')

    if not filtered:
        st.info(f'No {sev_filter} {status_f} issues. Run: python run.py analyse')

# ── AI VISIBILITY ─────────────────────────────────────────────────────────────
elif '🤖 AI Visibility' in page:
    st.title(f'🤖 AI Visibility — {domain}')
    st.caption(f'Track where {domain} appears in AI-generated answers')

    tab1, tab2, tab3 = st.tabs(['📊 Overview', '📝 Manual Log', '📈 Trends'])

    with tab1:
        with get_session() as s:
            all_aeo = s.query(AeoResult).filter_by(site_id=site_id).order_by(
                AeoResult.date.desc()
            ).limit(200).all()

        if all_aeo:
            import pandas as pd
            engines = sorted({r.engine for r in all_aeo})
            engine_filter = st.multiselect('Engine', engines, default=engines)
            shown = [r for r in all_aeo if r.engine in engine_filter]

            total  = len(shown)
            cited  = sum(1 for r in shown if r.is_cited)
            pct    = cited / total * 100 if total else 0

            col1, col2, col3 = st.columns(3)
            col1.metric('Total AEO Checks', total)
            col2.metric('Times Cited', cited)
            col3.metric('Citation Rate', f'{pct:.0f}%')

            data = [{'Query': r.query, 'Engine': r.engine,
                     'Cited': '✅' if r.is_cited else '❌',
                     'Snippet': (r.raw_snippet or '')[:80],
                     'Date': str(r.date)} for r in shown[:100]]
            st.dataframe(pd.DataFrame(data), use_container_width=True)
        else:
            st.info('No AEO data yet. Run: python run.py aeo')
            st.code('python run.py aeo')

    with tab2:
        st.subheader('Log Manual AEO Check')
        st.caption('For ChatGPT/Gemini/Perplexity — check manually and log the result here')
        col1, col2 = st.columns(2)
        with col1:
            manual_query  = st.text_input('Query you searched')
            manual_engine = st.selectbox('Engine', ['chatgpt', 'gemini', 'perplexity', 'copilot', 'grok'])
        with col2:
            manual_cited  = st.checkbox('Was our site cited/mentioned?')
            manual_url    = st.text_input('Which page URL was cited (if any)')
        if st.button('Log Result') and manual_query:
            from collectors.aeo_tracker import log_manual_aeo
            ok = log_manual_aeo(domain, manual_query, manual_engine, manual_cited, manual_url)
            st.success('Logged!' if ok else 'Error logging — check DB')

    with tab3:
        with get_session() as s:
            all_aeo = s.query(AeoResult).filter_by(site_id=site_id).order_by(
                AeoResult.date.asc()
            ).all()
        if all_aeo:
            import pandas as pd
            trend_df = pd.DataFrame([{
                'Date': r.date, 'Engine': r.engine, 'Cited': int(r.is_cited)
            } for r in all_aeo])
            trend_df['Date'] = pd.to_datetime(trend_df['Date'])
            pivot = trend_df.groupby(['Date', 'Engine'])['Cited'].sum().unstack(fill_value=0)
            if not pivot.empty:
                st.subheader('Citations per Engine Over Time')
                st.line_chart(pivot)
        else:
            st.info('No trend data yet.')

    # Bing WMT summary
    st.subheader('Bing Search Performance')
    with get_session() as s:
        bing_rows = (s.query(BingQuery).filter_by(site_id=site_id)
                     .order_by(BingQuery.date.desc(), BingQuery.clicks.desc())
                     .limit(50).all())
    if bing_rows:
        import pandas as pd
        bdf = pd.DataFrame([{
            'Query': r.query, 'Clicks': r.clicks,
            'Impressions': r.impressions, 'CTR %': round((r.ctr or 0) * 100, 2),
            'Avg Position': r.avg_position, 'Date': str(r.date),
        } for r in bing_rows])
        st.dataframe(bdf, use_container_width=True)
    else:
        st.info('No Bing data yet. Set BING_WMT_API_KEY in .env then run: python run.py collect')


# ── SITE AUDIT ────────────────────────────────────────────────────────────────
elif '🔍 Site Audit' in page:
    st.title(f'🔍 Technical Site Audit — {domain}')
    st.caption('Screaming Frog equivalent — crawls all 187 pages for technical issues')

    with get_session() as s:
        crawl_pages = (s.query(SiteCrawlPage).filter_by(site_id=site_id)
                       .order_by(SiteCrawlPage.crawled_at.desc()).all())

    if not crawl_pages:
        st.info('No audit data yet. Run: python run.py audit')
        if st.button('🔍 Run Site Audit Now'):
            with st.spinner('Crawling 187 pages... (30-60 seconds)'):
                from audit.site_crawler import run_site_audit
                result = run_site_audit(domain)
                st.success(f'Done: {result["pages_audited"]} pages | {result["critical"]} critical | {result["warnings"]} warnings')
                st.rerun()
    else:
        import pandas as pd
        # Issue summary
        all_issues = [iss for p in crawl_pages for iss in (p.issues or [])]
        from collections import Counter
        issue_counts = Counter(all_issues)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric('Pages Audited', len(crawl_pages))
        critical = sum(1 for p in crawl_pages for i in (p.issues or [])
                       if i in ('missing_title', 'missing_h1', 'thin_content',
                                 'noindex_page', 'broken_internal_links', 'missing_meta_desc'))
        c2.metric('Critical Issues', critical, delta_color='inverse')
        c3.metric('Pages with Schema', sum(1 for p in crawl_pages if p.has_schema))
        c4.metric('Avg Word Count', int(sum(p.word_count or 0 for p in crawl_pages) / max(len(crawl_pages), 1)))

        # Issue breakdown
        st.subheader('Issue Breakdown')
        if issue_counts:
            issue_df = pd.DataFrame(
                [{'Issue': k, 'Pages Affected': v, 'Severity': 'Critical' if k in
                  ('missing_title','missing_h1','thin_content','noindex_page','broken_internal_links','missing_meta_desc')
                  else 'Warning'}
                 for k, v in sorted(issue_counts.items(), key=lambda x: -x[1])]
            )
            st.dataframe(issue_df, use_container_width=True)

        # Filter and show pages
        sev_filter = st.selectbox('Filter by issue', ['All'] + list(issue_counts.keys()))
        if sev_filter == 'All':
            shown = [p for p in crawl_pages if p.issues]
        else:
            shown = [p for p in crawl_pages if sev_filter in (p.issues or [])]

        if shown:
            df = pd.DataFrame([{
                'URL': p.url.replace(f'https://{domain}', '')[:50],
                'Title': (p.title or '')[:50],
                'Words': p.word_count,
                'H1s': p.h1_count,
                'Schema': '✅' if p.has_schema else '❌',
                'Issues': ', '.join(p.issues or [])[:60],
            } for p in shown[:100]])
            st.dataframe(df, use_container_width=True)


# ── PAGESPEED ─────────────────────────────────────────────────────────────────
elif '⚡ PageSpeed' in page:
    st.title(f'⚡ Core Web Vitals — {domain}')
    st.caption('Google PageSpeed Insights — free API, no auth required')

    with get_session() as s:
        ps_rows = (s.query(PageSpeed).filter_by(site_id=site_id)
                   .order_by(PageSpeed.date.desc(), PageSpeed.performance.asc())
                   .limit(100).all())

    if not ps_rows:
        st.info('No PageSpeed data yet. Run: python run.py pagespeed')
        if st.button('⚡ Run PageSpeed Audit Now'):
            with st.spinner('Checking 10 pages × 2 strategies... (takes ~3 min)'):
                from collectors.pagespeed import run_pagespeed_audit
                run_pagespeed_audit(domain)
                st.rerun()
    else:
        import pandas as pd
        strategy = st.radio('Strategy', ['mobile', 'desktop'], horizontal=True)
        filtered = [r for r in ps_rows if r.strategy == strategy]

        if filtered:
            avg_score = int(sum(r.performance or 0 for r in filtered) / len(filtered))
            poor = sum(1 for r in filtered if (r.performance or 0) < 50)
            good = sum(1 for r in filtered if (r.performance or 0) >= 90)

            c1, c2, c3 = st.columns(3)
            c1.metric(f'Avg {strategy.title()} Score', f'{avg_score}/100',
                      delta='Good' if avg_score >= 75 else 'Needs work',
                      delta_color='normal' if avg_score >= 75 else 'inverse')
            c2.metric('Poor Pages (<50)', poor, delta_color='inverse')
            c3.metric('Good Pages (90+)', good)

            df = pd.DataFrame([{
                'Page': r.page_url.replace(f'https://{domain}', '')[:45],
                'Score': r.performance or '-',
                'LCP (s)': f'{r.lcp:.1f}' if r.lcp else '-',
                'CLS': f'{r.cls:.3f}' if r.cls else '-',
                'INP (ms)': f'{r.inp:.0f}' if r.inp else '-',
                'TTFB (ms)': f'{r.ttfb:.0f}' if r.ttfb else '-',
                'Date': str(r.date),
            } for r in filtered])
            st.dataframe(df.sort_values('Score'), use_container_width=True)

            # Score distribution chart
            scores = [r.performance for r in filtered if r.performance]
            if scores:
                st.subheader('Score Distribution')
                score_df = pd.DataFrame({'Score': scores})
                st.bar_chart(score_df['Score'].value_counts().sort_index())


# ── SERP ANALYSIS ─────────────────────────────────────────────────────────────
elif '📊 SERP Analysis' in page:
    st.title(f'📊 SERP Top-10 Analysis — {domain}')
    st.caption('"What does it take to outrank position 1?" — word count, backlinks, schema')

    with get_session() as s:
        keywords_analysed = s.query(SerpAnalysisResult.keyword).filter_by(
            site_id=site_id).distinct().all()
        keywords_list = [k[0] for k in keywords_analysed]

    if not keywords_list:
        st.info('No SERP analysis yet. Run: python run.py serp')
        if st.button('📊 Analyse SERPs Now'):
            with st.spinner('Analysing top-10 for 5 keywords...'):
                from analysis.serp_analyzer import run_serp_analyser
                run_serp_analyser(domain, max_keywords=5)
                st.rerun()
    else:
        import pandas as pd
        kw_select = st.selectbox('Keyword', keywords_list)

        with get_session() as s:
            rows = (s.query(SerpAnalysisResult)
                    .filter_by(site_id=site_id, keyword=kw_select)
                    .order_by(SerpAnalysisResult.position).all())

        if rows:
            top3 = [r for r in rows if r.position <= 3]
            avg_wc  = int(sum(r.word_count or 0 for r in top3) / max(len(top3), 1))
            schemas = sum(1 for r in top3 if r.has_schema)
            faqs    = sum(1 for r in top3 if r.has_faq)
            our_row = next((r for r in rows if r.is_our_domain), None)

            st.subheader(f'To rank top 3 for: "{kw_select}"')
            c1, c2, c3, c4 = st.columns(4)
            c1.metric('Avg Words (top 3)', f'{avg_wc}+')
            c2.metric('Schema needed', f'{schemas}/3 have it')
            c3.metric('FAQ needed', f'{faqs}/3 have it')
            c4.metric('Our position', our_row.position if our_row else 'Not in top 10')

            df = pd.DataFrame([{
                'Pos': r.position,
                'Domain': r.domain[:30],
                'Title': (r.title or '')[:45],
                'Words': r.word_count or '-',
                'Backlinks': r.backlink_count or '-',
                'Schema': '✅' if r.has_schema else '❌',
                'FAQ': '✅' if r.has_faq else '❌',
                'Us': '⭐' if r.is_our_domain else '',
            } for r in rows])
            st.dataframe(df, use_container_width=True)

    # Visibility / Share of Voice
    st.divider()
    st.subheader('📈 Share of Voice (Search Visibility)')
    with get_session() as s:
        sov_rows = (s.query(VisibilityScore).filter_by(site_id=site_id)
                    .order_by(VisibilityScore.date.desc()).limit(50).all())
    if sov_rows:
        import pandas as pd
        latest_date = max(r.date for r in sov_rows)
        latest = [r for r in sov_rows if r.date == latest_date]
        latest.sort(key=lambda x: -(x.score or 0))
        for r in latest:
            marker = '⭐ **Us**' if r.domain == domain else r.domain
            col1, col2 = st.columns([3, 1])
            col1.progress(min(1.0, (r.score or 0) / 100), text=f'{marker} — {r.score:.2f}%')
            col2.write(f'~{r.traffic_est:,}/mo')
    else:
        st.info('No visibility data yet. Run: python run.py analyse')


# ── ALERTS ────────────────────────────────────────────────────────────────────
elif '🚨 Alerts' in page:
    st.title(f'🚨 Alerts — {domain}')
    st.caption('Rank drops, lost backlinks, competitor pages, PageSpeed drops, site uptime')

    with get_session() as s:
        all_alerts = (s.query(Alert).filter_by(site_id=site_id)
                      .order_by(Alert.created_at.desc()).limit(100).all())
        unread = sum(1 for a in all_alerts if not a.is_read)

    col1, col2 = st.columns(2)
    col1.metric('Total Alerts', len(all_alerts))
    col2.metric('Unread', unread, delta_color='inverse' if unread > 0 else 'normal')

    if st.button('✅ Mark All Read'):
        with get_session() as s:
            for a in s.query(Alert).filter_by(site_id=site_id, is_read=False).all():
                a.is_read = True
            s.commit()
        st.success('All marked as read')

    if st.button('🔔 Run Alert Check Now'):
        with st.spinner('Checking for alerts...'):
            from alerts.alert_engine import run_alerts
            result = run_alerts(domain)
            st.success(f'{result.get("total", 0)} alert(s) detected')
            st.rerun()

    sev_filter = st.selectbox('Severity', ['all', 'critical', 'warning', 'info'])
    type_filter = st.selectbox('Type', ['all', 'rank_drop', 'lost_backlink',
                                         'competitor_page', 'pagespeed_drop', 'site_down'])

    shown = [a for a in all_alerts
             if (sev_filter == 'all' or a.severity == sev_filter)
             and (type_filter == 'all' or a.alert_type == type_filter)]

    for alert in shown[:50]:
        icon = {'critical': '🔴', 'warning': '🟡', 'info': 'ℹ️'}.get(alert.severity, '•')
        read_marker = '' if alert.is_read else '**NEW** '
        with st.expander(f'{icon} {read_marker}{alert.alert_type.replace("_", " ").title()} — {str(alert.created_at)[:16]}'):
            st.write(alert.message)
            if alert.details:
                st.json(alert.details)
            if st.button('Mark Read', key=f'read_{alert.id}'):
                with get_session() as s:
                    a = s.query(Alert).get(alert.id)
                    if a:
                        a.is_read = True
                        s.commit()

    if not shown:
        st.success('No alerts matching filter. ✅')


# ── REPORTS ───────────────────────────────────────────────────────────────────
elif '📄 Reports' in page:
    st.title(f'📄 Weekly Reports — {domain}')

    reports_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'reports')
    if os.path.exists(reports_dir):
        report_files = sorted(os.listdir(reports_dir), reverse=True)
        if report_files:
            selected = st.selectbox('Select Report', report_files)
            with open(os.path.join(reports_dir, selected)) as f:
                content = f.read()
            st.text_area('Report', content, height=800)
            st.download_button('Download', content, file_name=selected)
        else:
            st.info('No reports yet. Run: python run.py report')

    if st.button('🚀 Generate Report Now'):
        with st.spinner('Generating...'):
            from report.builder import build_and_send
            report = build_and_send(domain)
            st.success('Report generated!')
            st.text_area('New Report', report, height=600)
