"""
RankPilot — Weekly Report Builder
Generates a comprehensive, plain-English weekly SEO brief.
Covers: leads, search performance, rankings, countries, competitors,
        content gaps, keyword opportunities, E-E-A-T, backlinks, community.
"""
import os, sys, json
from datetime import datetime, date, timezone, timedelta
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import TARGET_DOMAIN, COMPETITORS
from core.db import (get_session, Site, GscQuery, GscPage, GscQuery,
                     Ranking, Keyword, KeywordOpportunity, CompetitorUrl,
                     Backlink, Mention, AuditIssue, Ga4Session, AeoResult, BingQuery,
                     SiteCrawlPage, PageSpeed, VisibilityScore, Alert)

COMMERCIAL_KWS = [
    'nri property lawyer', 'nri property dispute lawyer india', 'nri property dispute lawyer',
    'nri criminal lawyer india', 'nri criminal lawyer', 'nri divorce lawyer india',
    'nri divorce lawyer', 'power of attorney for nri', 'power of attorney for nri india',
    '498a nri husband', '498a against nri husband', 'nri inheritance lawyer india',
    'nri inheritance lawyer', 'nri sell property india', 'nri legal services',
    'nri legal services delhi', 'example legal firm', 'nri lawyer delhi',
    'nri lawyer india', 'fir quashing for nri', 'anticipatory bail for nri',
]

COUNTRY_NAMES = {
    'IND': 'India', 'USA': 'USA', 'CAN': 'Canada', 'GBR': 'UK',
    'ARE': 'UAE', 'AUS': 'Australia', 'SGP': 'Singapore', 'SAU': 'Saudi Arabia',
    'NZL': 'New Zealand', 'DEU': 'Germany'
}
HIGH_VALUE = {'USA', 'CAN', 'GBR', 'ARE', 'AUS', 'SGP'}

def sep(char='─', width=60): return char * width

def pct(old, new):
    if not old: return f'(new: {new})' if new else ''
    diff = new - old; p = diff/old*100
    sym = '↑' if diff > 0 else ('↓' if diff < 0 else '→')
    return f'{sym} {abs(p):.0f}%  (was {old:,})'

def pos_arrow(old, new):
    if old is None: return '🆕 new'
    d = new - old
    if abs(d) < 0.5: return '→ same'
    return f'{"↑" if d < 0 else "↓"} {abs(d):.0f}  (was {old:.0f})'

def page_rank_label(pos):
    if pos is None: return 'Not found ❌'
    if pos <= 3:  return f'Page 1 Top 3 ✅  (pos {pos:.0f})'
    if pos <= 10: return f'Page 1 ✅  (pos {pos:.0f})'
    if pos <= 20: return f'Page 2 🟡  (pos {pos:.0f})'
    if pos <= 30: return f'Page 3 🟠  (pos {pos:.0f})'
    return f'Page {int(pos/10)+1} ❌  (pos {pos:.0f})'

def classify_intent(query: str) -> str:
    q = query.lower()
    commercial_signals = ['lawyer', 'advocate', 'legal help', 'legal services',
                          'consult', 'hire', 'attorney', 'legal advice']
    near_commercial = ['property', 'dispute', 'inheritance', 'divorce', '498a',
                       'bail', 'fir', 'passport', 'oci', 'power of attorney', 'proclaimed']
    if any(s in q for s in commercial_signals): return 'commercial'
    if 'nri' in q and any(s in q for s in near_commercial): return 'near-commercial'
    return 'informational'

def _load_gsc_from_db(site_id: int) -> dict:
    """Build gsc_data dict from DB when no live fetch is available.
    Uses only the most recent stored period date to avoid summing across multiple collect runs."""
    today    = date.today()
    week_ago = today - timedelta(days=7)
    two_weeks_ago = today - timedelta(days=14)
    from sqlalchemy import func
    with get_session() as s:
        # Use only the most recent stored date for each period to avoid double-counting
        this_date = s.query(func.max(GscQuery.date)).filter(
            GscQuery.site_id == site_id,
            GscQuery.date >= week_ago
        ).scalar()
        prev_date = s.query(func.max(GscQuery.date)).filter(
            GscQuery.site_id == site_id,
            GscQuery.date >= two_weeks_ago,
            GscQuery.date < week_ago
        ).scalar()
        this_q = s.query(GscQuery).filter(
            GscQuery.site_id == site_id,
            GscQuery.date == this_date
        ).all() if this_date else []
        prev_q = s.query(GscQuery).filter(
            GscQuery.site_id == site_id,
            GscQuery.date == prev_date
        ).all() if prev_date else []
        this_p_date = s.query(func.max(GscPage.date)).filter(
            GscPage.site_id == site_id,
            GscPage.date >= week_ago
        ).scalar()
        prev_p_date = s.query(func.max(GscPage.date)).filter(
            GscPage.site_id == site_id,
            GscPage.date >= two_weeks_ago,
            GscPage.date < week_ago
        ).scalar()
        this_p = s.query(GscPage).filter(
            GscPage.site_id == site_id,
            GscPage.date == this_p_date
        ).all() if this_p_date else []
        prev_p = s.query(GscPage).filter(
            GscPage.site_id == site_id,
            GscPage.date == prev_p_date
        ).all() if prev_p_date else []

    def agg_queries(rows):
        d = {}
        for r in rows:
            k = r.query.lower()
            if k not in d:
                d[k] = {'clicks': 0, 'impressions': 0, 'position': r.position or 0, 'ctr': 0}
            d[k]['clicks']      += r.clicks or 0
            d[k]['impressions'] += r.impressions or 0
        return d

    def agg_pages(rows):
        d = {}
        for r in rows:
            k = r.page
            if k not in d:
                d[k] = {'clicks': 0, 'impressions': 0, 'position': r.position or 0}
            d[k]['clicks']      += r.clicks or 0
            d[k]['impressions'] += r.impressions or 0
        return d

    return {
        'this': {'queries': agg_queries(this_q), 'pages': agg_pages(this_p),
                 'start': week_ago.isoformat(), 'end': today.isoformat()},
        'prev': {'queries': agg_queries(prev_q), 'pages': agg_pages(prev_p),
                 'start': two_weeks_ago.isoformat(), 'end': (week_ago - timedelta(days=1)).isoformat()},
    }


