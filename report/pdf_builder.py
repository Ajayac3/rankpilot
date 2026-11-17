"""
RankPilot — PDF Report Generator (Silicon Valley Quality Edition)
Uses matplotlib for charts + fpdf2 for layout.
Output: rankpilot/data/reports/YYYY-MM-DD.pdf
"""
import os, sys, io
from datetime import date, datetime, timedelta
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import TARGET_DOMAIN, FIRM_NAME

REPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           'data', 'reports')
BRAND_BLUE   = (0, 82, 165)
BRAND_ORANGE = (255, 140, 0)
GREEN        = (39, 174, 96)
RED          = (231, 76, 60)
YELLOW       = (243, 156, 18)
LIGHT_BLUE   = (235, 242, 255)
LIGHT_GREEN  = (235, 255, 240)
LIGHT_RED    = (255, 235, 235)
LIGHT_YELLOW = (255, 249, 219)
TEXT_DARK    = (30, 30, 30)
TEXT_GRAY    = (100, 100, 100)


# ── ASCII sanitizer ───────────────────────────────────────────────────────────
def _s(text) -> str:
    return str(text).encode('ascii', errors='ignore').decode('ascii')


# ── Matplotlib chart helpers ──────────────────────────────────────────────────
def _chart_bytes(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    import matplotlib.pyplot as plt
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def _traffic_trend_chart(period_clicks: list[tuple]) -> bytes:
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    dates  = [d for d, _ in period_clicks]
    clicks = [c for _, c in period_clicks]
    fig, ax = plt.subplots(figsize=(8, 2.8))
    ax.plot(dates, clicks, color='#0052A5', linewidth=2.5, marker='o',
            markersize=5, zorder=3)
    ax.fill_between(dates, clicks, alpha=0.12, color='#0052A5')
    ax.set_title('Organic Traffic Trend (6 months)', fontsize=10, fontweight='bold', pad=8)
    ax.set_ylabel('Clicks', fontsize=8)
    ax.tick_params(axis='both', labelsize=7)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %y'))
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.grid(axis='y', alpha=0.3, linestyle='--')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    fig.tight_layout()
    return _chart_bytes(fig)


def _rankings_distribution_chart(buckets: dict) -> bytes:
    import matplotlib.pyplot as plt
    labels = list(buckets.keys())
    values = list(buckets.values())
    colors = ['#27ae60', '#2ecc71', '#f39c12', '#e67e22', '#e74c3c'][:len(labels)]
    fig, ax = plt.subplots(figsize=(5, 2.2))
    bars = ax.barh(labels, values, color=colors, height=0.6)
    for bar, val in zip(bars, values):
        if val > 0:
            ax.text(bar.get_width() + 0.1, bar.get_y() + bar.get_height()/2,
                    str(val), va='center', fontsize=9, fontweight='bold')
    ax.set_title('Keyword Rankings Distribution', fontsize=10, fontweight='bold', pad=6)
    ax.set_xlabel('Keywords', fontsize=8)
    ax.tick_params(labelsize=8)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.grid(axis='x', alpha=0.3, linestyle='--')
    fig.tight_layout()
    return _chart_bytes(fig)


def _country_chart(country_data: list[tuple]) -> bytes:
    import matplotlib.pyplot as plt
    HIGH_VALUE = {'USA', 'CAN', 'GBR', 'ARE', 'AUS', 'SGP'}
    NAMES = {'IND': 'India', 'USA': 'USA', 'CAN': 'Canada', 'GBR': 'UK',
             'ARE': 'UAE', 'AUS': 'Australia', 'SGP': 'Singapore',
             'SAU': 'Saudi Arabia', 'NZL': 'NZ', 'DEU': 'Germany'}
    labels = [NAMES.get(c, c) for c, _ in country_data[:8]]
    values = [v for _, v in country_data[:8]]
    codes  = [c for c, _ in country_data[:8]]
    colors = ['#f39c12' if c in HIGH_VALUE else '#0052A5' for c in codes]
    fig, ax = plt.subplots(figsize=(5, 2.8))
    bars = ax.barh(labels[::-1], values[::-1], color=colors[::-1], height=0.6)
    for bar, val in zip(bars, values[::-1]):
        ax.text(bar.get_width() + 0.3, bar.get_y() + bar.get_height()/2,
                str(val), va='center', fontsize=8)
    ax.set_title('Clicks by Country (gold = high-value NRI market)', fontsize=9,
                 fontweight='bold', pad=6)
    ax.tick_params(labelsize=8)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.grid(axis='x', alpha=0.3, linestyle='--')
    fig.tight_layout()
    return _chart_bytes(fig)


def _competitor_chart(vis_scores: list) -> bytes:
    import matplotlib.pyplot as plt
    domains  = [_s(v.domain).replace('example-legal.in', 'US') for v in vis_scores[:7]]
    traffic  = [v.traffic_est or 0 for v in vis_scores[:7]]
    colors   = ['#27ae60' if 'nrilegal' in v.domain else '#0052A5' for v in vis_scores[:7]]
    if not any(traffic):
        return b''
    fig, ax = plt.subplots(figsize=(6, 2.5))
    bars = ax.barh(domains[::-1], traffic[::-1], color=colors[::-1], height=0.6)
    for bar, val in zip(bars, traffic[::-1]):
        if val > 0:
            ax.text(bar.get_width() + 5, bar.get_y() + bar.get_height()/2,
                    f'{val:,}', va='center', fontsize=8)
    ax.set_title('Est. Monthly Traffic vs Competitors', fontsize=10,
                 fontweight='bold', pad=6)
    ax.set_xlabel('Est. visits/month', fontsize=8)
    ax.tick_params(labelsize=7)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.grid(axis='x', alpha=0.3, linestyle='--')
    fig.tight_layout()
    return _chart_bytes(fig)


def _opportunity_scatter(opps: list) -> bytes:
    import matplotlib.pyplot as plt
    commercial   = [o for o in opps if o.intent == 'commercial' and o.est_volume]
    near_comm    = [o for o in opps if o.intent == 'near-commercial' and o.est_volume]
    info         = [o for o in opps if o.intent == 'informational' and o.est_volume]
    if not (commercial or near_comm or info):
        return b''
    fig, ax = plt.subplots(figsize=(6, 3))
    for group, color, label in [
        (commercial, '#27ae60', 'Commercial'),
        (near_comm,  '#f39c12', 'Near-Commercial'),
        (info,       '#3498db', 'Informational'),
    ]:
        if group:
            xs = [min(o.kd_score or 30, 100) for o in group[:50]]
            ys = [min(o.est_volume or 10, 2000) for o in group[:50]]
            ax.scatter(xs, ys, c=color, alpha=0.6, s=40, label=label, zorder=3)
    ax.set_xlabel('Keyword Difficulty (0=easy, 100=hard)', fontsize=8)
    ax.set_ylabel('Est. Monthly Volume', fontsize=8)
    ax.set_title('Keyword Opportunity Matrix', fontsize=10, fontweight='bold', pad=6)
    ax.legend(fontsize=7)
    ax.tick_params(labelsize=7)
    ax.grid(alpha=0.3, linestyle='--')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.axvline(40, color='gray', linestyle='--', alpha=0.4, linewidth=0.8)
    ax.text(41, ax.get_ylim()[1] * 0.95, 'Quick wins →', fontsize=7, color='gray')
    fig.tight_layout()
    return _chart_bytes(fig)


# ── PDF wrapper ───────────────────────────────────────────────────────────────
def _try_fpdf():
    try:
        from fpdf import FPDF
        return FPDF
    except ImportError:
        return None


class PDF:
    def __init__(self, site_domain: str):
        FPDF = _try_fpdf()
        if not FPDF:
            raise ImportError('pip install fpdf2')
        self.p = FPDF()
        self.p.set_auto_page_break(auto=True, margin=18)
        self.p.add_page()
        self.p.set_margins(10, 10, 10)
        self._cover(site_domain)

    def _cover(self, domain: str):
        p = self.p
        p.set_fill_color(*BRAND_BLUE)
        p.rect(0, 0, 210, 42, 'F')
        p.set_text_color(255, 255, 255)
        p.set_font('Helvetica', 'B', 18)
        p.set_xy(10, 8)
        p.cell(0, 10, 'RankPilot - Weekly SEO Intelligence Report', ln=True)
        p.set_font('Helvetica', '', 10)
        p.set_xy(10, 22)
        p.cell(0, 8, f'{_s(domain)}  |  {date.today().strftime("%d %B %Y")}', ln=True)
        p.set_text_color(*TEXT_DARK)
        # Move cursor below the blue bar
        p.set_xy(10, 48)

    def section(self, title: str):
        p = self.p
        p.ln(3)
        p.set_x(10)
        p.set_fill_color(*BRAND_BLUE)
        p.set_text_color(255, 255, 255)
        p.set_font('Helvetica', 'B', 11)
        p.cell(0, 8, f'  {_s(title)}', ln=True, fill=True)
        p.set_text_color(*TEXT_DARK)
        p.set_font('Helvetica', '', 9)
        p.ln(2)

    def kpi_cards(self, cards: list[tuple]):
        """Draw a row of KPI cards. cards = [(label, value, change, good), ...]"""
        p = self.p
        n = len(cards)
        w = int(185 / n)
        y = p.get_y()
        for i, (label, value, change, is_good) in enumerate(cards):
            x = 10 + i * w
            bg = LIGHT_GREEN if is_good else LIGHT_RED if is_good is False else LIGHT_BLUE
            p.set_fill_color(*bg)
            p.set_draw_color(*BRAND_BLUE)
            p.rect(x, y, w - 2, 22, 'FD')
            p.set_font('Helvetica', 'B', 8)
            p.set_text_color(*TEXT_GRAY)
            p.set_xy(x + 2, y + 2)
            p.cell(w - 4, 4, _s(label)[:18], ln=True)
            p.set_font('Helvetica', 'B', 14)
            p.set_text_color(*BRAND_BLUE)
            p.set_xy(x + 2, y + 7)
            p.cell(w - 4, 7, _s(str(value)), ln=True)
            p.set_font('Helvetica', '', 7)
            chg_color = GREEN if (change or '').startswith('+') or 'up' in str(change).lower() \
                        else RED if (change or '').startswith('-') or 'down' in str(change).lower() \
                        else TEXT_GRAY
            p.set_text_color(*chg_color)
            p.set_xy(x + 2, y + 15)
            p.cell(w - 4, 4, _s(str(change or '')))
        p.set_text_color(*TEXT_DARK)
        p.set_draw_color(0, 0, 0)
        p.ln(26)

    def health_score(self, score: int):
        """Draw health score as a two-cell row (no absolute positioning)."""
        p = self.p
        if score >= 70:
            color, label = GREEN, 'HEALTHY'
        elif score >= 50:
            color, label = YELLOW, 'NEEDS WORK'
        else:
            color, label = RED, 'CRITICAL'
        p.set_x(10)
        # Score box
        p.set_fill_color(*color)
        p.set_draw_color(*color)
        p.set_text_color(255, 255, 255)
        p.set_font('Helvetica', 'B', 22)
        p.cell(38, 14, str(score), fill=True, align='C')
        # Label next to it
        p.set_text_color(*TEXT_DARK)
        p.set_font('Helvetica', 'B', 12)
        p.cell(0, 14, f'  / 100  -  SEO Health: {label}', ln=True)
        # Sub-line
        p.set_x(10)
        p.set_font('Helvetica', '', 8)
        p.set_text_color(*TEXT_GRAY)
        p.cell(0, 5, 'Score: rankings 40% + CTR 20% + audit 20% + PageSpeed 20%', ln=True)
        p.set_text_color(*TEXT_DARK)
        p.set_draw_color(0, 0, 0)
        p.ln(4)

    def chart(self, png_bytes: bytes, w: int = 185):
        if not png_bytes:
            return
        p = self.p
        try:
            p.image(io.BytesIO(png_bytes), x=10, w=w)
            p.ln(3)
        except Exception:
            pass

    def two_charts(self, left_bytes: bytes, right_bytes: bytes):
        if not left_bytes and not right_bytes:
            return
        p = self.p
        y = p.get_y()
        if left_bytes:
            try:
                p.image(io.BytesIO(left_bytes), x=10, y=y, w=90)
            except Exception:
                pass
        if right_bytes:
            try:
                p.image(io.BytesIO(right_bytes), x=105, y=y, w=90)
            except Exception:
                pass
        p.set_y(y + 45)
        p.ln(3)

    def table(self, headers: list, rows: list, col_widths: list = None,
              row_colors: list = None):
        p = self.p
        p.set_x(10)
        n   = len(headers)
        cws = col_widths or [int(185 / n)] * n
        # Header
        p.set_fill_color(*BRAND_BLUE)
        p.set_text_color(255, 255, 255)
        p.set_font('Helvetica', 'B', 8)
        for h, w in zip(headers, cws):
            p.cell(w, 6, _s(h)[:22], border=1, fill=True)
        p.ln()
        p.set_font('Helvetica', '', 8)
        for i, row in enumerate(rows[:40]):
            bg = row_colors[i] if row_colors and i < len(row_colors) else \
                 (LIGHT_BLUE if i % 2 == 0 else (255, 255, 255))
            p.set_fill_color(*bg)
            p.set_text_color(*TEXT_DARK)
            max_h = 5
            for cell, w in zip(row, cws):
                p.cell(w, max_h, _s(cell)[:30], border=1, fill=True)
            p.ln()
        p.set_text_color(*TEXT_DARK)
        p.ln(2)

    def text_block(self, content: str, max_chars: int = 2000):
        p = self.p
        p.set_x(10)
        p.set_font('Helvetica', '', 9)
        p.set_text_color(*TEXT_DARK)
        lines = _s(content[:max_chars]).split('\n')
        for line in lines:
            if line.strip():
                p.set_x(10)
                p.multi_cell(185, 5, line.strip())
        p.ln(2)

    def metric_row(self, label: str, value: str, change: str = '', good: bool = None):
        p = self.p
        p.set_font('Helvetica', 'B', 9)
        p.cell(80, 6, _s(label))
        p.set_font('Helvetica', '', 9)
        p.cell(45, 6, _s(str(value)))
        if change:
            c = GREEN if good is True else RED if good is False else TEXT_GRAY
            p.set_text_color(*c)
            p.cell(60, 6, _s(str(change)))
            p.set_text_color(*TEXT_DARK)
        p.ln()

    def save(self) -> str:
        os.makedirs(REPORTS_DIR, exist_ok=True)
        path = os.path.join(REPORTS_DIR, f'{date.today().isoformat()}.pdf')
        self.p.output(path)
        return path


# ── Health score calculator ───────────────────────────────────────────────────
def _health_score(rankings, ctr, open_critical, avg_speed) -> int:
    score = 30
    top10 = sum(1 for r, _ in rankings if r.position and r.position <= 10)
    score += min(30, top10 * 3)
    score += min(15, int(ctr / 3.0 * 15))
    score -= min(15, open_critical)
    if avg_speed >= 90: score += 15
    elif avg_speed >= 70: score += 10
    elif avg_speed >= 50: score += 5
    return max(0, min(100, score))


# ── Main builder ──────────────────────────────────────────────────────────────
def build_pdf_report(site_domain: str = TARGET_DOMAIN,
                     gsc_live: dict = None) -> str | None:
    if not _try_fpdf():
        print('  info: pip install fpdf2')
        return None

    from sqlalchemy import func
    from core.db import (get_session, Site, GscPage, GscQuery, Ranking, Keyword,
                         KeywordOpportunity, Backlink, AuditIssue, Alert,
                         PageSpeed, Ga4Session, Mention, CompetitorUrl,
                         Competitor, ContentBrief, SerpVolatility, VisibilityScore,
                         BingQuery)

    with get_session() as s:
        site = s.query(Site).filter_by(domain=site_domain).first()
        if not site:
            return None
        sid    = site.id
        cutoff = date.today() - timedelta(days=7)

        # Rankings — latest date
        latest_rank_date = (s.query(func.max(Ranking.date))
                            .join(Keyword).filter(Keyword.site_id == sid).scalar())
        prev_rank_date   = latest_rank_date - timedelta(days=1) if latest_rank_date else None
        rankings = []
        prev_rankings = {}
        if latest_rank_date:
            rankings = (s.query(Ranking, Keyword).join(Keyword)
                        .filter(Keyword.site_id == sid,
                                Ranking.date == latest_rank_date,
                                Ranking.position != None)
                        .order_by(Ranking.position).all())
        if prev_rank_date:
            prev_rankings = {r.keyword_id: r.position for r in
                             s.query(Ranking).join(Keyword)
                             .filter(Keyword.site_id == sid,
                                     Ranking.date == prev_rank_date).all()
                             if r.position}

        # GSC data — all periods for trend
        all_gsc_pages = s.query(GscPage).filter_by(site_id=sid).all()
        recent_gsc    = s.query(GscPage).filter(
            GscPage.site_id == sid, GscPage.date >= cutoff).all()

        # Country breakdown from GSC queries
        country_rows = (s.query(GscQuery.country,
                                func.sum(GscQuery.clicks).label('clicks'))
                        .filter(GscQuery.site_id == sid, GscQuery.date >= cutoff)
                        .group_by(GscQuery.country)
                        .order_by(func.sum(GscQuery.clicks).desc())
                        .limit(8).all())

        # Other tables
        opps         = (s.query(KeywordOpportunity).filter_by(site_id=sid, status='new')
                        .order_by(KeywordOpportunity.est_volume.desc().nullslast())
                        .limit(200).all())
        live_bl      = s.query(Backlink).filter_by(site_id=sid, status='live').count()
        top_bl       = (s.query(Backlink).filter_by(site_id=sid, status='live')
                        .limit(8).all())
        open_issues  = (s.query(AuditIssue).filter_by(site_id=sid, status='open')
                        .order_by(AuditIssue.severity).all())
        critical_cnt = sum(1 for i in open_issues if i.severity == 'critical')
        ps_rows      = (s.query(PageSpeed).filter(
            PageSpeed.site_id == sid, PageSpeed.strategy == 'mobile',
            PageSpeed.date >= cutoff).order_by(PageSpeed.performance).limit(8).all())
        avg_speed    = int(sum(r.performance for r in ps_rows if r.performance) /
                          max(len(ps_rows), 1)) if ps_rows else 0
        ga4_rows     = s.query(Ga4Session).filter(
            Ga4Session.site_id == sid, Ga4Session.date >= cutoff).all()
        mentions     = (s.query(Mention).filter(
            Mention.site_id == sid, Mention.has_question == True)
                        .order_by(Mention.discovered_at.desc()).limit(8).all())
        new_comp     = (s.query(CompetitorUrl, Competitor).join(Competitor)
                        .filter(Competitor.site_id == sid,
                                CompetitorUrl.is_new == True,
                                CompetitorUrl.first_seen >= date.today() - timedelta(days=7))
                        .order_by(CompetitorUrl.first_seen.desc()).limit(8).all())
        briefs       = (s.query(ContentBrief).filter_by(site_id=sid)
                        .order_by(ContentBrief.created_at.desc()).limit(5).all())
        vis_scores   = (s.query(VisibilityScore).filter_by(site_id=sid)
                        .order_by(VisibilityScore.traffic_est.desc()).limit(8).all())
        alert_rows   = (s.query(Alert).filter_by(site_id=sid)
                        .order_by(Alert.created_at.desc()).limit(8).all())
        # Bing Webmaster Tools — most recent period
        bing_date = s.query(func.max(BingQuery.date)).filter_by(site_id=sid).scalar()
        bing_rows = s.query(BingQuery).filter(
            BingQuery.site_id == sid, BingQuery.date == bing_date
        ).order_by(BingQuery.clicks.desc()).limit(10).all() if bing_date else []
        bing_totals = (
            sum(r.clicks or 0 for r in s.query(BingQuery).filter_by(site_id=sid, date=bing_date).all()),
            sum(r.impressions or 0 for r in s.query(BingQuery).filter_by(site_id=sid, date=bing_date).all()),
        ) if bing_date else (0, 0)
        # Device breakdown from live GSC if available
        gsc_devices = {}
        if gsc_live and gsc_live.get('this', {}).get('devices'):
            gsc_devices = gsc_live['this']['devices']
        refresh_item = (s.query(__import__('core.db', fromlist=['ContentRefreshItem'])
                                .ContentRefreshItem)
                        .filter_by(site_id=sid, status='pending')
                        .order_by(__import__('core.db', fromlist=['ContentRefreshItem'])
                                  .ContentRefreshItem.refresh_score.desc())
                        .limit(5).all())

    # ── Aggregate GSC data ────────────────────────────────────────────────────
    page_agg = defaultdict(lambda: {'clicks': 0, 'impressions': 0,
                                    'pos_sum': 0.0, 'count': 0})
    for p in recent_gsc:
        page_agg[p.page]['clicks']      += p.clicks or 0
        page_agg[p.page]['impressions'] += p.impressions or 0
        page_agg[p.page]['pos_sum']     += p.position or 0.0
        page_agg[p.page]['count']       += 1

    top_pages    = sorted([{'page': u, 'clicks': v['clicks'],
                            'impressions': v['impressions'],
                            'position': v['pos_sum']/v['count'] if v['count'] else 0}
                           for u, v in page_agg.items()],
                          key=lambda x: -x['clicks'])[:10]

    total_clicks = sum(v['clicks'] for v in page_agg.values())
    total_imps   = sum(v['impressions'] for v in page_agg.values())
    ctr          = total_clicks / total_imps * 100 if total_imps else 0

    # Use live GSC for prev-week comparison
    prev_clicks = prev_imps = 0
    if gsc_live and gsc_live.get('prev'):
        prev_clicks = sum(v.get('clicks', 0) for v in gsc_live['prev'].get('pages', {}).values())
        prev_imps   = sum(v.get('impressions', 0) for v in gsc_live['prev'].get('pages', {}).values())

    # GA4 totals
    total_sessions = sum(r.sessions or 0 for r in ga4_rows)
    total_leads    = sum(r.conversions or 0 for r in ga4_rows)

    # Traffic trend — group all GSC pages by period date → clicks sum
    period_clicks = defaultdict(int)
    for p in all_gsc_pages:
        period_clicks[p.date] += p.clicks or 0
    trend_data = sorted(period_clicks.items())[-12:]  # last 12 periods

    # Rankings buckets
    buckets = {'Top 3': 0, '4-10': 0, '11-30': 0, '31-100': 0, 'Not Ranked': 0}
    total_kws = 0
    with get_session() as s:
        total_kws = s.query(Keyword).filter_by(site_id=sid).count()
    for r, _ in rankings:
        if r.position:
            if r.position <= 3:    buckets['Top 3'] += 1
            elif r.position <= 10: buckets['4-10'] += 1
            elif r.position <= 30: buckets['11-30'] += 1
            else:                  buckets['31-100'] += 1
    buckets['Not Ranked'] = max(0, total_kws - sum(v for k, v in buckets.items() if k != 'Not Ranked'))

    # Health score
    health = _health_score(rankings, ctr, critical_cnt, avg_speed)

    # Slug helper
    def slug(url: str, maxlen: int = 45) -> str:
        return (url.replace(f'https://{site_domain}', '')
                   .replace(f'http://{site_domain}', '') or '/')[:maxlen]

    # Read AI summary from TXT report
    ai_summary = quick_wins = alerts_text = ''
    txt_path = os.path.join(REPORTS_DIR, f'{date.today().isoformat()}.txt')
    txt = ''
    if os.path.exists(txt_path):
        with open(txt_path, encoding='utf-8', errors='ignore') as f:
            txt = f.read()
        def _extract(marker, chars=2000):
            if marker not in txt:
                return ''
            s = txt.find(marker) + len(marker)
            e = txt.find('\n\n\n', s)
            return txt[s:e if e > 0 else s + chars].strip()
        ai_summary   = _extract('AI EXECUTIVE SUMMARY')
        quick_wins   = _extract("THIS WEEK'S QUICK WINS", 1500)
        alerts_text  = _extract('URGENT ALERTS', 800)

    # ── Build PDF ─────────────────────────────────────────────────────────────
    try:
        doc = PDF(site_domain)

        # ── Page 1: Health Score + KPI Cards + AI Summary ────────────────────
        doc.section('Site SEO Health Score')
        doc.health_score(health)

        doc.section('Weekly Performance at a Glance')
        click_chg = f'+{total_clicks - prev_clicks}' if prev_clicks and total_clicks > prev_clicks \
                    else (f'{total_clicks - prev_clicks}' if prev_clicks else 'baseline')
        doc.kpi_cards([
            ('ORGANIC CLICKS', f'{total_clicks:,}',
             click_chg, total_clicks >= prev_clicks if prev_clicks else None),
            ('IMPRESSIONS', f'{total_imps:,}',
             f'{total_imps - prev_imps:+,}' if prev_imps else 'baseline',
             total_imps >= prev_imps if prev_imps else None),
            ('CLICK RATE', f'{ctr:.2f}%',
             f'target: 3%', ctr >= 1.5),
        ])
        doc.kpi_cards([
            ('GA4 SESSIONS', f'{total_sessions:,}', '', None),
            ('LEADS', str(total_leads), '', total_leads > 0),
            ('LIVE BACKLINKS', f'{live_bl:,}', '', live_bl > 0),
        ])
        doc.kpi_cards([
            ('KEYWORDS TOP 10', str(sum(1 for r,_ in rankings if r.position and r.position<=10)),
             f'of {total_kws} tracked', None),
            ('AUDIT ISSUES', str(len(open_issues)),
             f'{critical_cnt} critical', critical_cnt == 0),
            ('OPPORTUNITIES', f'{len(opps):,}', 'to create content for', None),
        ])

        if ai_summary:
            doc.section('AI Executive Summary (DeepSeek Analysis)')
            doc.text_block(ai_summary, 1800)

        # ── Page 2: Traffic Trend + Rankings Distribution ─────────────────────
        doc.section('Traffic Trend & Rankings Distribution')
        trend_chart   = _traffic_trend_chart(trend_data) if len(trend_data) >= 3 else b''
        ranking_chart = _rankings_distribution_chart(buckets)
        doc.two_charts(trend_chart, ranking_chart)

        # Rankings gains/losses
        gains  = [(kw.keyword, prev_rankings.get(kw.id, 0), r.position)
                  for r, kw in rankings if r.position and
                  prev_rankings.get(kw.id, 999) > r.position][:5]
        losses = [(kw.keyword, prev_rankings.get(kw.id, 0), r.position)
                  for r, kw in rankings if r.position and
                  prev_rankings.get(kw.id, 0) and
                  prev_rankings.get(kw.id) < r.position][:5]

        if gains or losses:
            doc.section('Keyword Movers This Week')
            if gains:
                doc.p.set_font('Helvetica', 'B', 9)
                doc.p.set_text_color(*GREEN)
                doc.p.cell(0, 5, '  IMPROVED RANKINGS:', ln=True)
                doc.p.set_text_color(*TEXT_DARK)
                doc.table(['Keyword', 'Was', 'Now', 'Change'],
                          [[kw[:38], str(was), str(now), f'+{was-now}']
                           for kw, was, now in gains],
                          [95, 25, 25, 30],
                          [LIGHT_GREEN] * len(gains))
            if losses:
                doc.p.set_font('Helvetica', 'B', 9)
                doc.p.set_text_color(*RED)
                doc.p.cell(0, 5, '  DROPPED RANKINGS:', ln=True)
                doc.p.set_text_color(*TEXT_DARK)
                doc.table(['Keyword', 'Was', 'Now', 'Drop'],
                          [[kw[:38], str(was), str(now), f'-{now-was}']
                           for kw, was, now in losses],
                          [95, 25, 25, 30],
                          [LIGHT_RED] * len(losses))

        # ── Page 3: Full Keyword Rankings ─────────────────────────────────────
        doc.section(f'Full Keyword Rankings (as of {latest_rank_date})')
        COMMERCIAL_KWS = {'nri property lawyer', 'nri property dispute lawyer india',
                          'nri criminal lawyer india', 'nri divorce lawyer india',
                          'power of attorney for nri', '498a against nri husband',
                          'nri legal services', 'example legal firm',
                          'nri lawyer delhi', 'fir quashing for nri',
                          'anticipatory bail for nri'}
        rank_colors = []
        rank_rows   = []
        for r, kw in rankings[:25]:
            is_comm = kw.keyword.lower() in COMMERCIAL_KWS
            if r.position <= 3:     bg = LIGHT_GREEN
            elif r.position <= 10:  bg = (220, 255, 220)
            elif r.position <= 30:  bg = LIGHT_YELLOW
            else:                   bg = (255, 245, 230)
            rank_colors.append(bg)
            prev = prev_rankings.get(kw.id)
            chg  = f'+{prev-r.position}' if prev and prev > r.position else \
                   (f'-{r.position-prev}' if prev and prev < r.position else '=')
            rank_rows.append([
                ('* ' if is_comm else '') + kw.keyword[:38],
                kw.country,
                str(r.position),
                chg if prev else 'new',
                slug(r.url or '')[:25]
            ])
        if rank_rows:
            doc.table(['Keyword (* = commercial)', 'Cty', 'Pos', 'Chg', 'URL'],
                      rank_rows, [88, 15, 15, 18, 45], rank_colors)
        else:
            doc.text_block('No rankings yet. Run: python run.py rank')

        # ── Page 4: Country + Competitor charts ───────────────────────────────
        doc.section('Geographic Performance & Competitor Comparison')
        country_data = [(r.country or '', r.clicks or 0) for r in country_rows]
        comp_chart   = _competitor_chart(vis_scores)
        cntry_chart  = _country_chart(country_data) if country_data else b''
        doc.two_charts(cntry_chart, comp_chart)

        # Top Pages table
        doc.section('Top Pages This Week (GSC)')
        if top_pages:
            doc.table(
                ['Page', 'Clicks', 'Impressions', 'CTR%', 'Avg Pos'],
                [[slug(p['page'], 45), str(p['clicks']), str(p['impressions']),
                  f'{p["clicks"]/p["impressions"]*100:.1f}' if p['impressions'] else '0',
                  f'{p["position"]:.0f}']
                 for p in top_pages],
                [90, 20, 30, 22, 18]
            )

        # GA4 channels
        if ga4_rows:
            doc.section('Traffic Sources (GA4)')
            ch = defaultdict(lambda: {'s': 0, 'c': 0})
            for r in ga4_rows:
                ch[r.channel or 'Unknown']['s'] += r.sessions or 0
                ch[r.channel or 'Unknown']['c'] += r.conversions or 0
            doc.table(['Channel', 'Sessions', 'Leads', 'Lead Rate'],
                      [[ch_name, str(v['s']), str(v['c']),
                        f'{v["c"]/v["s"]*100:.1f}%' if v['s'] else '0%']
                       for ch_name, v in sorted(ch.items(), key=lambda x: -x[1]['s'])],
                      [90, 35, 30, 30])

        # Bing Webmaster Tools
        if bing_rows:
            doc.section(f'Bing Search Performance  ({bing_date})')
            b_clicks, b_imps = bing_totals
            b_ctr = f'{b_clicks/b_imps*100:.2f}%' if b_imps else 'n/a'
            doc.text_block(
                f'Total Bing clicks: {b_clicks:,}  |  Impressions: {b_imps:,}  |  CTR: {b_ctr}', 400)
            doc.table(
                ['Query', 'Clicks', 'Impressions', 'CTR%', 'Avg Pos'],
                [[r.query[:40], str(r.clicks or 0), str(r.impressions or 0),
                  f'{r.clicks/r.impressions*100:.1f}' if r.impressions else '0',
                  f'{r.avg_position:.0f}' if r.avg_position else '-']
                 for r in bing_rows],
                [90, 22, 32, 22, 18]
            )

        # Mobile vs Desktop
        if gsc_devices:
            doc.section('Mobile vs Desktop (Google Search)')
            total_dev = sum(d.get('clicks', 0) for d in gsc_devices.values()) or 1
            dev_rows = []
            for dev in ['MOBILE', 'DESKTOP', 'TABLET']:
                d = gsc_devices.get(dev, gsc_devices.get(dev.capitalize(), {}))
                clk = d.get('clicks', 0)
                imp = d.get('impressions', 0)
                pct_share = clk / total_dev * 100
                bar = '█' * int(pct_share / 5)
                dev_rows.append([dev, f'{pct_share:.0f}%', str(clk), str(imp), bar])
            doc.table(['Device', 'Share', 'Clicks', 'Impressions', 'Bar'],
                      dev_rows, [35, 22, 25, 35, 65])
            doc.text_block('Note: GSC omits device data for low-traffic queries (privacy threshold) — '
                           'proportions are representative even if absolute counts are lower than total.', 600)

        # ── Page 5: Opportunities ─────────────────────────────────────────────
        total_opps = sum(1 for o in opps)
        doc.section(f'Keyword Opportunities  {total_opps} discovered, top commercial shown')
        opp_chart = _opportunity_scatter(opps)
        if opp_chart:
            doc.chart(opp_chart, 140)
        top_opps = [o for o in opps if o.intent in ('commercial', 'near-commercial')][:15]
        if top_opps:
            doc.table(
                ['Keyword', 'Intent', 'Est. Vol/mo', 'KD'],
                [[o.keyword[:42], o.intent or '-',
                  str(o.est_volume or '-'), str(o.kd_score or '-')]
                 for o in top_opps],
                [100, 35, 32, 18]
            )

        # ── Page 6: Technical + Audit ─────────────────────────────────────────
        doc.section('Technical Audit Issues')
        if open_issues:
            from collections import Counter
            type_counts  = Counter(i.issue_type for i in open_issues)
            sev_map      = {i.issue_type: i.severity for i in open_issues}
            sev_color    = {'critical': LIGHT_RED, 'warning': LIGHT_YELLOW, 'info': LIGHT_BLUE}
            summary_rows = sorted(type_counts.items(), key=lambda x: -x[1])
            doc.table(
                ['Issue Type', 'Count', 'Severity'],
                [[t.replace('_', ' ').title()[:40],
                  str(c),
                  (sev_map.get(t, 'info') or 'info').upper()]
                 for t, c in summary_rows],
                [100, 30, 55],
                [sev_color.get(sev_map.get(t, 'info'), LIGHT_BLUE) for t, _ in summary_rows]
            )
            doc.text_block(f'Total: {len(open_issues)} issues across {len(type_counts)} categories  '
                           f'({critical_cnt} critical)', 600)

        if ps_rows:
            doc.section('Core Web Vitals (Mobile)')
            ps_colors = [LIGHT_RED if (r.performance or 100) < 50 else
                         LIGHT_YELLOW if (r.performance or 100) < 70 else
                         LIGHT_GREEN for r in ps_rows]
            doc.table(
                ['Page', 'Score', 'LCP(s)', 'CLS', 'INP(ms)'],
                [[slug(r.page_url)[:38], str(r.performance or '-'),
                  f'{r.lcp:.1f}' if r.lcp else '-',
                  f'{r.cls:.3f}' if r.cls else '-',
                  f'{r.inp:.0f}' if r.inp else '-']
                 for r in ps_rows],
                [82, 22, 25, 25, 30], ps_colors
            )

        # Backlinks
        if top_bl:
            doc.section(f'Backlinks ({live_bl} live)')
            doc.table(
                ['Source Domain', 'Anchor Text', 'Status', 'First Seen'],
                [[b.source_domain[:35], (b.anchor_text or '')[:30],
                  b.status, str(b.first_seen)]
                 for b in top_bl],
                [65, 72, 22, 26]
            )
        else:
            doc.section('Backlinks')
            doc.text_block(
                'No backlink data yet.\n'
                '1. Register FREE at: ahrefs.com/webmaster-tools\n'
                '2. Verify example-legal.in via GSC\n'
                '3. Export backlinks CSV -> save to rankpilot/data/ahrefs_backlinks.csv\n'
                '4. Run: python run.py import-backlinks'
            )

        # ── Page 7: Community + Briefs + Alerts ───────────────────────────────
        if mentions:
            doc.section('Reddit Answer Opportunities')
            doc.table(
                ['Question', 'Subreddit'],
                [[(m.title or '')[:60],
                  (m.source_url or '').split('/r/')[-1].split('/')[0][:25]]
                 for m in mentions],
                [140, 45]
            )

        if new_comp:
            doc.section('New Competitor Pages This Week')
            doc.table(
                ['Competitor', 'Page Title', 'Detected'],
                [[cu.url.split('/')[2] if '/' in cu.url else comp.domain,
                  (cu.title or cu.url.rstrip('/').split('/')[-1])[:50],
                  str(cu.first_seen)]
                 for cu, comp in new_comp],
                [52, 110, 23]
            )

        if briefs:
            doc.section('AI Content Briefs (DeepSeek)')
            doc.table(
                ['Keyword', 'Status', 'Target Words', 'Created'],
                [[b.keyword[:40], b.status,
                  str(b.target_word_count or '-'),
                  str(b.created_at.date()) if b.created_at else '-']
                 for b in briefs],
                [95, 28, 32, 30]
            )

        if refresh_item:
            doc.section('Content Refresh Queue')
            doc.table(
                ['Keyword / Page', 'Score', 'Signal'],
                [[r.keyword[:45], str(int(r.refresh_score or 0)),
                  (r.reasons[0] if r.reasons else '')[:40]]
                 for r in refresh_item],
                [95, 22, 68]
            )

        if quick_wins:
            doc.section('Quick Wins This Week')
            doc.text_block(quick_wins, 1200)

        if alerts_text or alert_rows:
            doc.section('Urgent Alerts')
            if alerts_text:
                doc.text_block(alerts_text, 600)
            if alert_rows:
                al_colors = [LIGHT_RED if a.severity == 'critical' else LIGHT_YELLOW
                             for a in alert_rows]
                doc.table(
                    ['Type', 'Message', 'Severity'],
                    [[a.alert_type.replace('_', ' ')[:20],
                      (a.message or '')[:55], (a.severity or '').upper()]
                     for a in alert_rows],
                    [45, 115, 25], al_colors
                )

        # ── Footer ────────────────────────────────────────────────────────────
        doc.p.set_y(-15)
        doc.p.set_font('Helvetica', 'I', 7)
        doc.p.set_text_color(*TEXT_GRAY)
        doc.p.cell(0, 5,
                   f'RankPilot SEO Intelligence | {site_domain} | '
                   f'{datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")} | '
                   f'Powered by DeepSeek AI',
                   align='C')

        path = doc.save()
        print(f'  ✅ PDF saved: {path}')
        return path

    except Exception as e:
        import traceback
        print(f'  ⚠️ PDF failed: {e}')
        traceback.print_exc()
        return None


if __name__ == '__main__':
    build_pdf_report()
