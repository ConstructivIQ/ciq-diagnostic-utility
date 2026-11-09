"""
reporters/tabs/project.py
──────────────────────────
Project Errors tab: service-wise CloudWatch error + warn lines for a project_id.

Renders:
  • KPI tiles          — total events, services with hits, latest timestamp, environment
  • Service Overview   — one row per log group: service name, group, count, last event
  • Per-service cards  — expandable error table for each service that has hits
  • Import Log IDs     — all unique import_log_ids affected
  • Log Groups card    — all groups queried
"""
from __future__ import annotations
import re
from collections import defaultdict
from reporters.components import _stat, e


# ── Friendly service name from log group path ─────────────────────────────────
def _service_name(log_group: str) -> str:
    """Derive a short human-readable service name from a log group path."""
    name = log_group
    # Strip common prefixes
    for prefix in ("/ecs/", "/aws/lambda/", "/aws/ecs/"):
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    # Strip env prefix like ciq-prod-useast1-, ciq-dev-useast2-, etc.
    name = re.sub(r"^ciq-[\w]+-useast\d-", "", name)
    name = re.sub(r"^ciq-[\w]+-", "", name)
    # Strip generic task/lambda/job prefix
    name = re.sub(r"^(task|lambda|job)-", "", name)
    # Capitalise words
    name = name.replace("-", " ").replace("_", " ").title()
    # Annotate type
    if "/ecs/" in log_group:
        name += " (ECS)"
    elif "/aws/lambda/" in log_group:
        name += " (λ)"
    return name


def _svc_color(hits: int) -> str:
    if hits == 0:
        return "var(--fg3)"
    return "var(--sev-err)"


