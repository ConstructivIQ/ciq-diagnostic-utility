"""
reporters/tabs/waste.py
────────────────────────
HTML renderer for the ♻️ Waste Finder tab.

Receives the dict returned by collectors.waste_collector.collect_waste()
and produces a self-contained HTML fragment.
"""
from __future__ import annotations

from reporters.components import e


# ── Severity badge ─────────────────────────────────────────────────────────────

_SEV_COLORS = {
    "stopped":  ("var(--sev-crit)",   "#fff"),
    "idle":     ("var(--sev-warn)",   "#000"),
    "empty":    ("var(--mt)",         "#fff"),
    "no-data":  ("var(--sev-exc)",    "#fff"),
    "error":    ("var(--sev-fatal)",  "#fff"),
}

_COST_COLORS = {
    "high":    ("var(--sev-crit)",  "#fff"),
    "medium":  ("var(--sev-warn)",  "#000"),
    "low":     ("var(--sev-ok)",    "#000"),
    "free":    ("var(--mt)",        "#fff"),
    "unknown": ("var(--bd)",        "var(--tx)"),
}

_TYPE_ICONS = {
    "RDS":         "🗄️",
    "EC2":         "🖥️",
    "Lambda":      "λ",
    "ELB":         "⚖️",
    "ElastiCache": "⚡",
    "ECS":         "📦",
    "S3":          "🪣",
}


def _sev_badge(sev: str) -> str:
    bg, fg = _SEV_COLORS.get(sev, ("var(--bd)", "var(--tx)"))
    label  = sev.upper()
    return (
        f'<span class="sev-badge" '
        f'style="background:{bg};color:{fg}">{e(label)}</span>'
    )


def _cost_badge(cost: str) -> str:
    bg, fg = _COST_COLORS.get(cost, ("var(--bd)", "var(--tx)"))
    label  = cost.upper() + " COST"
    return (
        f'<span class="chip" '
        f'style="background:{bg};color:{fg};border-color:{bg}">{e(label)}</span>'
    )


def _age_str(age: float | None) -> str:
    if age is None:
        return '<span class="text-m sm">—</span>'
    if age < 30:
        color = "var(--sev-ok)"
    elif age < 180:
        color = "var(--sev-warn)"
    else:
        color = "var(--sev-crit)"
    return f'<span style="color:{color};font-weight:600">{age:.0f}d</span>'


def _metric_cell(metric: str | None, value: float | None) -> str:
    if metric is None:
        return '<td class="text-m sm">—</td>'
    val_str = "—" if value is None else f"{value:,.3f}".rstrip("0").rstrip(".")
    return (
        f'<td><span class="mono" style="font-size:11px;color:var(--mt)">'
        f'{e(metric)}</span><br>'
        f'<span style="font-weight:600">{e(val_str)}</span></td>'
    )


# ── Main render ────────────────────────────────────────────────────────────────

