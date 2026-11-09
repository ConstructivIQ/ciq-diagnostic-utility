"""
reporters/tabs/rds.py
──────────────────────
RDS / PostgreSQL health tab renderer.
"""
from __future__ import annotations

from reporters.components import _stat, _bar, e


def render(snap: "Any | None") -> str:
    from typing import Any  # local import avoids circular at module level

    if snap is None:
        return (
            '<div class="empty-state"><div class="ei">🗄️</div>'
            '<p>RDS data not collected.</p>'
            '<p class="hint">Add PG_HOST, PG_DATABASE, PG_USER, PG_PASSWORD to .env and re-run.</p>'
            '</div>'
        )
    if not snap.connected:
        err  = getattr(snap, "error", "unknown error")
        host = getattr(snap, "host", "")
        return (
            '<div class="empty-state"><div class="ei">🔴</div>'
            f'<p>Could not connect to <code>{e(host)}</code>.</p>'
            f'<p class="hint">{e(err)}</p>'
            '<p class="hint">Ensure you are on VPN and the RDS security group allows your IP on port 5432.</p>'
            '</div>'
        )

    conn_color  = "var(--sev-err)"  if snap.total_connections > snap.max_connections * 0.8 else "var(--sev-ok)"
    dead_color  = "var(--sev-err)"  if snap.deadlocks > 0 else "var(--sev-ok)"
    cache_color = "var(--sev-warn)" if snap.cache_hit_ratio < 95 else "var(--sev-ok)"

    stats = (
        _stat(f"{snap.total_connections} / {snap.max_connections}", "Connections (used/max)", conn_color) +
        _stat(f"{snap.active_connections}", "Active Queries",
              "var(--sev-warn)" if snap.active_connections > 10 else "var(--accent)") +
        _stat(f"{snap.idle_in_tx}", "Idle in Tx",
              "var(--sev-warn)" if snap.idle_in_tx > 0 else "var(--accent)") +
        _stat(f"{snap.db_size_mb:.1f} MB", "DB Size") +
        _stat(f"{snap.cache_hit_ratio:.1f}%", "Cache Hit Ratio", cache_color) +
        _stat(f"{snap.deadlocks}", "Deadlocks", dead_color)
    )

    info_row = (
        f'<div class="rds-info">'
        f'<span class="chip">🗄️ {e(snap.host)}</span>'
        f'<span class="chip">📦 {e(snap.database)}</span>'
        f'<span class="chip">{e(snap.pg_version)}</span>'
        + (f'<span class="chip">🔁 Replication lag: {snap.replication_lag_s}s</span>'
           if snap.replication_lag_s is not None else '')
        + f'</div>'
    )

    if snap.long_queries:
        lq_rows = ""
        for q in snap.long_queries:
            dur       = q.get("duration_s", 0)
            dur_color = "var(--sev-err)" if dur > 60 else "var(--sev-warn)"
            lq_rows += (
                f"<tr>"
                f'<td class="mono sm">{e(str(q.get("pid","")))}</td>'
                f'<td><span style="color:{dur_color};font-weight:600">{e(str(dur))}s</span></td>'
                f'<td class="sm">{e(str(q.get("state","")))}</td>'
                f'<td class="expand-cell mono sm text-m" title="{e(q.get("query",""))}">{e(q.get("query","")[:120])}</td>'
                f"</tr>"
            )
        long_q_html = (
            '<div class="card"><div class="card-hd">'
            f'<h2>Long-Running Queries</h2><span class="chip">{len(snap.long_queries)} queries &gt; 5s</span>'
            '</div><div class="tw"><table class="dt"><thead><tr>'
            '<th>PID</th><th>Duration</th><th>State</th><th>Query</th>'
            f'</tr></thead><tbody>{lq_rows}</tbody></table></div></div>'
        )
    else:
        long_q_html = (
            '<div class="card"><div class="card-hd"><h2>Long-Running Queries</h2></div>'
            '<div class="empty-state" style="padding:24px"><div class="ei" style="font-size:24px">✅</div>'
            '<p>No queries running longer than 5 seconds.</p></div></div>'
        )

    if snap.top_tables:
        max_mb   = max((float(t.get("size_mb") or 0) for t in snap.top_tables), default=1)
        tbl_rows = ""
        for t in snap.top_tables:
            mb = float(t.get("size_mb") or 0)
            tbl_rows += (
                f"<tr>"
                f'<td class="mono sm">{e(str(t.get("table_name","")))}</td>'
                f'<td class="num">{e(str(t.get("total_size","")))}</td>'
                f'<td class="num">{int(t.get("row_estimate") or 0):,}</td>'
                f'<td style="min-width:120px">{_bar(int(mb*10), int(max_mb*10), "var(--ac)", "6px")}</td>'
                f"</tr>"
            )
        tables_html = (
            '<div class="card"><div class="card-hd">'
            f'<h2>Top Tables by Size</h2><span class="chip">{len(snap.top_tables)} tables</span>'
            '</div><div class="tw"><table class="dt"><thead><tr>'
            '<th>Table</th><th>Size</th><th>Rows (est.)</th><th></th>'
            f'</tr></thead><tbody>{tbl_rows}</tbody></table></div></div>'
        )
    else:
        tables_html = ""

    return f"""
<div class="stats-grid">{stats}</div>
{info_row}
{long_q_html}
{tables_html}
"""
