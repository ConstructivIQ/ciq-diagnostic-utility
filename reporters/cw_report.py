"""
reporters/cw_report.py
───────────────────────
Thin orchestrator: assembles the full HTML dashboard from tab renderers.

Tabs (left to right):
  1. 🎫 Customer Tickets       — Jira Prod_Issue tickets
  2. 🔄 Integration Sync       — Prod 24h subscription/project impact
  3. 🌐 Environment Issues     — per-env CloudWatch breakdown
  4. 📧 Support Emails         — last 2 days of support inbox
  5. 🗄️ RDS                   — PostgreSQL health snapshot
  6. 🏗️ Infra Check           — AWS resource inventory + optional cost

Import and call:
  from reporters.cw_report import generate_cw_report
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Tab renderers — each module owns one tab's HTML
from reporters.tabs import tickets as _tickets
from reporters.tabs import sync    as _sync
from reporters.tabs import environment as _env
from reporters.tabs import emails  as _emails
from reporters.tabs import rds     as _rds
from reporters.tabs import infra   as _infra
from reporters.tabs import waste   as _waste
from reporters.tabs import project as _project

# Shared utilities
from reporters.components import _stat, ENV_ICON, e
from reporters.styles import _css

from datetime import timedelta, timezone as _tz

_IST = _tz(timedelta(hours=5, minutes=30))


# ── Public entry point ────────────────────────────────────────────────────────

def generate_cw_report(
    env_data:     dict,
    hours:        int = 1,
    output_path:  Path | None = None,
    jira_tickets: list[dict] | None = None,
    sync_data:    dict | None = None,
    emails:       list | None = None,
    rds_snap:     Any | None = None,
    infra_data:   dict | None = None,
    waste_data:   dict | None = None,
    project_id:   str | None = None,
    project_data: dict | None = None,
) -> Path:
    """Build and write the HTML report. Returns the output path.

    Args:
        env_data:     CloudWatch error data per environment (from collect_env).
        hours:        Look-back window used for env_data collection.
        output_path:  Where to write the HTML file (default: cw_report_<ts>.html).
        jira_tickets: List of ticket dicts from jira_collector.
        sync_data:    Prod 24h CloudWatch dict — used for Integration Sync tab.
                      Falls back to aggregating env_data when not provided.
        emails:       List of EmailMessage objects from email_collector.
        rds_snap:     RdsSnapshot object from rds_collector.
        infra_data:   Dict from collectors.infra_collector.collect_infra().
                      Set to None to skip the Infra tab (shows placeholder).
        waste_data:   Dict from collectors.waste_collector.collect_waste().
                      Set to None to skip the Waste Finder tab (shows placeholder).
    """
    output_path = output_path or Path(
        f"cw_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        _render(env_data, hours, jira_tickets or [], sync_data, emails or [],
                rds_snap, infra_data, waste_data,
                project_id=project_id, project_data=project_data),
        encoding="utf-8",
    )
    return output_path


# ── HTML assembly ─────────────────────────────────────────────────────────────

def _render(
    env_data:     dict,
    hours:        int,
    jira_tickets: list[dict] | None = None,
    sync_data:    dict | None = None,
    emails:       list | None = None,
    rds_snap:     Any | None = None,
    infra_data:   dict | None = None,
    waste_data:   dict | None = None,
    project_id:   str | None = None,
    project_data: dict | None = None,
) -> str:
    jira_tickets = jira_tickets or []
    emails       = emails or []
    now          = datetime.now(tz=_IST).strftime("%d %b %Y %H:%M:%S IST")
    envs         = list(env_data.keys())
    email_count  = len(emails)

    # Integration Sync Failures tab — always prod 24h.
    sync_env_data = {"prod": sync_data} if sync_data is not None else env_data
    sync_hours_label = "24h" if sync_data is not None else f"{hours}h"

    # Aggregate counters for sync KPI tiles
    all_sub:  Counter = Counter()
    all_proj: Counter = Counter()
    total_ev  = 0
    total_err = 0
    for d in sync_env_data.values():
        for k, v in d.get("sub_errors", {}).items():
            all_sub[k] += v
        for k, v in d.get("proj_errors", {}).items():
            all_proj[k] += v
        for v in d.get("totals", {}).values():
            if v >= 0:
                total_ev += v
        st = d.get("sev_totals", Counter())
        total_err += st.get("ERROR", 0) + st.get("CRITICAL", 0) + st.get("FATAL", 0)

    sync_stats = (
        _stat(f"{total_ev:,}", "Total Events (Prod 24h)") +
        _stat(f"{len(all_sub):,}", "Subscriptions Affected",
              "var(--sev-err)" if all_sub else "var(--accent)") +
        _stat(f"{len(all_proj):,}", "Projects Affected",
              "var(--sev-warn)" if all_proj else "var(--accent)") +
        _stat(f"{total_err:,}", "Errors / Critical", "var(--sev-err)")
    )

    # Environment sub-tabs
    env_tabs   = ""
    env_panels = ""
    for i, env in enumerate(envs):
        active = "active" if i == 0 else ""
        icon   = ENV_ICON.get(env, "⚪")
        env_tabs += (
            f'<button class="etab {active}" data-env="{e(env)}">'
            f'{icon} {env.upper()}</button>'
        )
        env_panels += (
            f'<div id="ep-{e(env)}" class="epanel {active}">'
            f'{_env.render(env, env_data[env])}</div>'
        )

    # Customer Tickets KPI
    open_count = len(jira_tickets)
    hi_pri     = sum(1 for t in jira_tickets if t.get("priority", "").lower() in ("highest", "critical", "high"))
    unassigned = sum(1 for t in jira_tickets if not t.get("assignee") or t.get("assignee") == "Unassigned")
    customers  = len(set(t.get("customer_name", "") for t in jira_tickets if t.get("customer_name")))

    _now_utc   = datetime.now(tz=timezone.utc)
    _ages: list[float] = []
    for _t in jira_tickets:
        _raw = _t.get("created", "")
        if _raw:
            try:
                _dt = datetime.fromisoformat(_raw.replace("Z", "+00:00"))
                _ages.append((_now_utc - _dt).total_seconds() / 86400)
            except Exception:
                pass
    avg_age_days = round(sum(_ages) / len(_ages), 1) if _ages else 0.0
    stale_count  = sum(1 for d in _ages if d > 3)

    ticket_kpi = (
        _stat(str(open_count),    "Open Prod Issues",   "var(--sev-err)" if open_count else "var(--accent)") +
        _stat(str(hi_pri),        "High+ Priority",     "var(--sev-warn)" if hi_pri else "var(--accent)") +
        _stat(str(stale_count),   "Open &gt; 3 Days",   "var(--sev-err)" if stale_count else "var(--accent)") +
        _stat(f"{avg_age_days}d", "Avg Age",            "var(--sev-warn)" if avg_age_days > 3 else "var(--accent)") +
        _stat(str(unassigned),    "Unassigned",         "var(--sev-warn)" if unassigned else "var(--accent)") +
        _stat(str(customers),     "Customers Affected", "var(--ac)")
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Support Dashboard</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:ital,wght@0,400;0,500;0,600;0,700&family=JetBrains+Mono:wght@400;500&display=swap">
<style>{_css()}</style>
</head>
<body>

<header>
  <div class="hi">
    <div class="brand">
      <span class="bi">⚡</span>
      <span class="bn">ConstructivIQ</span>
      <span class="bs">Support Dashboard</span>
    </div>
    <nav class="mtabs" role="tablist">
      <button class="mtab active" data-tab="tickets" role="tab">
        🎫 Customer Tickets <span class="tab-count">{open_count}</span>
      </button>
      <button class="mtab" data-tab="sync" role="tab">🔄 Integration Sync Failures</button>
      <button class="mtab" data-tab="environment" role="tab">🌐 Environment Issues</button>
      <button class="mtab" data-tab="emails" role="tab">
        📧 Support Emails <span class="tab-count">{email_count}</span>
      </button>
      <button class="mtab" data-tab="rds" role="tab">🗄️ RDS</button>
      <button class="mtab" data-tab="infra" role="tab">🏗️ Infra Check</button>
      <button class="mtab" data-tab="waste" role="tab">♻️ Waste Finder</button>
      {'<button class="mtab proj-tab" data-tab="project" role="tab">🔍 Project Errors <span class="tab-count tab-count-err">' + str(project_data.get("total", 0) if project_data else 0) + '</span></button>' if project_id else ''}
    </nav>
    <div class="hmeta">
      <span class="meta-window">Last {e(str(hours))}h</span>
      <span class="dot">·</span>
      <div class="ts-block">
        <span class="ts-label">Last updated</span>
        <span class="ts-value">{e(now)}</span>
      </div>
    </div>
  </div>
</header>

<main>

  <!-- Tab 1: Customer Tickets (Jira) -->
  <div id="tab-tickets" class="tpanel active">
    <div class="container">
      <div class="stats-grid" style="grid-template-columns:repeat(6,1fr)">
        {ticket_kpi}
      </div>
      <div class="card">
        <div class="card-hd">
          <h2>Production Issues</h2>
          <span class="chip">{open_count} issues · label: Prod_Issue</span>
        </div>
        {_tickets.render(jira_tickets)}
      </div>
    </div>
  </div>

  <!-- Tab 2: Integration Sync Failures (always Prod 24h) -->
  <div id="tab-sync" class="tpanel">
    <div class="container">
      <div class="sync-header">
        <span class="sync-badge">🔴 PROD</span>
        <span class="sync-badge">⏱ Last {e(sync_hours_label)}</span>
        <span class="sync-note">
          Subscription &amp; project impact from integration sync errors ·
          env-independent, always prod
        </span>
      </div>
      <div class="stats-grid">{sync_stats}</div>
      {_sync.category_panel(sync_env_data)}
      <div class="card">
        <div class="card-hd">
          <h2>Most Impacted Subscriptions</h2>
          <span class="chip">{len(all_sub):,} found</span>
        </div>
        {_sync.sub_table(sync_env_data, show_env_col=False, show_cust_col=False)}
      </div>
      <div class="card">
        <div class="card-hd">
          <h2>Most Impacted Projects</h2>
          <span class="chip">{len(all_proj):,} found</span>
        </div>
        {_sync.proj_table(sync_env_data)}
      </div>
    </div>
  </div>

  <!-- Tab 3: Environment Issues (CloudWatch per-env) -->
  <div id="tab-environment" class="tpanel">
    <div class="container">
      <div class="etab-strip">{env_tabs}</div>
      {env_panels}
    </div>
  </div>

  <!-- Tab 4: Support Emails (last 2 days) -->
  <div id="tab-emails" class="tpanel">
    <div class="container">
      <div class="card">
        <div class="card-hd">
          <h2>Support Emails</h2>
          <span class="chip">{email_count} emails · last 2 days</span>
        </div>
        {_emails.render(emails)}
      </div>
    </div>
  </div>

  <!-- Tab 5: RDS / PostgreSQL health -->
  <div id="tab-rds" class="tpanel">
    <div class="container">
      {_rds.render(rds_snap)}
    </div>
  </div>

  <!-- Tab 6: Infra Check -->
  <div id="tab-infra" class="tpanel">
    <div class="container">
      {_infra.render(infra_data)}
    </div>
  </div>

  <!-- Tab 7: Waste Finder (unused/idle resources) -->
  <div id="tab-waste" class="tpanel">
    <div class="container">
      {_waste.render(waste_data)}
    </div>
  </div>

  <!-- Tab 8: Project Errors (only rendered when --project-id supplied) -->
  {f'''<div id="tab-project" class="tpanel">
    <div class="container">
      {_project.render(project_data)}
    </div>
  </div>''' if project_id else ''}

</main>

<style>
.tab-count-err {{ background: var(--sev-err) !important; }}
.proj-tab {{ border-bottom: 2px solid var(--sev-err) !important; }}
</style>
<div class="footer">ConstructivIQ Diagnostic Utility &middot; {e(now)}</div>

<script>
// Main tab switcher
document.querySelectorAll('.mtab').forEach(b => b.addEventListener('click', () => {{
  const t = b.dataset.tab;
  document.querySelectorAll('.mtab').forEach(x => x.classList.remove('active'));
  document.querySelectorAll('.tpanel').forEach(x => x.classList.remove('active'));
  b.classList.add('active');
  const panel = document.getElementById('tab-' + t);
  if (panel) panel.classList.add('active');
}}));

// Environment sub-tabs
document.querySelectorAll('.etab').forEach(b => b.addEventListener('click', () => {{
  const env = b.dataset.env;
  document.querySelectorAll('.etab').forEach(x => x.classList.remove('active'));
  document.querySelectorAll('.epanel').forEach(x => x.classList.remove('active'));
  b.classList.add('active');
  const p = document.getElementById('ep-' + env);
  if (p) p.classList.add('active');
}}));

// Expand/collapse cells on click
document.addEventListener('click', ev => {{
  const cell = ev.target.closest('.expand-cell, .json-cell');
  if (cell) cell.classList.toggle('expanded');
}});

// Auto-activate Project Errors tab if present
(function() {{
  const projBtn = document.querySelector('.proj-tab');
  if (projBtn) {{
    projBtn.click();
  }}
}})();
</script>
</body>
</html>"""
