"""
reporters/tabs/project.py
──────────────────────────
Project Errors tab: all CloudWatch error + warn lines for a specific project_id.

Renders:
  • KPI tiles    — total events, unique import_log_ids, latest timestamp, environment
  • Error table  — timestamp · source · import_log_id · error name · message
  • ID pills     — all unique import_log_ids affected
  • Log groups   — ECS and Lambda groups queried
"""
from __future__ import annotations

from reporters.components import _stat, e


def render(project_data: dict) -> str:
    if not project_data:
        return '<div class="card"><p style="color:var(--fg3)">No project data available.</p></div>'

    project_id     = project_data.get("project_id", "")
    env            = project_data.get("env", "")
    hours          = project_data.get("hours", 24)
    region         = project_data.get("region", "")
    errors         = project_data.get("errors", [])
    total          = project_data.get("total", 0)
    group_errors   = project_data.get("group_errors", {})
    log_groups     = project_data.get("log_groups", {})
    message_filter = project_data.get("message_filter")

    ecs_group    = log_groups.get("ecs") or "—"
    lambda_group = log_groups.get("lambda") or "—"

    # Unique import_log_ids
    unique_ids = list(dict.fromkeys(
        r["import_log_id"] for r in errors if r.get("import_log_id")
    ))

    # Latest timestamp
    latest_ts = errors[0].get("ts", "—") if errors else "—"

    # KPI row
    kpi = (
        _stat(str(total),           "Total Events",          "var(--sev-err)" if total else "var(--accent)") +
        _stat(str(len(unique_ids)), "Unique Import Log IDs", "var(--sev-warn)" if unique_ids else "var(--accent)") +
        _stat(latest_ts,            "Latest Event",          "var(--sev-err)" if errors else "var(--accent)") +
        _stat(env.upper(),          "Environment",           "var(--ac)")
    )

    # Header badges
    filter_badge = (
        f'<span class="sync-badge" style="background:rgba(99,102,241,.15);color:#818cf8;">'
        f'🔍 filter: {e(message_filter)}</span>'
        if message_filter else ""
    )
    header = f"""
<div class="sync-header">
  <span class="sync-badge">{'🔴 PROD' if env == 'prod' else '🟡 ' + env.upper()}</span>
  <span class="sync-badge">⏱ Last {hours}h</span>
  <span class="sync-badge" style="font-family:monospace;font-size:11px;">{e(project_id)}</span>
  {filter_badge}
  <span class="sync-note">Region: {e(region)}</span>
</div>"""

    # Group errors card (shown only when a log group query fails at the API level)
    group_err_card = ""
    if group_errors:
        rows = "".join(
            f'<div class="kv-row"><span style="font-family:monospace;font-size:11px;">{e(g)}</span>'
            f'<span style="color:var(--sev-err);font-size:11px;">{e(msg)}</span></div>'
            for g, msg in group_errors.items()
        )
        group_err_card = f"""
<div class="card" style="border-left:4px solid var(--sev-err);">
  <div class="card-hd"><h2>Log Group Query Errors</h2></div>
  {rows}
</div>"""

    # Error / warn table
    if errors:
        table_rows = ""
        for row in errors:
            imp_id   = row.get("import_log_id", "")
            imp_cell = (
                f'<code class="expand-cell" style="cursor:pointer;">{e(imp_id[:18])}…</code>'
                if imp_id else '<span style="color:var(--fg3)">—</span>'
            )
            err_name  = row.get("error_name", "")
            msg       = row.get("message", row.get("raw", "")[:180])
            source    = row.get("source", "")
            src_color = "#22c55e" if source == "ECS" else "#f59e0b"
            level     = row.get("level", "ERROR")
            lv_color  = "var(--sev-err)" if level in ("ERROR", "CRITICAL", "FATAL") else "var(--sev-warn)"

            table_rows += f"""
<tr>
  <td style="font-size:11px;white-space:nowrap;color:var(--fg3);">{e(row.get('ts', ''))}</td>
  <td><span style="background:rgba(0,0,0,.3);color:{src_color};border-radius:3px;padding:1px 6px;font-size:10px;font-weight:600;">{e(source)}</span></td>
  <td><span style="color:{lv_color};font-size:10px;font-weight:600;">{e(level)}</span></td>
  <td>{imp_cell}</td>
  <td style="font-size:11px;color:var(--sev-err);">{e(err_name)}</td>
  <td class="expand-cell" style="font-size:11px;max-width:340px;cursor:pointer;">{e(msg)}</td>
</tr>"""

        error_table = f"""
<div class="card">
  <div class="card-hd">
    <h2>Log Lines</h2>
    <span class="chip">{total} events · newest first</span>
  </div>
  <div style="overflow-x:auto;">
    <table class="err-table">
      <thead><tr>
        <th>Timestamp (IST)</th>
        <th>Source</th>
        <th>Level</th>
        <th>Import Log ID</th>
        <th>Error Type</th>
        <th>Message</th>
      </tr></thead>
      <tbody>{table_rows}</tbody>
    </table>
  </div>
</div>"""
    else:
        error_table = f"""
<div class="card">
  <div class="card-hd"><h2>Log Lines</h2></div>
  <p style="color:var(--fg3);padding:20px 0;text-align:center;">
    No errors or warnings found for this project in the last {hours}h.
  </p>
</div>"""

    # Import log IDs pill row
    ids_card = ""
    if unique_ids:
        id_pills = "".join(
            f'<code style="background:var(--bg3);border:1px solid var(--border);'
            f'border-radius:4px;padding:3px 8px;font-size:11px;margin:2px;">{e(i)}</code>'
            for i in unique_ids
        )
        ids_card = f"""
<div class="card">
  <div class="card-hd">
    <h2>Import Log IDs Affected</h2>
    <span class="chip">{len(unique_ids)} unique IDs</span>
  </div>
  <div style="display:flex;flex-wrap:wrap;gap:4px;padding:8px 0;">{id_pills}</div>
</div>"""

    # Log groups info
    lg_card = f"""
<div class="card" style="font-size:12px;">
  <div class="card-hd"><h2>Log Groups Queried</h2><span class="chip">Region: {e(region)}</span></div>
  <div style="display:grid;grid-template-columns:120px 1fr;gap:6px 16px;padding:4px 0;">
    <span style="color:var(--fg3);">ECS (JOB)</span>
    <code style="font-size:11px;">{e(ecs_group)}</code>
    <span style="color:var(--fg3);">Lambda</span>
    <code style="font-size:11px;">{e(lambda_group)}</code>
  </div>
</div>"""

    return f"""
{header}
<div class="stats-grid" style="grid-template-columns:repeat(4,1fr);">{kpi}</div>
{group_err_card}
{error_table}
{ids_card}
{lg_card}"""
