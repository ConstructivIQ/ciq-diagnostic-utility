"""
reporters/html_reporter.py
Generates a self-contained HTML diagnostic report.
"""
from __future__ import annotations
import html as html_lib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from analyzers.ai_analyzer import DiagnosticAnalysis
import config

SEVERITY_STYLE = {
    "CRITICAL": ("#dc2626", "CRITICAL"),
    "HIGH":     ("#ea580c", "HIGH"),
    "MEDIUM":   ("#d97706", "MEDIUM"),
    "LOW":      ("#16a34a", "LOW"),
}
LEVEL_BADGE_COLOR = {
    "ERROR":    "#dc2626",
    "CRITICAL": "#7f1d1d",
    "FATAL":    "#7f1d1d",
    "WARNING":  "#d97706",
    "WARN":     "#d97706",
    "EXCEPTION":"#9333ea",
}


def e(text) -> str:
    return html_lib.escape(str(text or ""))


def generate_report(
    analysis: DiagnosticAnalysis,
    issue: Optional[dict] = None,
    log_entries: Optional[list] = None,
    api_results: Optional[list] = None,
    email_messages: Optional[list] = None,
    output_path: Optional[Path] = None,
) -> Path:
    output_path = output_path or Path(
        f"diagnostic_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    )
    html = _render(analysis, issue, log_entries or [], api_results or [], email_messages or [])
    output_path.write_text(html, encoding="utf-8")
    return output_path


def _render(analysis, issue, log_entries, api_results, email_messages) -> str:
    now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    sev_color, sev_label = SEVERITY_STYLE.get(analysis.severity.upper(), ("#d97706", "MEDIUM"))
    issue_key = issue.get("key", "---") if issue else "---"
    issue_title = issue.get("summary", "") if issue else ""

    factors_html = "".join(
        f'<li class="factor-item"><span class="bullet">-</span> {e(f)}</li>'
        for f in analysis.contributing_factors
    ) or "<li>None identified.</li>"

    questions_html = "".join(
        f'<li class="factor-item"><span class="bullet">?</span> {e(q)}</li>'
        for q in analysis.open_questions
    ) or "<li>None.</li>"

    actions_html = "".join(
        f'<li class="action-item"><span class="action-num">{i+1}</span><span>{e(a)}</span></li>'
        for i, a in enumerate(analysis.recommended_actions)
    ) or "<li>No actions generated.</li>"

    components_html = ", ".join(e(c) for c in analysis.affected_components) or "&mdash;"

    conf_pct = {"HIGH": 80, "MEDIUM": 50, "LOW": 25}.get(analysis.confidence.upper(), 50)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Diagnostic Report &ndash; {e(issue_key)}</title>
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
:root{{
  --bg:#F2F5FA;--surface:#FFF;--card:#F8FAFD;--border:#D8E0EC;--border-sub:#E8EEF6;
  --text:#0B1520;--text2:#3A4A60;--text3:#6A7B94;
  --amber:#C8880E;--amber-bg:#FDF3DC;
  --crit:#B91C1C;--high:#C2410C;--med:#A16207;--low:#166534;
  --ok:#15803D;--ok-bg:#DCFCE7;--err:#DC2626;--err-bg:#FEF2F2;
  --warn:#B45309;--warn-bg:#FFFBEB;
  --mono:'Courier New',monospace;--sans:system-ui,-apple-system,sans-serif;
  --radius:6px;--shadow:0 1px 3px rgba(0,0,0,.06)
}}
@media(prefers-color-scheme:dark){{
  :root:not([data-theme="light"]){{
    --bg:#0B1520;--surface:#121E30;--card:#1A2740;--border:#253650;--border-sub:#1E2E45;
    --text:#DDE6F2;--text2:#8EA8C8;--text3:#5A7898;
    --amber:#E8A020;--amber-bg:#1E1A00;
    --crit:#F87171;--high:#FB923C;--med:#FCD34D;--low:#4ADE80;
    --ok:#4ADE80;--ok-bg:#012210;--err:#F87171;--err-bg:#1C0808;
    --warn:#FCD34D;--warn-bg:#1C1400;
    --shadow:0 1px 3px rgba(0,0,0,.3)
  }}
}}
:root[data-theme="dark"]{{
  --bg:#0B1520;--surface:#121E30;--card:#1A2740;--border:#253650;--border-sub:#1E2E45;
  --text:#DDE6F2;--text2:#8EA8C8;--text3:#5A7898;
  --amber:#E8A020;--amber-bg:#1E1A00;
  --crit:#F87171;--high:#FB923C;--med:#FCD34D;--low:#4ADE80;
  --ok:#4ADE80;--ok-bg:#012210;--err:#F87171;--err-bg:#1C0808;
  --warn:#FCD34D;--warn-bg:#1C1400;
  --shadow:0 1px 3px rgba(0,0,0,.3)
}}
body{{font-family:var(--sans);background:var(--bg);color:var(--text);line-height:1.6;font-size:14px;padding:24px}}
a{{color:var(--amber)}}
.container{{max-width:980px;margin:0 auto}}
.card{{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:20px 24px;box-shadow:var(--shadow);margin-bottom:16px}}
.card-label{{font-family:var(--mono);font-size:10px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:var(--text3);margin-bottom:12px;display:flex;align-items:center;gap:8px}}
.card-label::after{{content:'';flex:1;height:1px;background:var(--border-sub)}}
.sev-header{{background:var(--surface);border-bottom:1px solid var(--border);padding:12px 24px;margin:-24px -24px 24px;display:flex;align-items:center;gap:14px;box-shadow:var(--shadow)}}
.sev-badge{{display:inline-flex;align-items:center;gap:6px;padding:4px 12px;border-radius:4px;font-family:var(--mono);font-size:11px;font-weight:700;letter-spacing:.06em;background:{sev_color}20;color:{sev_color}}}
.sev-dot{{width:7px;height:7px;border-radius:50%;background:{sev_color};flex-shrink:0}}
.header-title{{font-family:var(--mono);font-size:13px;font-weight:500;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.header-meta{{font-size:11px;color:var(--text3);display:flex;gap:16px;flex-shrink:0}}
.page-headline{{font-family:var(--mono);font-size:20px;font-weight:600;margin-bottom:6px;text-wrap:balance}}
.page-meta{{display:flex;gap:18px;flex-wrap:wrap;font-size:12px;color:var(--text3);margin-bottom:24px}}
.page-meta strong{{color:var(--text2);font-weight:500}}
.grid-2{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
@media(max-width:640px){{.grid-2{{grid-template-columns:1fr}}}}
.summary-text{{font-size:14px;line-height:1.7;color:var(--text2);margin-bottom:16px}}
.root-cause-box{{background:var(--amber-bg);border:1px solid var(--amber);border-left:3px solid var(--amber);border-radius:4px;padding:12px 14px}}
.root-cause-box .lbl{{font-family:var(--mono);font-size:10px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:var(--amber);margin-bottom:4px}}
.root-cause-box p{{font-size:13px;color:var(--text)}}
.action-item{{display:flex;gap:10px;align-items:flex-start;padding:9px 0;border-bottom:1px solid var(--border-sub)}}
.action-item:last-child{{border-bottom:none}}
.action-num{{font-family:var(--mono);font-size:11px;font-weight:600;color:var(--text3);background:var(--card);border:1px solid var(--border);width:22px;height:22px;border-radius:4px;display:flex;align-items:center;justify-content:center;flex-shrink:0;margin-top:1px}}
.factor-item{{display:flex;gap:8px;align-items:baseline;padding:6px 0;border-bottom:1px solid var(--border-sub);font-size:13px;color:var(--text2)}}
.factor-item:last-child{{border-bottom:none}}
.bullet{{font-family:var(--mono);font-size:11px;color:var(--text3);flex-shrink:0}}
.conf-bar-track{{height:5px;background:var(--border);border-radius:3px;overflow:hidden;margin-top:6px}}
.conf-bar-fill{{height:100%;background:var(--amber);border-radius:3px;width:{conf_pct}%}}
.chip{{font-family:var(--mono);font-size:11px;padding:2px 8px;border-radius:3px;background:var(--card);border:1px solid var(--border);color:var(--text2);display:inline-block;margin:2px}}
.log-wrap{{overflow-x:auto}}
.log-table{{width:100%;border-collapse:collapse;min-width:600px}}
.log-table th{{font-family:var(--mono);font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--text3);font-weight:500;padding:7px 10px;text-align:left;border-bottom:2px solid var(--border);white-space:nowrap}}
.log-table td{{padding:8px 10px;border-bottom:1px solid var(--border-sub);vertical-align:top;font-size:12px}}
.log-table tbody tr:hover td{{background:var(--card)}}
.ts,.src{{font-family:var(--mono);font-size:11px;color:var(--text3);white-space:nowrap}}
.msg{{font-family:var(--mono);font-size:11.5px;white-space:pre-wrap;word-break:break-all;max-width:440px}}
.lvl{{display:inline-block;font-family:var(--mono);font-size:10px;font-weight:600;padding:2px 6px;border-radius:3px}}
.probe-row{{display:flex;align-items:center;gap:10px;padding:9px 0;border-bottom:1px solid var(--border-sub);flex-wrap:wrap}}
.probe-row:last-child{{border-bottom:none}}
.probe-status{{font-family:var(--mono);font-size:11px;font-weight:600;padding:2px 8px;border-radius:3px;flex-shrink:0}}
.probe-ok{{background:var(--ok-bg);color:var(--ok)}}
.probe-err{{background:var(--err-bg);color:var(--err)}}
.probe-url{{font-family:var(--mono);font-size:12px;flex:1;word-break:break-all}}
.probe-lat{{font-family:var(--mono);font-size:11px;color:var(--text3)}}
.email-item{{padding:12px 0;border-bottom:1px solid var(--border-sub)}}
.email-item:last-child{{border-bottom:none}}
.email-subject{{font-size:13px;font-weight:500;margin-bottom:2px}}
.email-meta{{font-family:var(--mono);font-size:11px;color:var(--text3);margin-bottom:6px}}
.email-body{{font-size:12px;line-height:1.6;color:var(--text2);background:var(--card);border:1px solid var(--border-sub);border-radius:4px;padding:8px 10px;white-space:pre-wrap}}
.comment{{padding:10px 0;border-top:1px solid var(--border-sub)}}
.comment-meta{{font-size:11px;color:var(--text3);margin-bottom:3px}}
.comment-meta strong{{color:var(--text2);font-weight:500}}
.comment-body{{font-size:13px;color:var(--text2)}}
.info-table td{{padding:5px 0;font-size:12.5px;vertical-align:top}}
.info-table td:first-child{{font-family:var(--mono);font-size:11px;color:var(--text3);padding-right:14px;white-space:nowrap;width:110px}}
.info-table tr+tr td{{border-top:1px solid var(--border-sub)}}
.footer{{margin-top:40px;padding-top:16px;border-top:1px solid var(--border);display:flex;justify-content:space-between;font-family:var(--mono);font-size:11px;color:var(--text3);flex-wrap:wrap;gap:8px}}
</style>
</head>
<body>
<div class="container">
<div class="sev-header">
  <span class="sev-badge"><span class="sev-dot"></span>{e(analysis.severity)}</span>
  <span class="header-title">{e(issue_key)} &mdash; {e(issue_title)}</span>
  <div class="header-meta">
    <span>{len(log_entries)} log entries</span>
    <span>{len(api_results)} API probes</span>
    <span>{len(email_messages)} emails</span>
  </div>
</div>

<h1 class="page-headline">{e(issue_title or "Diagnostic Report")}</h1>
<div class="page-meta">
  {"".join(f'<span><strong>{k}</strong> {e(v)}</span>' for k, v in [
    ("Issue", issue_key),
    ("Priority", issue.get("priority","") if issue else ""),
    ("Status", issue.get("status","") if issue else ""),
    ("Reporter", issue.get("reporter","") if issue else ""),
    ("Generated", now),
  ] if v)}
</div>

<div class="card">
  <div class="card-label">Executive Summary</div>
  <p class="summary-text">{e(analysis.summary)}</p>
  <div class="root-cause-box">
    <div class="lbl">Likely Root Cause</div>
    <p>{e(analysis.likely_root_cause)}</p>
  </div>
</div>

<div class="card">
  <div class="card-label">Recommended Actions</div>
  <ol style="list-style:none">{actions_html}</ol>
</div>

<div class="grid-2">
  <div class="card">
    <div class="card-label">Contributing Factors</div>
    <ul style="list-style:none">{factors_html}</ul>
  </div>
  <div class="card">
    <div class="card-label">Open Questions</div>
    <ul style="list-style:none">{questions_html}</ul>
  </div>
</div>

<div class="card">
  <div class="card-label">Affected Components</div>
  <div>{components_html}</div>
  <div style="margin-top:14px">
    <div style="display:flex;justify-content:space-between;font-size:11px;color:var(--text3)">
      <span style="font-family:var(--mono);letter-spacing:.06em;text-transform:uppercase">AI Confidence</span>
      <span style="font-family:var(--mono);color:var(--amber);font-weight:600">{e(analysis.confidence)}</span>
    </div>
    <div class="conf-bar-track"><div class="conf-bar-fill"></div></div>
  </div>
</div>

{_render_jira(issue)}
{_render_logs(log_entries)}
{_render_api(api_results)}
{_render_emails(email_messages)}

<div class="footer">
  <span>ConstructivIQ Diagnostic Utility</span>
  <span>Generated {now} &middot; Model: {e(config.ANTHROPIC_MODEL)}</span>
</div>
</div>
</body>
</html>"""


def _render_jira(issue):
    if not issue:
        return ""
    rows = "".join(
        f"<tr><td>{e(k)}</td><td>{e(v)}</td></tr>"
        for k, v in [
            ("Key", issue.get("key")),
            ("Type", issue.get("issue_type")),
            ("Priority", issue.get("priority")),
            ("Status", issue.get("status")),
            ("Reporter", issue.get("reporter")),
            ("Assignee", issue.get("assignee")),
            ("Labels", ", ".join(issue.get("labels", []))),
            ("Components", ", ".join(issue.get("components", []))),
            ("Created", issue.get("created")),
            ("Updated", issue.get("updated")),
        ] if v
    )
    desc = e(issue.get("description", "(none)"))
    comments_html = _render_comments(issue.get("comments", []))
    return f"""<div class="card">
  <div class="card-label">Jira Issue &mdash; <a href="{e(issue.get('url','#'))}" target="_blank">{e(issue.get('key'))}</a></div>
  <table class="info-table"><tbody>{rows}</tbody></table>
  <div style="margin-top:14px;font-size:12px;font-family:var(--mono);color:var(--text3);margin-bottom:4px;text-transform:uppercase;letter-spacing:.06em">Description</div>
  <div style="background:var(--card);border:1px solid var(--border-sub);border-radius:4px;padding:10px 12px;font-size:13px;white-space:pre-wrap;color:var(--text2)">{desc}</div>
  {comments_html}
</div>"""


def _render_comments(comments):
    if not comments:
        return ""
    items = []
    for c in comments:
        items.append(
            f'<div class="comment">'
            f'<div class="comment-meta"><strong>{e(c.get("author",""))}</strong> &middot; {e(c.get("created",""))}</div>'
            f'<div class="comment-body">{e(c.get("body",""))}</div>'
            f'</div>'
        )
    return f'<div style="margin-top:14px">{"".join(items)}</div>'


def _render_logs(log_entries):
    if not log_entries:
        return ""
    rows = []
    for entry in log_entries[:50]:
        color = LEVEL_BADGE_COLOR.get(entry.level.upper(), "#64748b")
        rows.append(
            f'<tr>'
            f'<td><span class="lvl" style="background:{color}22;color:{color}">{e(entry.level)}</span></td>'
            f'<td class="ts">{e(entry.timestamp or "---")}</td>'
            f'<td class="src">{e(Path(entry.source_file).name)}:{e(entry.line_number)}</td>'
            f'<td><div class="msg">{e(entry.message[:400])}</div></td>'
            f'</tr>'
        )
    return f"""<div class="card">
  <div class="card-label">Application Logs ({len(log_entries)} entries)</div>
  <div class="log-wrap">
    <table class="log-table">
      <thead><tr><th>Level</th><th>Timestamp</th><th>Source</th><th>Message</th></tr></thead>
      <tbody>{"".join(rows)}</tbody>
    </table>
  </div>
</div>"""


def _render_api(api_results):
    if not api_results:
        return ""
    rows = []
    for r in api_results:
        cls = "probe-ok" if r.ok else "probe-err"
        code = str(r.status_code) if r.status_code else "ERR"
        rows.append(
            f'<div class="probe-row">'
            f'<span class="probe-status {cls}">{code}</span>'
            f'<span class="probe-url">{e(r.url)}</span>'
            f'<span class="probe-lat">{e(r.latency_ms)}ms</span>'
            + (f'<span style="font-size:11px;color:var(--err)">{e(r.error)}</span>' if r.error else "")
            + f'</div>'
        )
    return f"""<div class="card">
  <div class="card-label">API Health Probes</div>
  {"".join(rows)}
</div>"""


def _render_emails(email_messages):
    if not email_messages:
        return ""
    items = []
    for em in email_messages[:10]:
        items.append(
            f'<div class="email-item">'
            f'<div class="email-subject">{e(em.subject)}</div>'
            f'<div class="email-meta">{e(em.sender)} &middot; {e(em.date)}</div>'
            f'<div class="email-body">{e(em.body[:600])}</div>'
            f'</div>'
        )
    return f"""<div class="card">
  <div class="card-label">Support Emails ({len(email_messages)} messages)</div>
  {"".join(items)}
</div>"""


from pathlib import Path  # noqa: E402