def _load_ga4_from_db(site_id: int) -> dict | None:
    """Build ga4_data dict from DB rows."""
    today = date.today()
    with get_session() as s:
        rows = s.query(Ga4Session).filter(
            Ga4Session.site_id == site_id,
            Ga4Session.date >= today - timedelta(days=7)
        ).all()
    if not rows:
        return None
    total_sessions  = sum(r.sessions or 0 for r in rows)
    total_conv      = sum(r.conversions or 0 for r in rows)
    events_combined = {}
    for r in rows:
        for k, v in (r.events or {}).items():
            events_combined[k] = events_combined.get(k, 0) + v
    return {
        'this': events_combined,
        'prev': {},
        'sessions': {'this': total_sessions, 'prev': 0},
        'landing_pages': [],
        'sources': {r.channel: r.sessions for r in rows if r.channel},
    }


def build_report(site_domain: str = TARGET_DOMAIN,
                 gsc_data: dict = None, ga4_data: dict = None) -> str:
    """Build the full weekly Markdown report."""

    now = datetime.now(timezone.utc)
    lines = []
    alerts = []

    # Load from DB if not passed in directly
    with get_session() as s:
        _site = s.query(Site).filter_by(domain=site_domain).first()
        _sid  = _site.id if _site else None
    if _sid and gsc_data is None:
        gsc_data = _load_gsc_from_db(_sid)
    if _sid and ga4_data is None:
        ga4_data = _load_ga4_from_db(_sid)

    # Header — show exact reporting dates so it's clear what's being compared
    _this_start = gsc_data['this'].get('start', '') if gsc_data else ''
    _this_end   = gsc_data['this'].get('end', '') if gsc_data else ''
    _prev_start = gsc_data['prev'].get('start', '') if gsc_data else ''
    _prev_end   = gsc_data['prev'].get('end', '') if gsc_data else ''
    header_lines = [
        '━' * 60,
        f'  RANKPILOT WEEKLY SEO BRIEF — {site_domain}',
    ]
    if _this_start and _this_end:
        header_lines.append(f'  Reporting period:  {_this_start} → {_this_end}')
    if _prev_start and _prev_end:
        header_lines.append(f'  Comparison to:     {_prev_start} → {_prev_end}  (prior week)')
    if not _this_start:
        header_lines.append(f'  Week ending: {now.strftime("%d %B %Y")}')
    try:
        from analysis.share_of_voice import calculate_share_of_voice
        _sov = calculate_share_of_voice(site_domain)
        if _sov and _sov.get('our_score') is not None:
            header_lines.append(
                f'  Share of Voice:  {_sov["our_score"]:.1f}%'
                f'  (est. {_sov["our_traffic"]:,} organic visits/month)'
            )
    except Exception:
        pass
    header_lines.append('━' * 60)
    lines += header_lines

    # ── SECTION 1: LEADS ──────────────────────────────────────────────────────
    if ga4_data:
        t = ga4_data['this']; p = ga4_data['prev']
        forms = t.get('contact_form_submit', 0); pf = p.get('contact_form_submit', 0)
        wa    = t.get('whatsapp_click', 0);      pw = p.get('whatsapp_click', 0)
        phone = t.get('phone_click', 0);         pp = p.get('phone_click', 0)
        total = forms + wa + phone; ptotal = pf + pw + pp
        sess_t = ga4_data['sessions'].get('this', 0)
        sess_p = ga4_data['sessions'].get('prev', 0)
        lr = f'{total/sess_t*100:.1f}%' if sess_t else 'n/a'
        lines += ['', '📞 HOW MANY PEOPLE CONTACTED YOU THIS WEEK?', sep(),
                  f'  Contact form:      {forms:<5} {pct(pf, forms)}',
                  f'  WhatsApp clicked:  {wa:<5} {pct(pw, wa)}',
                  f'  Phone clicked:     {phone:<5} {pct(pp, phone)}',
                  f'  {sep("─", 44)}',
                  f'  TOTAL LEADS:       {total:<5} {pct(ptotal, total)}',
                  f'  Sessions:          {sess_t:,}   {pct(sess_p, sess_t)}',
                  f'  Lead rate:         {lr}  (leads per 100 visitors)']
        if total == 0:
            alerts.append('🔴 ZERO LEADS this week — check form + WhatsApp button')
        if ga4_data.get('landing_pages'):
            best = sorted(ga4_data['landing_pages'], key=lambda x: -x.get('events', 0))
            if best:
                slug = best[0]['page'].replace(f'https://{site_domain}', '') or '/'
                lines.append(f'  Best page for leads: {slug}')
    else:
        lines += ['', '📞 LEADS: Configure GA4_PROPERTY_ID in .env to track leads', '']

    # ── SECTION 2: SEARCH PERFORMANCE ────────────────────────────────────────
    if gsc_data:
        tq = gsc_data['this']['queries']; pq = gsc_data['prev']['queries']
        tp = gsc_data['this']['pages'];   pp_pages = gsc_data['prev']['pages']
        t_clicks = sum(v['clicks'] for v in tq.values())
        p_clicks = sum(v['clicks'] for v in pq.values())
        t_imp    = sum(v['impressions'] for v in tq.values())
        p_imp    = sum(v['impressions'] for v in pq.values())
        t_ctr    = t_clicks / t_imp * 100 if t_imp else 0
        p_ctr    = p_clicks / p_imp * 100 if p_imp else 0
        t_pos    = (sum(v['position']*v['impressions'] for v in tq.values())/t_imp) if t_imp else 0

        lines += ['', '🔍 HOW MANY PEOPLE FOUND YOU ON GOOGLE THIS WEEK?', sep(),
                  f'  People who clicked:   {t_clicks:,}    {pct(p_clicks, t_clicks)}',
                  f'  People who saw you:   {t_imp:,}    {pct(p_imp, t_imp)}',
                  f'  % who clicked (CTR):  {t_ctr:.2f}%    (industry avg: 3%)',
                  f'  Avg position:         {t_pos:.1f}',
                  '',
                  f'  What this means: Google showed you to {t_imp:,} people.',
                  f'  At 3% CTR you would get {int(t_imp*0.03):,} clicks/week instead of {t_clicks}.']

        if t_ctr < 1.0:
            alerts.append(f'🟡 CTR is {t_ctr:.2f}% — rewrite page titles (goal: 2%+)')

    # ── SECTION 3: COUNTRIES ──────────────────────────────────────────────────
    if gsc_data and gsc_data.get('this', {}).get('countries'):
        countries = gsc_data['this']['countries']
        lines += ['', '🌍 WHERE ARE YOUR VISITORS COMING FROM?', sep()]
        lines.append(f'  {"COUNTRY":<14} {"CLICKS":>7}  {"SAW YOU":>9}  {"CLICK%":>7}  NOTE')
        lines.append(f'  {sep("─", 52)}')
        for code, data in sorted(countries.items(), key=lambda x: -x[1]['clicks'])[:8]:
            name = COUNTRY_NAMES.get(code, code)
            note = 'HIGH VALUE ⭐' if code in HIGH_VALUE else ('Most traffic (lower value)' if code == 'IND' else '')
            ctr_flag = ' ⚠️' if code in HIGH_VALUE and data['ctr'] < 0.5 else ''
            lines.append(f'  {name:<14} {data["clicks"]:>7,}  {data["impressions"]:>9,}  {data["ctr"]:>6.2f}%{ctr_flag}  {note}')
        # USA alert
        usa = countries.get('USA', countries.get('US', {}))
        if usa and usa.get('ctr', 99) < 0.5 and usa.get('impressions', 0) > 500:
            alerts.append(f'⚠️ USA CTR is {usa["ctr"]:.2f}% on {usa["impressions"]:,} impressions — add "for USA NRIs" to service page titles')

    # ── SECTION 3b: MOBILE vs DESKTOP ────────────────────────────────────────
    if gsc_data and gsc_data.get('this', {}).get('devices'):
        devices = gsc_data['this']['devices']
        total_dev_clicks = sum(d['clicks'] for d in devices.values()) or 1
        lines += ['', '📱 MOBILE vs DESKTOP', sep()]
        order = ['MOBILE', 'DESKTOP', 'TABLET']
        for dev in order:
            d = devices.get(dev, {})
            if not d and not any(k.startswith(dev[:3]) for k in devices):
                continue
            # normalise key (API may return 'MOBILE', 'DESKTOP', 'TABLET')
            d = devices.get(dev, devices.get(dev.capitalize(), {}))
            clk = d.get('clicks', 0)
            pct_share = clk / total_dev_clicks * 100
            bar = '█' * int(pct_share / 5)
            lines.append(f'  {dev:<10}: {pct_share:>3.0f}% of traffic  ({clk:,} clicks)  {bar}')

    # ── SECTION 4: TOP PAGES ──────────────────────────────────────────────────
    if gsc_data:
        tp = gsc_data['this']['pages']
        pp_pages = gsc_data['prev']['pages']
        lines += ['', '📈 YOUR BEST PAGES THIS WEEK', sep()]
        lines.append(f'  {"PAGE":<52} {"CLICKS":>6}  CHANGE')
        lines.append(f'  {sep("─", 62)}')
        for url, v in sorted(tp.items(), key=lambda x: -x[1]['clicks'])[:10]:
            slug = url.replace(f'https://{site_domain}', '') or '/'
            prev_v = next((pv for pu, pv in pp_pages.items() if slug in pu), {})
            ch = pct(prev_v.get('clicks', 0), v['clicks']) if prev_v else ''
            lines.append(f'  {slug[:52]:<52} {v["clicks"]:>6,}  {ch}')

    # ── SECTION 4b: STRIKING-DISTANCE QUERIES ────────────────────────────────
    # Queries at position 5-20 with >50 impressions and <3% CTR — fastest path to clicks
    if _sid:
        from sqlalchemy import func as _func
        with get_session() as s:
            _latest = s.query(_func.max(GscQuery.date)).filter(
                GscQuery.site_id == _sid
            ).scalar()
            sd_rows = []
            if _latest:
                # Aggregate across device/country/page dimensions
                agg = s.query(
                    GscQuery.query,
                    _func.sum(GscQuery.impressions).label('total_impressions'),
                    _func.sum(GscQuery.clicks).label('total_clicks'),
                    (_func.sum(GscQuery.position * GscQuery.impressions) /
                     _func.sum(GscQuery.impressions)).label('avg_position'),
                ).filter(
                    GscQuery.site_id == _sid,
                    GscQuery.date == _latest,
                ).group_by(GscQuery.query).all()

                for row in agg:
                    imp = row.total_impressions or 0
                    clk = row.total_clicks or 0
                    pos = row.avg_position or 0
                    if imp >= 50 and 5 <= pos <= 20 and (clk / imp if imp else 1) < 0.03:
                        sd_rows.append({
                            'query': row.query,
                            'impressions': imp,
                            'clicks': clk,
                            'position': pos,
                            'score': int(imp * (20 - pos)),
                        })
                sd_rows.sort(key=lambda r: -r['score'])

        if sd_rows:
            lines += ['', '🎯 QUICK WINS — STRIKING DISTANCE KEYWORDS', sep(),
                      '  You\'re on page 1-2 for these. Small title/meta tweak = immediate clicks.',
                      '  Score = impressions × (20 − position). Higher = bigger opportunity.',
                      '',
                      f'  {"QUERY":<42} {"IMPR":>6}  {"POS":>6}  {"CTR":>6}  {"SCORE":>7}']
            lines.append(f'  {sep("─", 72)}')
            for r in sd_rows[:15]:
                ctr_pct = r['clicks'] / r['impressions'] * 100 if r['impressions'] else 0
                lines.append(
                    f'  {r["query"][:42]:<42} {r["impressions"]:>6,}  {r["position"]:>6.1f}  '
                    f'{ctr_pct:>5.1f}%  {r["score"]:>7,}'
                )
            lines.append('')
            lines.append('  Fix: rewrite title to match search intent. Add FAQ schema to boost CTR.')
            if sd_rows[0]['score'] > 500:
                top = sd_rows[0]
                ctr_top = top['clicks'] / top['impressions'] * 100 if top['impressions'] else 0
                alerts.append(
                    f'🟡 Top striking-distance query: "{top["query"]}" '
                    f'({top["impressions"]:,} impr, pos {top["position"]:.1f}, '
                    f'{ctr_top:.1f}% CTR) — rewrite title/meta to capture these clicks'
                )

    # ── SECTION 5: COMMERCIAL KEYWORD RANKINGS ────────────────────────────────
    if gsc_data:
        tq = gsc_data['this']['queries']; pq = gsc_data['prev']['queries']
        # Build volume lookup from Keyword table (GSC-estimated monthly)
        kw_volumes: dict[str, int] = {}
        with get_session() as s:
            _site = s.query(Site).filter_by(domain=site_domain).first()
            if _site:
                from core.db import Keyword as KwModel
                for row in s.query(KwModel).filter_by(site_id=_site.id).all():
                    if row.volume:
                        kw_volumes[row.keyword.lower()] = row.volume
        lines += ['', '━' * 60,
                  '🎯 KEYWORDS YOUR POTENTIAL CLIENTS SEARCH',
                  '━' * 60, '',
                  '  People READY TO HIRE a lawyer. Fix ranking = get more clients.',
                  '  IMPRESSIONS = how often your site appeared in search (from GSC).',
                  '',
                  f'  {"KEYWORD":<42} {"IMPR/WK":>9}  {"YOUR RANK":<26}  PREV RANK',
                  f'  {sep("─", 88)}']
        for kw in COMMERCIAL_KWS:
            v  = tq.get(kw)
            pv = pq.get(kw)
            pos  = v['position'] if v else None
            ppos = pv['position'] if pv else None
            imp  = v['impressions'] if v else 0
            imp_str = f'{imp:,}/wk' if imp else '0/wk'
            rank_label = page_rank_label(pos)
            prev_label = page_rank_label(ppos) if ppos else 'Not found'
            lines.append(f'  {kw:<42} {imp_str:>8}  {rank_label:<26}  {prev_label}')
            if pos and ppos and (pos - ppos) > 5:
                alerts.append(f'🔴 RANKING DROP: "{kw}" dropped from pos {ppos:.0f} to {pos:.0f}')
        lines.append('')
        lines.append('  ✅ Ranking Page 1 for 3+ of these = more clients automatically.')

    # ── SECTION 6: INVISIBLE KEYWORD OPPORTUNITIES ───────────────────────────
    with get_session() as s:
        site = s.query(Site).filter_by(domain=site_domain).first()
        opps = []
        if site:
            opps = (s.query(KeywordOpportunity)
                    .filter_by(site_id=site.id, status='new')
                    .filter(KeywordOpportunity.intent.in_(['commercial', 'near-commercial']))
                    .order_by(KeywordOpportunity.discovered_at.desc())
                    .limit(10).all())

    if opps:
        lines += ['', '📡 NEWLY DISCOVERED KEYWORD OPPORTUNITIES', sep(),
                  '  Keywords clients search where you have ZERO visibility:', '']
        lines.append(f'  {"KEYWORD":<42} {"KD":>5}  {"INTENT":<16}  ACTION')
        lines.append(f'  {sep("─", 75)}')
        for opp in opps:
            kd_str = f'{opp.kd_score}/100' if opp.kd_score else 'n/a'
            action = 'Create page' if not opp.kd_score or opp.kd_score < 40 else 'Add to existing page'
            lines.append(f'  {opp.keyword:<42} {kd_str:>5}  {opp.intent:<16}  {action}')

    # ── SECTION 6b: GSC CONTENT GAPS ─────────────────────────────────────────
    try:
        from analysis.gsc_content_gap import detect_content_gaps
        cg_rows = detect_content_gaps(site_domain=site_domain, min_impressions=20, top_n=10)
        if cg_rows:
            lines += ['', '━' * 60,
                      '🔍 CONTENT GAPS — QUERIES WITH NO MATCHING PAGE',
                      '━' * 60, '',
                      '  Queries Google shows us for but no dedicated page exists yet.',
                      '  Creating pages for these could capture new organic traffic.',
                      '',
                      f'  {"QUERY":<42} {"IMPR":>6}  {"POS":>6}  {"CTR":>6}',
                      f'  {sep("─", 64)}']
            for g in cg_rows:
                lines.append(
                    f'  {g["query"][:42]:<42} {g["impressions"]:>6,}  '
                    f'{g["avg_position"]:>6.1f}  {g["ctr_pct"]:>5.1f}%'
                )
            lines += ['',
                      '  Action: create a focused blog post or service page for top gaps.']
            if cg_rows[0]['opportunity_score'] > 300:
                top_gap = cg_rows[0]
                alerts.append(
                    f'🟡 Content gap: "{top_gap["query"]}" gets {top_gap["impressions"]:,} '
                    f'impressions at pos {top_gap["avg_position"]:.0f} but no page covers it'
                )
    except Exception:
        pass

    # ── SECTION 7: COMPETITOR MOVES ──────────────────────────────────────────
    with get_session() as s:
        site = s.query(Site).filter_by(domain=site_domain).first()
        new_comp_pages = []
        changed_comp_pages = []
        if site:
            new_comp_pages = (s.query(CompetitorUrl)
                              .filter(CompetitorUrl.first_seen >= date.today())
                              .limit(10).all())
            # Content-changed issues logged this week
            changed_comp_pages = (s.query(AuditIssue)
                                  .filter_by(site_id=site.id, issue_type='competitor_content_changed',
                                             status='open')
                                  .filter(AuditIssue.detected_at >= datetime.combine(
                                      date.today() - timedelta(days=7), datetime.min.time()))
                                  .limit(10).all())

    if new_comp_pages or changed_comp_pages:
        lines += ['', '🕵️ COMPETITOR MOVES THIS WEEK', sep()]
        if new_comp_pages:
            alerts.append(f'⚠️ {len(new_comp_pages)} new competitor pages published — review and counter')
            for cp in new_comp_pages:
                lines.append(f'  🆕 {cp.url}')
                if cp.title:
                    lines.append(f'     Title: {cp.title}')
        if changed_comp_pages:
            lines.append(f'  📝 {len(changed_comp_pages)} competitor pages had content updates:')
            for issue in changed_comp_pages[:5]:
                lines.append(f'     {issue.description}')
                lines.append(f'     → {issue.remediation}')
    else:
        lines += ['', '🕵️ COMPETITOR MOVES: No new pages or content changes detected this week ✅']

    # ── SECTION 7b: BACKLINK TRENDS ──────────────────────────────────────────
    try:
        from analysis.backlink_trends import run_backlink_trends
        bl = run_backlink_trends(site_domain)
        if bl and bl.get('total_live', 0) > 0:
            net_arrow = ('↑' if bl['net_4w'] > 0 else ('↓' if bl['net_4w'] < 0 else '→'))
            lines += ['', '🔗 BACKLINKS THIS MONTH', sep(),
                      f'  Live backlinks:  {bl["total_live"]}',
                      f'  Gained (4 wks):  {bl["gained_4w"]}',
                      f'  Lost   (4 wks):  {bl["lost_4w"]}',
                      f'  Net change:      {net_arrow} {bl["net_4w"]}']
            if bl['lost_4w'] > bl['gained_4w']:
                alerts.append(f'🔴 Losing backlinks: -{bl["lost_4w"]} lost vs +{bl["gained_4w"]} gained (4 weeks)')
    except Exception:
        pass

    # ── SECTION 8: COMMUNITY OPPORTUNITIES ───────────────────────────────────
    with get_session() as s:
        site = s.query(Site).filter_by(domain=site_domain).first()
        answer_opps = []
        if site:
            answer_opps = (s.query(Mention)
                           .filter_by(site_id=site.id, has_question=True, is_answered=False)
                           .order_by(Mention.discovered_at.desc())
                           .limit(5).all())

    if answer_opps:
        lines += ['', '💬 COMMUNITY ANSWER OPPORTUNITIES', sep(),
                  '  NRIs asking legal questions online — answer to build authority:', '']
        for m in answer_opps:
            lines.append(f'  [{m.platform.upper()}] {m.title[:80]}')
            lines.append(f'    {m.source_url}')
    else:
        lines += ['', '💬 COMMUNITY: No new unanswered questions found this week']

    # ── SECTION 9: QUICK WINS ────────────────────────────────────────────────
    quick_wins = []
    if gsc_data:
        tp = gsc_data['this']['pages']
        for url, v in tp.items():
            if v['impressions'] < 100: continue
            actual_ctr = v['clicks'] / v['impressions'] if v['impressions'] else 0
            potential  = v['impressions'] * max(0, 0.03 - actual_ctr)
            slug = url.replace(f'https://{site_domain}', '') or '/'
            if potential > 10:
                quick_wins.append((slug, v['impressions'], actual_ctr*100, int(potential), v['position']))
        quick_wins.sort(key=lambda x: -x[3])

    # Near page-1 commercial keywords
    near_p1 = []
    if gsc_data:
        tq = gsc_data['this']['queries']
        near_p1 = [(kw, v) for kw, v in tq.items()
                   if 10 < v.get('position', 999) <= 20
                   and v.get('impressions', 0) > 30
                   and 'nri' in kw.lower()]
        near_p1.sort(key=lambda x: -x[1]['impressions'])

    lines += ['', '━' * 60,
              '⚡ THIS WEEK\'S QUICK WINS  (forward to Claude to execute)',
              '━' * 60, '']

    win_num = 1
    shown = set()
    for slug, imp, ctr, pot, pos in quick_wins[:5]:
        if win_num > 3: break
        if slug in shown: continue
        shown.add(slug)
        lines += [f'  {win_num}. CTR FIX: {slug}',
                  f'     Problem: {imp:,} people see this page but only {ctr:.2f}% click (losing ~{pot} clicks/week)',
                  f'     Fix: Rewrite title and meta description to be more compelling',
                  f'     Effort: 5 minutes', '']
        win_num += 1

    for kw, v in near_p1[:3]:
        if win_num > 5: break
        lines += [f'  {win_num}. RANKING PUSH: "{kw}"',
                  f'     Problem: Position {v["position"]:.1f} (page 2) — {v["impressions"]:,} searches/week',
                  f'     Fix: Add 3 internal links to relevant page using this as anchor text',
                  f'     Effort: 10 minutes', '']
        win_num += 1

    # ── SECTION 9b: AI VISIBILITY ────────────────────────────────────────────
    with get_session() as s:
        site = s.query(Site).filter_by(domain=site_domain).first()
        aeo_results = []
        bing_rows   = []
        if site:
            aeo_results = (s.query(AeoResult)
                           .filter_by(site_id=site.id)
                           .filter(AeoResult.date >= date.today() - timedelta(days=7))
                           .all())
            bing_all = (s.query(BingQuery)
                        .filter_by(site_id=site.id)
                        .filter(BingQuery.date >= date.today() - timedelta(days=7))
                        .all())
            bing_rows = sorted(bing_all, key=lambda r: r.clicks, reverse=True)[:5]

    if aeo_results:
        aio_cited = sum(1 for r in aeo_results if r.is_cited)
        bing_cited = sum(1 for r in aeo_results if r.is_cited and 'bing' in r.engine)
        google_cited = sum(1 for r in aeo_results if r.is_cited and 'google' in r.engine)
        lines += ['', '🤖 AI SEARCH VISIBILITY THIS WEEK', sep(),
                  f'  Cited in {aio_cited}/{len(aeo_results)} AI engine checks',
                  f'  Google AI Overviews: cited in {google_cited}',
                  f'  Bing Copilot:        cited in {bing_cited}',
                  '',
                  '  Manual checks needed: ChatGPT, Gemini, Perplexity',
                  '  → Use Dashboard → AI Visibility → Manual Log tab']
        if aio_cited == 0:
            alerts.append('🟡 Not cited in any AI search checks this week — add schema markup + llms.txt')

    if bing_rows:
        b_total_clicks = sum(r.clicks for r in bing_all)
        b_total_imps   = sum(r.impressions for r in bing_all)
        lines += ['', '🔷 BING SEARCH PERFORMANCE', sep(),
                  f'  Bing clicks (week):       {b_total_clicks:,}',
                  f'  Bing impressions (week):  {b_total_imps:,}',
                  '',
                  f'  {"QUERY":<42} {"CLICKS":>7}  {"IMPS":>9}  {"RANK":>6}']
        for r in bing_rows[:5]:
            lines.append(f'  {r.query:<42} {r.clicks:>7,}  {r.impressions:>9,}  {r.avg_position or "-":>6}')

    # ── SECTION 9c: TECHNICAL AUDIT SUMMARY ──────────────────────────────────
    with get_session() as s:
        site = s.query(Site).filter_by(domain=site_domain).first()
        if site:
            crawl_pages = s.query(SiteCrawlPage).filter_by(site_id=site.id).all()
            ps_rows     = s.query(PageSpeed).filter_by(site_id=site.id, strategy='mobile',
                                                        date=date.today()).all()
            sov_row     = (s.query(VisibilityScore)
                           .filter_by(site_id=site.id, domain=site_domain)
                           .order_by(VisibilityScore.date.desc()).first())
            new_alerts  = (s.query(Alert)
                           .filter_by(site_id=site.id, is_read=False,
                                      severity='critical').count())
        else:
            crawl_pages = ps_rows = []
            sov_row = None
            new_alerts = 0

    if crawl_pages:
        from collections import Counter
        all_issues = [i for p in crawl_pages for i in (p.issues or [])]
        issue_counts = Counter(all_issues)
        critical_pages = sum(1 for p in crawl_pages for i in (p.issues or [])
                             if i in ('missing_title', 'missing_h1', 'thin_content',
                                       'noindex_page', 'broken_internal_links'))
        lines += ['', '🔍 TECHNICAL SITE AUDIT', sep(),
                  f'  Pages crawled:    {len(crawl_pages)}',
                  f'  Critical issues:  {critical_pages} pages',
                  f'  Top issues:']
        for issue_type, count in sorted(issue_counts.items(), key=lambda x: -x[1])[:5]:
            lines.append(f'    • {issue_type.replace("_", " ").title()}: {count} pages')

    if ps_rows:
        avg_score = int(sum(r.performance or 0 for r in ps_rows) / len(ps_rows))
        poor = sum(1 for r in ps_rows if (r.performance or 0) < 50)
        lines += ['', '⚡ CORE WEB VITALS (MOBILE)', sep(),
                  f'  Avg performance score: {avg_score}/100',
                  f'  Pages with poor score (<50): {poor}']
        if poor:
            alerts.append(f'🟡 {poor} pages have poor mobile performance (<50) — fix before Google penalises')

    if sov_row:
        lines += ['', '📊 SHARE OF VOICE', sep(),
                  f'  Our search visibility: {sov_row.score:.2f}%',
                  f'  Est. monthly traffic:  ~{sov_row.traffic_est:,} visits']

    if new_alerts:
        alerts.append(f'🔴 {new_alerts} unread CRITICAL alerts in dashboard — action required')

    # ── SECTION 9c.5: CORE WEB VITALS / PAGESPEED ────────────────────────────
    with get_session() as s:
        site = s.query(Site).filter_by(domain=site_domain).first()
        cwv_rows = []
        if site:
            # Most recent date available for each page_url, strategy=mobile
            from sqlalchemy import func as _func
            latest_dates = (s.query(PageSpeed.page_url,
                                    _func.max(PageSpeed.date).label('max_date'))
                            .filter_by(site_id=site.id, strategy='mobile')
                            .group_by(PageSpeed.page_url)
                            .all())
            if latest_dates:
                # Fetch one row per page_url at its latest date
                for page_url, max_date in latest_dates:
                    row = (s.query(PageSpeed)
                           .filter_by(site_id=site.id, strategy='mobile',
                                      page_url=page_url, date=max_date)
                           .first())
                    if row:
                        cwv_rows.append(row)

    if cwv_rows:
        cwv_date = max(r.date for r in cwv_rows)
        scores   = [r.performance or 0 for r in cwv_rows]
        avg_score = int(sum(scores) / len(scores))
        pages_poor    = sum(1 for s_ in scores if s_ < 50)
        pages_lcp_bad = sum(1 for r in cwv_rows if r.lcp and r.lcp > 4.0)
        pages_cls_bad = sum(1 for r in cwv_rows if r.cls and r.cls > 0.1)

        def _score_icon(sc):
            if sc >= 90: return '✅'
            if sc >= 50: return '🟡'
            return '🔴'

        lines += ['', f'⚡ CORE WEB VITALS (MOBILE)  — {cwv_date}', sep(),
                  f'  {"PAGE":<42} {"SCORE":>5}  {"LCP":>6}  {"CLS":>7}  FLAGS']
        lines.append(f'  {sep("─", 68)}')
        for r in sorted(cwv_rows, key=lambda x: -(x.performance or 0)):
            slug  = r.page_url.replace(f'https://{site_domain}', '') or r.page_url
            slug  = slug[:42]
            sc    = r.performance or 0
            icon  = _score_icon(sc)
            lcp_s = f'{r.lcp:.1f}s' if r.lcp else '—'
            cls_s = f'{r.cls:.3f}' if r.cls is not None else '—'
            flags = []
            if r.lcp and r.lcp > 4.0:      flags.append('⚠️ LCP')
            if r.cls is not None and r.cls > 0.1: flags.append('⚠️ CLS')
            flag_str = '  '.join(flags)
            lines.append(f'  {slug:<42} {icon}{sc:>3}  {lcp_s:>6}  {cls_s:>7}  {flag_str}')
        lines += ['',
                  f'  Avg mobile score: {avg_score}/100',
                  f'  Pages scoring < 50: {pages_poor}   '
                  f'Pages with LCP > 4s: {pages_lcp_bad}   '
                  f'Pages with CLS > 0.1: {pages_cls_bad}']

        if avg_score < 70:
            alerts.append(f'🔴 Avg mobile PageSpeed score {avg_score}/100 — below 70, Google may demote mobile rankings')
        if pages_poor:
            alerts.append(f'🔴 {pages_poor} page(s) score < 50 on mobile — critical performance issue')
        # Homepage LCP alert
        home_row = next((r for r in cwv_rows
                         if r.page_url.rstrip('/').endswith(site_domain)
                         or r.page_url in (f'https://{site_domain}/', f'https://{site_domain}')),
                        None)
        if home_row and home_row.lcp and home_row.lcp > 4.0:
            alerts.append(f'🟡 Homepage LCP {home_row.lcp:.1f}s > 4s — Google threshold for "needs improvement"')
    else:
        lines += ['', '⚡ CORE WEB VITALS (MOBILE)', sep(),
                  '  No data yet.',
                  '  Run: python run.py pagespeed   (takes ~3 min)']

    # ── SECTION 9c.7: DOMAIN AUTHORITY ───────────────────────────────────────
    try:
        from analysis.domain_authority import check_domain_authority
        da = check_domain_authority(site_domain)
        source_note = ('add OPEN_PAGE_RANK_KEY to .env for real scores'
                       if da['data_source'] == 'backlink_proxy'
                       else 'openpagerank.com')
        lines += ['', '🏛️ DOMAIN AUTHORITY COMPARISON', sep(),
                  f'  {"DOMAIN":<38} {"AUTHORITY":>9}  ']
        lines.append(f'  {sep("─", 52)}')
        for item in da['all']:
            marker = '  ← OURS' if item['is_ours'] else ''
            stronger = '  (stronger ↑)' if not item['is_ours'] and item['pagerank'] > da['our_pagerank'] else ''
            lines.append(f'  {item["domain"]:<38} {item["pagerank"]:>9.1f}{marker}{stronger}')
        lines += [f'  Source: {da["data_source"]} ({source_note})',
                  f'  {da["insight"]}']
    except Exception as _da_err:
        lines += ['', '🏛️ DOMAIN AUTHORITY: unavailable — ' + str(_da_err)[:80]]

    # ── SECTION 9d: E-E-A-T AUDIT ────────────────────────────────────────────
    with get_session() as s:
        site = s.query(Site).filter_by(domain=site_domain).first()
        eeat_issues = []
        if site:
            eeat_issues = (s.query(AuditIssue)
                           .filter(AuditIssue.site_id == site.id,
                                   AuditIssue.issue_type.like('eeat_%'),
                                   AuditIssue.status == 'open')
                           .order_by(AuditIssue.detected_at.desc())
                           .all())

    if eeat_issues:
        from analysis.eeat_audit import SERVICE_PAGES
        # Compute per-page scores from issue deductions
        _DEDUCT = {'critical': 25, 'warning': 15, 'info': 5}
        page_deductions: dict[str, int] = {}
        for issue in eeat_issues:
            page_deductions[issue.page_url] = (
                page_deductions.get(issue.page_url, 0) + _DEDUCT.get(issue.severity, 5)
            )
        page_scores = {url: max(0, 100 - d) for url, d in page_deductions.items()}
        avg_eeat = int(sum(page_scores.values()) / len(page_scores)) if page_scores else 0
        critical_count = sum(1 for i in eeat_issues if i.severity == 'critical')
        # Count distinct issue types to surface top problems
        from collections import Counter
        type_counts = Counter(i.issue_type for i in eeat_issues)
        lines += ['', '🏅 E-E-A-T AUTHORITY AUDIT  (YMYL Trust Signals)', sep(),
                  f'  Avg E-E-A-T score:    {avg_eeat}/100',
                  f'  Pages audited:        {len(page_scores)}',
                  f'  Critical issues:      {critical_count}',
                  f'  Top issues:']
        for issue_type, count in type_counts.most_common(4):
            label = issue_type.replace('eeat_', '').replace('_', ' ').title()
            lines.append(f'    • {label}: {count} pages')
        if avg_eeat < 60:
            alerts.append(f'🔴 E-E-A-T avg score {avg_eeat}/100 — Google YMYL penalty risk for legal site')
        elif avg_eeat < 80:
            alerts.append(f'🟡 E-E-A-T avg score {avg_eeat}/100 — fix critical issues to improve trust signals')
        # Worst 3 pages
        worst = sorted(page_scores.items(), key=lambda x: x[1])[:3]
        if worst:
            lines.append(f'  Worst pages:')
            for page_url, score in worst:
                path = page_url.replace(f'https://{site_domain}', '') or '/'
                lines.append(f'    {score}/100  {path}')
    else:
        lines += ['', '🏅 E-E-A-T AUDIT: No data — run `python analysis/eeat_audit.py` to populate']

    # ── SECTION 10: ALERTS ───────────────────────────────────────────────────
    lines += ['━' * 60, '🚨 URGENT ALERTS', '━' * 60]
    if alerts:
        for a in alerts:
            lines.append(f'  {a}')
    else:
        lines.append('  ✅ No urgent issues this week')

    lines += ['━' * 60,
              f'  Generated: {now.strftime("%Y-%m-%d %H:%M UTC")}',
              f'  Site: {site_domain}',
              '━' * 60]

    report_text = '\n'.join(lines)

    # ── AI EXECUTIVE SUMMARY (prepended) ─────────────────────────────────────
    ai_summary = _generate_ai_summary(site_domain, gsc_data, alerts)
    if ai_summary:
        report_text = ai_summary + '\n\n' + report_text

    return report_text


