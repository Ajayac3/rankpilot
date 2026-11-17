"""RankPilot — HTML email sender with PDF attachment."""
import os, sys, ssl, smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import SMTP_USER, SMTP_PASS, REPORT_RECIPIENTS, TARGET_DOMAIN


def _html_email(report_text: str, site_domain: str,
                total_clicks: int = 0, prev_clicks: int = 0,
                total_leads: int = 0, health_score: int = 0,
                ai_summary: str = '') -> str:
    click_chg  = total_clicks - prev_clicks
    chg_color  = '#27ae60' if click_chg >= 0 else '#e74c3c'
    chg_symbol = '+' if click_chg >= 0 else ''
    health_clr = '#27ae60' if health_score >= 70 else '#f39c12' if health_score >= 50 else '#e74c3c'
    # Extract first paragraph of AI summary for email
    ai_snippet = ''
    for line in ai_summary.split('\n'):
        line = line.strip().lstrip('*').strip()
        if len(line) > 50:
            ai_snippet = line[:350] + '...'
            break
    date_str = datetime.now().strftime('%d %B %Y')

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width"></head>
<body style="margin:0;padding:0;background:#f4f6f9;font-family:Arial,sans-serif">
<div style="max-width:600px;margin:0 auto;background:#ffffff">

  <!-- Header -->
  <div style="background:#0052A5;padding:24px 20px;text-align:center">
    <h1 style="color:white;margin:0;font-size:20px">RankPilot Weekly SEO Report</h1>
    <p style="color:rgba(255,255,255,0.8);margin:6px 0 0">{site_domain} &nbsp;|&nbsp; {date_str}</p>
  </div>

  <!-- Health Score Banner -->
  <div style="background:{health_clr};padding:10px 20px;text-align:center">
    <span style="color:white;font-size:15px;font-weight:bold">
      SEO Health Score: {health_score}/100
      {'✅ Healthy' if health_score >= 70 else '⚠️ Needs Work' if health_score >= 50 else '🔴 Critical'}
    </span>
  </div>

  <!-- KPI Cards -->
  <div style="padding:20px;background:#f8f9fc">
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr>
        <td width="33%" style="padding:6px">
          <div style="background:white;border:1px solid #e0e0e0;border-radius:8px;padding:14px;text-align:center">
            <div style="font-size:28px;font-weight:bold;color:#0052A5">{total_clicks:,}</div>
            <div style="font-size:11px;color:#666;margin-top:4px">Organic Clicks</div>
            <div style="font-size:12px;color:{chg_color};font-weight:bold;margin-top:3px">
              {chg_symbol}{click_chg:,} vs last week
            </div>
          </div>
        </td>
        <td width="33%" style="padding:6px">
          <div style="background:white;border:1px solid #e0e0e0;border-radius:8px;padding:14px;text-align:center">
            <div style="font-size:28px;font-weight:bold;color:#0052A5">{total_leads}</div>
            <div style="font-size:11px;color:#666;margin-top:4px">Leads This Week</div>
            <div style="font-size:12px;color:{'#27ae60' if total_leads > 0 else '#999'};font-weight:bold;margin-top:3px">
              {'WhatsApp + Form' if total_leads > 0 else 'Set up GA4 events'}
            </div>
          </div>
        </td>
        <td width="33%" style="padding:6px">
          <div style="background:white;border:1px solid #e0e0e0;border-radius:8px;padding:14px;text-align:center">
            <div style="font-size:28px;font-weight:bold;color:{health_clr}">{health_score}</div>
            <div style="font-size:11px;color:#666;margin-top:4px">SEO Health Score</div>
            <div style="font-size:12px;color:{health_clr};font-weight:bold;margin-top:3px">
              /100
            </div>
          </div>
        </td>
      </tr>
    </table>
  </div>

  <!-- AI Summary -->
  {f'''<div style="padding:0 20px 20px">
    <div style="background:#f0f4ff;border-left:4px solid #0052A5;padding:14px;border-radius:0 6px 6px 0">
      <div style="font-size:11px;color:#0052A5;font-weight:bold;margin-bottom:6px">
        AI EXECUTIVE SUMMARY (DeepSeek)
      </div>
      <p style="margin:0;font-size:12px;color:#333;line-height:1.6">{ai_snippet}</p>
    </div>
  </div>''' if ai_snippet else ''}

  <!-- PDF Notice -->
  <div style="padding:0 20px 20px;text-align:center">
    <div style="background:#fff8e6;border:1px solid #ffd54f;border-radius:8px;padding:14px">
      <p style="margin:0;font-size:13px;color:#555">
        📊 <strong>Full PDF report attached</strong> — includes traffic charts,
        keyword rankings, competitor analysis, and 726 keyword opportunities.
      </p>
    </div>
  </div>

  <!-- Footer -->
  <div style="background:#0052A5;padding:14px 20px;text-align:center">
    <p style="color:rgba(255,255,255,0.7);margin:0;font-size:11px">
      RankPilot SEO Intelligence &nbsp;|&nbsp; Generated {date_str}
      &nbsp;|&nbsp; Powered by DeepSeek AI
    </p>
  </div>

</div>
</body>
</html>"""


def send_report(report_text: str, site_domain: str = TARGET_DOMAIN,
                pdf_path: str = None,
                total_clicks: int = 0, prev_clicks: int = 0,
                total_leads: int = 0, health_score: int = 0,
                ai_summary: str = '') -> bool:

    if not SMTP_USER or not SMTP_PASS:
        print('  ⚠️ SMTP not configured — skipping email (set SMTP_USER + SMTP_PASS in .env)')
        return False

    has_alerts = any(c in report_text for c in ['URGENT ALERTS', '🔴', 'CRITICAL'])
    status     = '⚠️ ACTION NEEDED' if has_alerts else '✅ All Good'
    date_str   = datetime.now().strftime('%d %b %Y')
    subject    = f'📊 {status} — RankPilot SEO Brief {date_str} | {site_domain}'

    msg = MIMEMultipart('mixed')
    msg['From']    = f'RankPilot SEO <{SMTP_USER}>'
    msg['To']      = ', '.join(REPORT_RECIPIENTS)
    msg['Subject'] = subject

    # HTML + plain text alternatives
    alt = MIMEMultipart('alternative')
    alt.attach(MIMEText(report_text, 'plain'))
    alt.attach(MIMEText(
        _html_email(report_text, site_domain, total_clicks, prev_clicks,
                    total_leads, health_score, ai_summary),
        'html'
    ))
    msg.attach(alt)

    # Attach PDF
    if pdf_path and os.path.exists(pdf_path):
        with open(pdf_path, 'rb') as f:
            pdf_data = f.read()
        pdf_part = MIMEApplication(pdf_data, Name=os.path.basename(pdf_path))
        pdf_part['Content-Disposition'] = f'attachment; filename="{os.path.basename(pdf_path)}"'
        msg.attach(pdf_part)

    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP('smtp.gmail.com', 587) as s:
            s.ehlo(); s.starttls(context=ctx); s.ehlo()
            s.login(SMTP_USER, SMTP_PASS)
            s.sendmail(SMTP_USER, REPORT_RECIPIENTS, msg.as_string())
        print(f'  📧 HTML report emailed to: {", ".join(REPORT_RECIPIENTS)}')
        return True
    except Exception as e:
        print(f'  ❌ Email failed: {e}')
        return False
