"""
reporters/tabs/environment.py
──────────────────────────────
Environment Issues tab — per-env CloudWatch error breakdown.
"""
from __future__ import annotations

from collections import Counter

from reporters.components import (
    SEV_ORDER, SEV_VAR, _SEV_RANK,
    _badge, _bar, _fmt_json, _stat,
    e,
)


def render(env: str, d: dict, top: int = 15) -> str:
    """Render the full environment panel (stats + error table + warning table + sidebar)."""
    counts           = d.get("counts", Counter())
    sevs             = d.get("severities", {})
    samples          = d.get("raw_samples", {})
    raw_json_samples = d.get("raw_json_samples", {})
    svc_hits         = d.get("service_hits", {})
    latest           = d.get("latest", {})
    sev_tot          = d.get("sev_totals", Counter())
    totals           = d.get("totals", {})

    total_ev = sum(v for v in totals.values() if v >= 0)
    err_cnt  = sev_tot.get("ERROR", 0) + sev_tot.get("CRITICAL", 0) + sev_tot.get("FATAL", 0)
    exc_cnt  = sev_tot.get("EXCEPTION", 0)

    stats = (
        _stat(f"{total_ev:,}", "Total Events") +
        _stat(f"{err_cnt:,}", "Errors / Critical", "var(--sev-err)") +
        _stat(f"{exc_cnt:,}", "Exceptions", "var(--sev-exc)")
    )

    _ERROR_SEVS = {"FATAL", "CRITICAL", "ERROR", "EXCEPTION"}

    def _make_table(items: list, mx: int, label: str) -> str:
        if not items:
            return f'<div class="empty-state" style="padding:20px"><p>No {label.lower()} patterns.</p></div>'
        rows = ""
        for i, (key, cnt) in enumerate(items, 1):
            sev      = sevs.get(key, "?")
            svcs     = ", ".join(sorted(svc_hits.get(key, set())))
            last     = latest.get(key, "—")
            full_msg = samples.get(key, key)
            msg      = full_msg.split("\n")[0]
            raw_json = _fmt_json(raw_json_samples.get(key, ""))
            rows += (
                f"<tr>"
                f'<td class="rank">{i}</td>'
                f'<td>{_badge(sev)}</td>'
                f'<td class="num">{cnt:,}</td>'
                f'<td>{_bar(cnt, mx, SEV_VAR.get(sev, "var(--accent)"), "4px")}</td>'
                f'<td class="ts">{e(last)}</td>'
                f'<td class="sm text-m">{e(svcs)}</td>'
                f'<td class="expand-cell mono sm" title="{e(full_msg)}">{e(msg)}</td>'
                f'<td class="json-cell"><pre>{e(raw_json)}</pre></td>'
                f"</tr>"
            )
        return (
            '<div class="tw"><table class="dt"><thead><tr>'
            '<th>#</th><th>Sev</th><th>Count</th><th>Volume</th>'
            '<th>Last seen</th><th>Services</th>'
            '<th>Message ↕ click to expand</th>'
            '<th>Raw JSON ↕ click to expand</th>'
            f'</tr></thead><tbody>{rows}</tbody></table></div>'
        )

    if counts:
        mx           = counts.most_common(1)[0][1]
        sorted_items = sorted(
            ((k, counts[k]) for k in counts),
            key=lambda kv: (_SEV_RANK.get(sevs.get(kv[0], "?"), len(SEV_ORDER)), -kv[1]),
        )
        error_items = [(k, c) for k, c in sorted_items if sevs.get(k, "?") in _ERROR_SEVS][:top]
        errors_html = _make_table(error_items, mx, "error")
    else:
        errors_html = '<div class="empty-state"><p>No events found.</p></div>'
        error_items = []

    # Service bars
    valid   = {s: v for s, v in totals.items() if v >= 0}
    mx_svc  = max(valid.values()) if valid else 1
    svc_html = ""
    for svc, cnt in sorted(totals.items(), key=lambda x: -(x[1] if x[1] >= 0 else 0)):
        if cnt < 0:
            svc_html += (
                f'<div class="svc-row">'
                f'<span class="svc-nm">{e(svc)}</span>'
                f'<span class="sm text-m">access denied</span>'
                f'</div>'
            )
        else:
            svc_html += (
                f'<div class="svc-row">'
                f'<span class="svc-nm">{e(svc)}</span>'
                f'{_bar(cnt, mx_svc, "var(--accent)", "10px")}'
                f'<span class="svc-n">{cnt:,}</span>'
                f'</div>'
            )

    # Severity breakdown mini-bars
    sev_html = ""
    mx_sev   = max((sev_tot.get(s, 0) for s in SEV_ORDER), default=1)
    for s in SEV_ORDER:
        n = sev_tot.get(s, 0)
        if n:
            sev_html += (
                f'<div class="sev-row">'
                f'{_badge(s)}'
                f'<span class="sev-n">{n:,}</span>'
                f'{_bar(n, mx_sev, SEV_VAR.get(s, "var(--muted)"), "6px")}'
                f'</div>'
            )

    return f"""
<div class="stats-grid">{stats}</div>
<div class="env-grid">
  <div class="card span-main">
    <div class="card-hd"><h3>Top {top} Error Patterns</h3>
      <span class="chip">{len(error_items)} unique</span></div>
    {errors_html}
  </div>
  <div class="side-col">
    <div class="card">
      <div class="card-hd"><h3>Service Breakdown</h3></div>
      <div class="svc-bars">{svc_html}</div>
    </div>
    <div class="card">
      <div class="card-hd"><h3>By Severity</h3></div>
      <div class="sev-bars">{sev_html if sev_html else '<p class="text-m sm" style="padding:12px 16px">No data</p>'}</div>
    </div>
  </div>
</div>
"""