def _generate_ai_summary(site_domain: str, gsc_data: dict, alerts: list) -> str:
    """Generate a 3-paragraph AI executive summary using DeepSeek."""
    try:
        from utils.deepseek import chat, is_available
        if not is_available():
            return ''

        clicks     = gsc_data['this']['queries'] if gsc_data else {}
        total_c    = sum(v.get('clicks', 0) for v in clicks.values()) if clicks else 0
        total_i    = sum(v.get('impressions', 0) for v in clicks.values()) if clicks else 0
        avg_pos    = (sum(v.get('position', 0) for v in clicks.values()) /
                      max(len(clicks), 1)) if clicks else 0
        prev_c     = sum(v.get('clicks', 0) for v in gsc_data['prev']['queries'].values()
                         ) if gsc_data and gsc_data.get('prev') else 0

        ctr_c = f'{total_c / total_i * 100:.2f}%' if total_i else 'n/a'
        wow   = f'+{total_c - prev_c}' if total_c >= prev_c else str(total_c - prev_c)
        prompt = (
            f'You are an SEO analyst writing a weekly executive summary for an NRI legal consultancy.\n\n'
            f'EXACT DATA THIS WEEK (use these numbers verbatim — do not invent or round differently):\n'
            f'- Organic clicks this week: EXACTLY {total_c:,}\n'
            f'- Organic clicks last week: EXACTLY {prev_c:,}\n'
            f'- Week-over-week change: EXACTLY {wow} clicks\n'
            f'- Impressions: EXACTLY {total_i:,}\n'
            f'- CTR: EXACTLY {ctr_c}\n'
            f'- Average position: EXACTLY {avg_pos:.1f}\n'
            f'- Active alerts: {", ".join(alerts[:3]) if alerts else "None"}\n\n'
            f'Write a 3-paragraph executive summary. Use the EXACT numbers above.\n'
            f'1. Performance vs last week — state exact click numbers and what the change means\n'
            f'2. The single most important action this week and the specific reason\n'
            f'3. What to expect next week if no action is taken\n\n'
            f'Be direct and specific. Use plain language. No vague phrases like "consider" or "may want to".\n'
            f'Do not include any service promotion, "call us", pricing, or client solicitation.'
        )
        summary = chat(prompt, max_tokens=400, temperature=0.4)
        # Validate: if DeepSeek hallucinated wrong numbers, replace with template
        if summary and str(total_c) not in summary:
            wow_str = f'+{total_c - prev_c}' if total_c >= prev_c else str(total_c - prev_c)
            ctr_val = f'{total_c / total_i * 100:.2f}%' if total_i else 'n/a'
            summary = (
                f'This week example-legal.in received {total_c:,} organic clicks '
                f'({wow_str} vs last week\'s {prev_c:,}). Impressions: {total_i:,}. '
                f'CTR: {ctr_val} (target: 3%). Average position: {avg_pos:.1f}.\n\n'
                + (summary if summary else '')
            )
        if summary:
            return (
                '━' * 60 + '\n'
                '🤖 AI EXECUTIVE SUMMARY  (DeepSeek)\n'
                + '━' * 60 + '\n'
                + summary + '\n'
                + '━' * 60
            )
    except Exception:
        pass
    return ''