def render(waste: dict | None) -> str:
    if not waste:
        return _placeholder()

    findings     = waste.get("findings", [])
    total        = waste.get("total", len(findings))
    days_checked = waste.get("days_checked", 14)
    env          = waste.get("env", "")
    account      = waste.get("account", "")
    region       = waste.get("region", "")

    if not findings:
        return _no_issues(days_checked)

    # Counts by severity
    counts: dict[str, int] = {}
    for f in findings:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1

    stopped_n   = counts.get("stopped", 0)
    idle_n      = counts.get("idle", 0)
    empty_n     = counts.get("empty", 0) + counts.get("no-data", 0)
    high_cost_n = sum(1 for f in findings if f.get("cost_hint") == "high")

    stat_style  = "grid-template-columns:repeat(4,1fr)"

    # Stat cards
    def _stat_card(val: str, label: str, color: str = "var(--ac)") -> str:
        return (
            f'<div class="stat-card" style="border-top-color:{color}">'
            f'<div class="stat-val" style="color:{color}">{val}</div>'
            f'<div class="stat-lbl">{label}</div></div>'
        )

    stats_html = (
        _stat_card(str(total),        "Total Findings",      "var(--sev-warn)")
        + _stat_card(str(stopped_n),  "Stopped / Inactive",  "var(--sev-crit)" if stopped_n else "var(--ac)")
        + _stat_card(str(idle_n),     "Idle (no traffic)",   "var(--sev-warn)" if idle_n else "var(--ac)")
        + _stat_card(str(high_cost_n),"High-Cost Instances",  "var(--sev-crit)" if high_cost_n else "var(--ac)")
    )

    # Breakdown chips by resource type
    type_counts: dict[str, int] = {}
    for f in findings:
        t = f["resource_type"]
        type_counts[t] = type_counts.get(t, 0) + 1

    type_chips = " ".join(
        f'<span class="chip">{_TYPE_ICONS.get(t,"•")} {e(t)} ({n})</span>'
        for t, n in sorted(type_counts.items(), key=lambda x: -x[1])
    )

    # Table rows
    rows = []
    for f in findings:
        rtype  = f.get("resource_type", "")
        icon   = _TYPE_ICONS.get(rtype, "•")
        sev    = f.get("severity", "unknown")
        cost   = f.get("cost_hint", "unknown")

        row_class = {
            "stopped": "row-crit",
            "idle":    "row-warn",
            "no-data": "row-error",
        }.get(sev, "")

        rows.append(
            f'<tr class="{row_class}">'
            f'<td><span class="mono" style="font-size:12px">{icon} {e(rtype)}</span></td>'
            f'<td class="mono" style="font-size:12px;max-width:200px;word-break:break-all">'
            f'{e(f.get("resource_id",""))}</td>'
            f'<td>{_sev_badge(sev)}</td>'
            f'<td class="msg-cell">{e(f.get("reason",""))}</td>'
            + _metric_cell(f.get("metric"), f.get("metric_value"))
            + f'<td class="sm" style="color:var(--mt)">{e(f.get("class",""))}</td>'
            + f'<td style="text-align:right">{_age_str(f.get("age_days"))}</td>'
            + f'<td>{_cost_badge(cost)}</td>'
            + "</tr>"
        )

    table_html = f"""
<div class="tw">
  <table class="dt">
    <thead>
      <tr>
        <th>Type</th>
        <th>Resource ID</th>
        <th>Status</th>
        <th>Reason</th>
        <th>Metric / Value</th>
        <th>Class / Runtime</th>
        <th style="text-align:right">Age</th>
        <th>Cost Impact</th>
      </tr>
    </thead>
    <tbody>{"".join(rows)}</tbody>
  </table>
</div>"""

    meta_note = (
        f'Checked last <strong>{days_checked}</strong> days of CloudWatch metrics · '
        f'<code style="font-size:11px">{e(account)}</code> / '
        f'<code style="font-size:11px">{e(region)}</code> · '
        f'env: <code style="font-size:11px">{e(env)}</code>'
    )

    return f"""
<div class="rds-info" style="padding:0 0 0 0;margin-bottom:8px">
  <span class="sync-badge">♻️ WASTE FINDER</span>
  <span class="sync-note">{meta_note}</span>
</div>

<div class="stats-grid" style="{stat_style}">
  {stats_html}
</div>

<div style="margin-bottom:14px;display:flex;gap:8px;flex-wrap:wrap">
  {type_chips}
</div>

<div class="card">
  <div class="card-hd">
    <h2>Unused / Idle Resources</h2>
    <span class="chip">{total} findings · {days_checked}d look-back</span>
  </div>
  {table_html}
</div>

<div class="card" style="margin-top:14px">
  <div class="card-hd"><h2>💡 Remediation Guide</h2></div>
  <div style="padding:16px 20px;font-size:13px;line-height:1.8;color:var(--tx)">
    <p style="margin-bottom:10px">
      <strong>Stopped RDS / EC2 instances</strong> — still incur EBS storage charges.
      Snapshot &amp; terminate if not needed within 30 days.
    </p>
    <p style="margin-bottom:10px">
      <strong>Idle RDS instances</strong> (zero connections) — verify with the owning team.
      If confirmed unused, create a final snapshot then delete.
    </p>
    <p style="margin-bottom:10px">
      <strong>Idle ElastiCache</strong> — check if any application still references the endpoint.
      If not, delete the cluster; Redis data can be snapshotted first.
    </p>
    <p style="margin-bottom:10px">
      <strong>Idle ELB load balancers</strong> — check target groups for registered targets.
      An ALB with no healthy targets is safe to remove (~$16–25/month saved per LB).
    </p>
    <p style="margin-bottom:10px">
      <strong>Zero-invocation Lambda functions</strong> — low urgency (no cost at idle)
      but add code-maintenance overhead. Archive or delete after confirming with owners.
    </p>
    <p>
      <strong>Empty S3 buckets</strong> — no storage cost, but can indicate orphaned
      infrastructure. Review bucket policies and delete if truly orphaned.
    </p>
  </div>
</div>
"""


def _placeholder() -> str:
    return """
<div class="empty-state">
  <div class="ei">♻️</div>
  <div>Waste Finder not collected this run.</div>
  <div class="hint">Re-run with <code>--waste</code> to check for unused AWS resources.</div>
</div>"""


def _no_issues(days: int) -> str:
    return f"""
<div class="empty-state">
  <div class="ei">✅</div>
  <div style="color:var(--sev-ok);font-weight:700">No unused resources found!</div>
  <div class="hint">Checked {days} days of CloudWatch metrics — everything looks active.</div>
</div>"""