def render(project_data: dict) -> str:
    if not project_data:
        return '<div class="card"><p style="color:var(--fg3)">No project data available.</p></div>'

    project_id      = project_data.get("project_id", "")
    env             = project_data.get("env", "")
    hours           = project_data.get("hours", 24)
    region          = project_data.get("region", "")
    errors          = project_data.get("errors", [])
    total           = project_data.get("total", 0)
    group_errors    = project_data.get("group_errors", {})
    message_filter  = project_data.get("message_filter")

    # Support both old (ECS+Lambda) and new (key-services / all-groups) modes
    key_services_mode = project_data.get("key_services_mode") or project_data.get("all_groups_mode")
    log_groups_scanned = project_data.get("log_groups_scanned", [])
    group_hits_map    = project_data.get("group_hits", {})   # group → count

    # Legacy ECS+Lambda mode — build scanned list from log_groups dict
    if not key_services_mode:
        lg = project_data.get("log_groups", {})
        for g in [lg.get("ecs"), lg.get("lambda")]:
            if g:
                log_groups_scanned.append(g)
        # Build hit map from errors
        for r in errors:
            g = r.get("log_group", "")
            group_hits_map[g] = group_hits_map.get(g, 0) + 1

    # Group errors by log_group
    errors_by_group: dict[str, list] = defaultdict(list)
    for r in errors:
        errors_by_group[r.get("log_group", "unknown")].append(r)

    # Unique import_log_ids
    unique_ids = list(dict.fromkeys(
        r["import_log_id"] for r in errors if r.get("import_log_id")
    ))

    # Latest timestamp
    latest_ts = errors[0].get("ts", "—") if errors else "—"

    # Services with hits
    services_with_hits = sum(1 for v in group_hits_map.values() if v > 0)

    # ── KPI row ───────────────────────────────────────────────────────────────
    kpi = (
        _stat(str(total),               "Total Events",          "var(--sev-err)" if total else "var(--accent)") +
        _stat(str(services_with_hits),  "Services With Errors",  "var(--sev-err)" if services_with_hits else "var(--fg3)") +
        _stat(latest_ts,                "Latest Event",          "var(--sev-err)" if errors else "var(--accent)") +
        _stat(env.upper(),              "Environment",           "var(--ac)")
    )

    # ── Header badges ─────────────────────────────────────────────────────────
    filter_badge = (
        f'<span class="sync-badge" style="background:rgba(99,102,241,.15);color:#818cf8;">'
        f'🔍 filter: {e(message_filter)}</span>'
        if message_filter else ""
    )
    mode_badge = ""
    if key_services_mode:
        mode_badge = '<span class="sync-badge" style="background:rgba(34,197,94,.12);color:#4ade80;">⚡ key services</span>'

    header = f"""
<div class="sync-header">
  <span class="sync-badge">{'🔴 PROD' if env == 'prod' else '🟡 ' + env.upper()}</span>
  <span class="sync-badge">⏱ Last {hours}h</span>
  <span class="sync-badge" style="font-family:monospace;font-size:11px;">{e(project_id)}</span>
  {filter_badge}
  {mode_badge}
  <span class="sync-note">Region: {e(region)}</span>
</div>"""

    # ── Group errors card ─────────────────────────────────────────────────────
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

    # ── Service Overview table ─────────────────────────────────────────────────
    svc_rows = ""
    for group in sorted(log_groups_scanned):
        hits   = group_hits_map.get(group, 0)
        sname  = _service_name(group)
        last_e = ""
        if hits:
            grp_errs = errors_by_group.get(group, [])
            last_e   = grp_errs[0].get("ts", "") if grp_errs else ""
        badge_bg  = "rgba(239,68,68,.15)" if hits else "rgba(255,255,255,.06)"
        badge_col = "var(--sev-err)" if hits else "var(--fg3)"
        svc_rows += f"""
<tr>
  <td style="font-size:12px;font-weight:600;">{e(sname)}</td>
  <td style="font-family:monospace;font-size:10px;color:var(--fg3);">{e(group)}</td>
  <td style="text-align:center;">
    <span style="background:{badge_bg};color:{badge_col};border-radius:12px;
                 padding:2px 10px;font-size:11px;font-weight:700;">{hits}</span>
  </td>
  <td style="font-size:11px;color:var(--fg3);">{e(last_e)}</td>
</tr>"""

    overview_card = f"""
<div class="card">
  <div class="card-hd">
    <h2>Service Overview</h2>
    <span class="chip">{len(log_groups_scanned)} groups queried · {services_with_hits} with errors</span>
  </div>
  <div style="overflow-x:auto;">
    <table class="err-table">
      <thead><tr>
        <th>Service</th>
        <th>Log Group</th>
        <th style="text-align:center;">Errors</th>
        <th>Last Error</th>
      </tr></thead>
      <tbody>{svc_rows}</tbody>
    </table>
  </div>
</div>"""

    # ── Per-service error cards ───────────────────────────────────────────────
    def _error_table_rows(rows: list) -> str:
        html = ""
        for row in rows:
            imp_id   = row.get("import_log_id", "")
            imp_cell = (
                f'<code class="expand-cell" style="cursor:pointer;">{e(imp_id[:18])}…</code>'
                if imp_id else '<span style="color:var(--fg3)">—</span>'
            )
            err_name = row.get("error_name", "")
            msg      = row.get("message", row.get("raw", "")[:180])
            level    = row.get("level", "ERROR")
            lv_color = "var(--sev-err)" if level in ("ERROR", "CRITICAL", "FATAL") else "var(--sev-warn)"
            html += f"""
<tr>
  <td style="font-size:11px;white-space:nowrap;color:var(--fg3);">{e(row.get('ts', ''))}</td>
  <td><span style="color:{lv_color};font-size:10px;font-weight:600;">{e(level)}</span></td>
  <td>{imp_cell}</td>
  <td style="font-size:11px;color:var(--sev-err);">{e(err_name)}</td>
  <td class="expand-cell" style="font-size:11px;max-width:380px;cursor:pointer;">{e(msg)}</td>
</tr>"""
        return html

    service_cards = ""
    # Only render cards for groups that have errors, newest-first by hit count
    groups_with_errors = sorted(
        [(g, errors_by_group[g]) for g in log_groups_scanned if group_hits_map.get(g, 0) > 0],
        key=lambda x: -len(x[1])
    )

    for idx, (group, grp_errors) in enumerate(groups_with_errors):
        sname     = _service_name(group)
        card_id   = f"svc-{idx}"
        tbl_rows  = _error_table_rows(grp_errors)
        service_cards += f"""
<div class="card" style="border-left:3px solid var(--sev-err);">
  <div class="card-hd" style="cursor:pointer;" onclick="toggleSvc('{card_id}')">
    <h2>{e(sname)}</h2>
    <span class="chip" style="color:var(--sev-err);">{len(grp_errors)} event(s)</span>
    <code style="font-size:10px;color:var(--fg3);margin-left:8px;">{e(group)}</code>
    <span id="{card_id}-arrow" style="margin-left:auto;font-size:12px;transition:transform .2s;">▼</span>
  </div>
  <div id="{card_id}" style="overflow-x:auto;">
    <table class="err-table">
      <thead><tr>
        <th>Timestamp (IST)</th><th>Level</th>
        <th>Import Log ID</th><th>Error Type</th><th>Message</th>
      </tr></thead>
      <tbody>{tbl_rows}</tbody>
    </table>
  </div>
</div>"""

    if not service_cards:
        service_cards = f"""
<div class="card">
  <div class="card-hd"><h2>Log Lines</h2></div>
  <p style="color:var(--fg3);padding:20px 0;text-align:center;">
    No errors or warnings found for this project in the last {hours}h.
  </p>
</div>"""

    # ── Import Log IDs pill row ───────────────────────────────────────────────
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

    # ── Toggle script ─────────────────────────────────────────────────────────
    toggle_script = """
<script>
function toggleSvc(id) {
  var el = document.getElementById(id);
  var arrow = document.getElementById(id + '-arrow');
  if (!el) return;
  var hidden = el.style.display === 'none';
  el.style.display = hidden ? '' : 'none';
  if (arrow) arrow.style.transform = hidden ? '' : 'rotate(-90deg)';
}
</script>"""

    return f"""
{header}
<div class="stats-grid" style="grid-template-columns:repeat(4,1fr);">{kpi}</div>
{group_err_card}
{overview_card}
{service_cards}
{ids_card}
{toggle_script}"""