def build_and_send(site_domain: str = TARGET_DOMAIN,
                   gsc_data: dict = None, ga4_data: dict = None) -> str:
    """Build report, build PDF, send HTML email with PDF attached."""
    report = build_report(site_domain, gsc_data, ga4_data)
    reports_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'reports')
    os.makedirs(reports_dir, exist_ok=True)

    # Build PDF
    from report.pdf_builder import build_pdf_report
    pdf_path = build_pdf_report(site_domain, gsc_live=gsc_data)

    # Extract metrics for email
    from core.db import get_session, Site, GscPage, Ga4Session
    from datetime import timedelta
    from collections import defaultdict
    try:
        with get_session() as s:
            site = s.query(Site).filter_by(domain=site_domain).first()
            if site:
                cutoff = __import__('datetime').date.today() - timedelta(days=7)
                pages  = s.query(GscPage).filter(GscPage.site_id==site.id,
                                                  GscPage.date>=cutoff).all()
                ga4    = s.query(Ga4Session).filter(Ga4Session.site_id==site.id,
                                                    Ga4Session.date>=cutoff).all()
                total_clicks = sum(p.clicks or 0 for p in pages)
                total_leads  = sum(r.conversions or 0 for r in ga4)
                prev_clicks  = 0
                if gsc_data and gsc_data.get('prev'):
                    prev_clicks = sum(v.get('clicks', 0)
                                      for v in gsc_data['prev'].get('pages', {}).values())
    except Exception:
        total_clicks = prev_clicks = total_leads = 0

    # Extract AI summary and health score from report text
    ai_summary = ''
    if 'AI EXECUTIVE SUMMARY' in report:
        s_idx = report.find('AI EXECUTIVE SUMMARY') + 22
        e_idx = report.find('\n\n\n', s_idx)
        ai_summary = report[s_idx:e_idx if e_idx > 0 else s_idx + 1500].strip()

    from report.email import send_report
    send_report(
        report_text=report,
        site_domain=site_domain,
        pdf_path=pdf_path,
        total_clicks=total_clicks,
        prev_clicks=prev_clicks,
        total_leads=total_leads,
        health_score=50,  # rough default; PDF calculates exact
        ai_summary=ai_summary,
    )
    return report

if __name__ == '__main__':
    # Test with dummy data (no API keys needed)
    print(build_report(TARGET_DOMAIN))
