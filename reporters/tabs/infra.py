"""
reporters/tabs/infra.py
────────────────────────
Infra Check tab renderer.

Displays AWS infrastructure resources discovered by collectors/infra_collector.py:
  ECS, EC2, RDS, ELB, ElastiCache, Lambda, S3 — all free to query.
  Optional Cost Explorer breakdown (behind --infra-cost flag, $0.01/call).

Each resource row shows:
  - Resource name / identifier
  - Service-specific fields (status, engine, class, etc.)
  - Age badge (green < 30d, amber < 180d, red >= 180d)
"""
from __future__ import annotations

from reporters.components import _stat, e


def _age_badge(age: "float | None") -> str:
    """Colour-coded age pill: green/amber/red based on resource age in days."""
    if age is None:
        return '<span class="age-badge age-unk">?</span>'
    if age < 30:
        color = "var(--sev-ok)"
    elif age < 180:
        color = "var(--sev-warn)"
    else:
        color = "var(--sev-err)"
    years  = int(age // 365)
    months = int((age % 365) // 30)
    days_r = int(age % 30)
    if years:
        label = f"{years}y {months}m"
    elif months:
        label = f"{months}m {days_r}d"
    else:
        label = f"{int(age)}d"
    return f'<span class="age-badge" style="color:{color};border-color:{color}55;background:{color}15">{label}</span>'


def render(infra: "dict | None") -> str:
    """Render the full Infra Check tab content."""
    if infra is None:
        return (
            '<div class="empty-state"><div class="ei">🏗️</div>'
            '<p>Infrastructure data not collected.</p>'
            '<p class="hint">Re-run with <code>--infra</code> to include AWS resource discovery (free).</p>'
            '<p class="hint">Add <code>--infra-cost</code> to also include cost data '
            '(<strong>⚠️ $0.01 per run</strong> — AWS Cost Explorer API charge).</p>'
            '</div>'
        )

    env       = infra.get("env", "")
    account   = infra.get("account", "")
    region    = infra.get("region", "")
    collected = (infra.get("collected_at") or "")[:16].replace("T", " ") + " UTC"
    services  = infra.get("services", {})
    cost      = infra.get("cost")

    # ── KPI tiles ─────────────────────────────────────────────────────────────
    total_resources = sum(
        len([r for r in lst if not r.get("_error")])
        for lst in services.values()
    )
    ecs_running = sum(r.get("running", 0) for r in services.get("ecs", []) if not r.get("_error"))
    rds_count   = len([r for r in services.get("rds", []) if not r.get("_error")])
    cost_days   = (cost or {}).get("period", {}).get("days", 7) if cost else 7
    cost_str    = f"${cost['total_usd']:,.2f}" if cost and "total_usd" in cost else "N/A"
    cost_color  = "var(--sev-warn)" if cost and cost.get("total_usd", 0) > 100 else "var(--accent)"

    kpi = (
        _stat(str(total_resources), "Total Resources")
        + _stat(str(ecs_running), "ECS Tasks Running",  "var(--sev-ok)" if ecs_running else "var(--mt)")
        + _stat(str(rds_count),   "RDS Instances")
        + _stat(cost_str,         f"Cost ({cost_days}d)", cost_color)
    )

    header_html = (
        f'<div class="sync-header" style="margin-bottom:16px">'
        f'<span class="sync-badge">🔴 {e(env.upper())}</span>'
        f'<span class="sync-badge">☁️ {e(account)}</span>'
        f'<span class="sync-badge">📍 {e(region)}</span>'
        f'<span class="sync-note">Collected {e(collected)} · describe_* / list_* calls are <strong>free</strong></span>'
        f'</div>'
    )

    # ── Cost panel ────────────────────────────────────────────────────────────
    cost_html = _render_cost(cost)

    # ── Per-service resource tables ───────────────────────────────────────────
    svc_cards = (
        _render_ecs(services.get("ecs", []))
        + _render_rds(services.get("rds", []))
        + _render_elb(services.get("elb", []))
        + _render_elasticache(services.get("elasticache", []))
        + _render_lambda(services.get("lambda", []))
        + _render_s3(services.get("s3", []))
    )

    if not svc_cards:
        svc_cards = (
            '<div class="empty-state"><div class="ei">🔍</div>'
            f'<p>No resources matched env <strong>{e(env)}</strong> in account <strong>{e(account)}</strong>.</p>'
            '<p class="hint">Resources are filtered by env name in their identifier/tags. '
            'Verify ENV_CONFIG account/region mapping.</p>'
            '</div>'
        )

    return f"""
<div class="stats-grid">{kpi}</div>
{header_html}
{cost_html}
{svc_cards}
"""


# ── Cost panel ────────────────────────────────────────────────────────────────

def _render_cost(cost: "dict | None") -> str:
    if cost is None:
        return (
            '<div class="card" style="margin-bottom:16px"><div class="card-hd"><h2>💰 Cost</h2>'
            '<span class="chip">Not collected</span></div>'
            '<div class="empty-state" style="padding:20px"><div class="ei" style="font-size:20px">💡</div>'
            '<p>Re-run with <code>--infra-cost</code> to include cost breakdown.</p>'
            '<p class="hint">⚠️ AWS Cost Explorer charges <strong>$0.01 per API call</strong>.</p>'
            '</div></div>'
        )
    if "_error" in cost:
        return (
            f'<div class="card" style="margin-bottom:16px"><div class="card-hd"><h2>💰 Cost</h2></div>'
            f'<div class="empty-state" style="padding:20px"><div class="ei" style="font-size:20px">❌</div>'
            f'<p>Cost query failed: {e(cost["_error"])}</p></div></div>'
        )
    cost_rows = ""
    for row in cost.get("by_service", [])[:20]:
        cost_rows += (
            f'<tr>'
            f'<td class="sm">{e(row["service"])}</td>'
            f'<td class="num">${row["amount"]:,.4f}</td>'
            f'<td class="sm text-m">{e(row.get("unit","USD"))}</td>'
            f'</tr>'
        )
    weekly = cost.get("weekly_usd")
    return (
        f'<div class="card" style="margin-bottom:16px"><div class="card-hd">'
        f'<h2>💰 Cost Breakdown</h2>'
        f'<span class="chip" style="color:#d29922;border-color:#d29922aa">⚠️ {e(cost.get("warning",""))}</span>'
        f'<span class="chip">Period: {e(cost["period"]["start"])} → {e(cost["period"]["end"])}</span>'
        f'<span class="chip" style="color:var(--sev-warn);font-weight:700">Total: ${cost["total_usd"]:,.2f}'
        + (f' · Weekly est.: ${weekly:,.2f}' if weekly is not None else '')
        + f'</span></div>'
        f'<div class="tw"><table class="dt"><thead><tr>'
        f'<th>AWS Service</th><th style="text-align:right">Amount</th><th>Unit</th>'
        f'</tr></thead><tbody>{cost_rows}</tbody></table></div></div>'
    )


# ── Per-service renderers ─────────────────────────────────────────────────────

def _render_ecs(items: list) -> str:
    clean = [r for r in items if not r.get("_error")]
    if not clean:
        return ""
    rows = ""
    for r in sorted(clean, key=lambda x: x.get("age_days") or 0, reverse=True):
        sc = "var(--sev-ok)"   if r.get("status","").upper() == "ACTIVE" else "var(--sev-warn)"
        rc = "var(--sev-err)"  if r.get("running",0) < r.get("desired",0) else "var(--sev-ok)"
        rows += (
            f'<tr><td class="sm">{e(r.get("cluster",""))}</td>'
            f'<td class="sm">{e(r.get("name",""))}</td>'
            f'<td><span style="color:{sc};font-size:11px;font-weight:600">{e(r.get("status",""))}</span></td>'
            f'<td class="num" style="color:{rc}">{r.get("running",0)}/{r.get("desired",0)}</td>'
            f'<td class="sm text-m">{e(r.get("task_def","")[:40])}</td>'
            f'<td style="text-align:center">{_age_badge(r.get("age_days"))}</td></tr>'
        )
    return (
        f'<div class="card" style="margin-bottom:16px"><div class="card-hd">'
        f'<h2>🚀 ECS Services</h2><span class="chip">{len(clean)} services</span></div>'
        f'<div class="tw"><table class="dt"><thead><tr>'
        f'<th>Cluster</th><th>Service</th><th>Status</th>'
        f'<th style="text-align:right">Running/Desired</th><th>Task Def</th><th>Age</th>'
        f'</tr></thead><tbody>{rows}</tbody></table></div></div>'
    )


def _render_rds(items: list) -> str:
    clean = [r for r in items if not r.get("_error")]
    if not clean:
        return ""
    rows = ""
    for r in sorted(clean, key=lambda x: x.get("age_days") or 0, reverse=True):
        sc = "var(--sev-ok)" if r.get("status","") == "available" else "var(--sev-warn)"
        rows += (
            f'<tr><td class="sm mono">{e(r.get("id",""))}</td>'
            f'<td class="sm">{e(r.get("engine",""))}</td>'
            f'<td><span style="color:{sc};font-size:11px;font-weight:600">{e(r.get("status",""))}</span></td>'
            f'<td class="sm text-m">{e(r.get("class",""))}</td>'
            f'<td class="sm text-m">{e(r.get("az",""))}</td>'
            f'<td class="num">{r.get("storage_gb",0)} GB</td>'
            f'<td class="sm text-m">{"Multi-AZ" if r.get("multi_az") else "Single-AZ"}</td>'
            f'<td style="text-align:center">{_age_badge(r.get("age_days"))}</td></tr>'
        )
    return (
        f'<div class="card" style="margin-bottom:16px"><div class="card-hd">'
        f'<h2>🗄️ RDS Instances</h2><span class="chip">{len(clean)} instances</span></div>'
        f'<div class="tw"><table class="dt"><thead><tr>'
        f'<th>Identifier</th><th>Engine</th><th>Status</th><th>Class</th>'
        f'<th>AZ</th><th style="text-align:right">Storage</th><th>HA</th><th>Age</th>'
        f'</tr></thead><tbody>{rows}</tbody></table></div></div>'
    )


def _render_elb(items: list) -> str:
    clean = [r for r in items if not r.get("_error")]
    if not clean:
        return ""
    rows = ""
    for r in sorted(clean, key=lambda x: x.get("age_days") or 0, reverse=True):
        sc = "var(--sev-ok)" if r.get("state","") == "active" else "var(--sev-warn)"
        rows += (
            f'<tr><td class="sm">{e(r.get("name",""))}</td>'
            f'<td class="sm text-m">{e(r.get("type","").upper())}</td>'
            f'<td class="sm text-m">{e(r.get("scheme",""))}</td>'
            f'<td><span style="color:{sc};font-size:11px;font-weight:600">{e(r.get("state",""))}</span></td>'
            f'<td style="text-align:center">{_age_badge(r.get("age_days"))}</td></tr>'
        )
    return (
        f'<div class="card" style="margin-bottom:16px"><div class="card-hd">'
        f'<h2>⚖️ Load Balancers</h2><span class="chip">{len(clean)} LBs</span></div>'
        f'<div class="tw"><table class="dt"><thead><tr>'
        f'<th>Name</th><th>Type</th><th>Scheme</th><th>State</th><th>Age</th>'
        f'</tr></thead><tbody>{rows}</tbody></table></div></div>'
    )


def _render_elasticache(items: list) -> str:
    clean = [r for r in items if not r.get("_error")]
    if not clean:
        return ""
    rows = ""
    for r in sorted(clean, key=lambda x: x.get("age_days") or 0, reverse=True):
        sc = "var(--sev-ok)" if r.get("status","") == "available" else "var(--sev-warn)"
        rows += (
            f'<tr><td class="sm mono">{e(r.get("id",""))}</td>'
            f'<td class="sm">{e(r.get("engine",""))}</td>'
            f'<td><span style="color:{sc};font-size:11px;font-weight:600">{e(r.get("status",""))}</span></td>'
            f'<td class="sm text-m">{e(r.get("node_type",""))}</td>'
            f'<td class="num">{r.get("nodes",0)}</td>'
            f'<td style="text-align:center">{_age_badge(r.get("age_days"))}</td></tr>'
        )
    return (
        f'<div class="card" style="margin-bottom:16px"><div class="card-hd">'
        f'<h2>⚡ ElastiCache</h2><span class="chip">{len(clean)} clusters</span></div>'
        f'<div class="tw"><table class="dt"><thead><tr>'
        f'<th>Cluster ID</th><th>Engine</th><th>Status</th><th>Node Type</th>'
        f'<th style="text-align:right">Nodes</th><th>Age</th>'
        f'</tr></thead><tbody>{rows}</tbody></table></div></div>'
    )


def _render_lambda(items: list) -> str:
    clean = [r for r in items if not r.get("_error")]
    if not clean:
        return ""
    rows = ""
    for r in sorted(clean, key=lambda x: x.get("name","")):
        rows += (
            f'<tr><td class="sm">{e(r.get("name",""))}</td>'
            f'<td class="sm text-m">{e(r.get("runtime",""))}</td>'
            f'<td class="num">{r.get("memory_mb",0)} MB</td>'
            f'<td class="num">{r.get("timeout_s",0)}s</td>'
            f'<td class="ts">{e((r.get("last_modified") or "")[:10])}</td>'
            f'<td style="text-align:center">{_age_badge(r.get("age_days"))}</td></tr>'
        )
    return (
        f'<div class="card" style="margin-bottom:16px"><div class="card-hd">'
        f'<h2>λ Lambda Functions</h2><span class="chip">{len(clean)} functions</span></div>'
        f'<div class="tw"><table class="dt"><thead><tr>'
        f'<th>Name</th><th>Runtime</th><th style="text-align:right">Memory</th>'
        f'<th style="text-align:right">Timeout</th><th>Last Modified</th><th>Age</th>'
        f'</tr></thead><tbody>{rows}</tbody></table></div></div>'
    )


def _render_s3(items: list) -> str:
    clean = [r for r in items if not r.get("_error")]
    if not clean:
        return ""
    rows = ""
    for r in sorted(clean, key=lambda x: x.get("age_days") or 0, reverse=True):
        rows += (
            f'<tr><td class="sm mono">{e(r.get("name",""))}</td>'
            f'<td style="text-align:center">{_age_badge(r.get("age_days"))}</td></tr>'
        )
    return (
        f'<div class="card" style="margin-bottom:16px"><div class="card-hd">'
        f'<h2>🪣 S3 Buckets</h2><span class="chip">{len(clean)} buckets</span></div>'
        f'<div class="tw"><table class="dt"><thead><tr>'
        f'<th>Bucket Name</th><th>Age</th>'
        f'</tr></thead><tbody>{rows}</tbody></table></div></div>'
    )
