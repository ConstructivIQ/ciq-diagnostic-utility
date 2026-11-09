"""
reporters/tabs/tickets.py
──────────────────────────
Customer Tickets tab renderer (Jira issues with label Prod_Issue).
"""
from __future__ import annotations

from reporters.components import (
    _TYPE_ICON_SVG, _TYPE_ICON_DEFAULT,
    _priority_badge, _status_badge, _fmt_date,
    e,
)


def render(tickets: list[dict]) -> str:
    """Render the Jira tickets table body HTML."""
    if not tickets:
        return (
            '<div class="empty-state"><div class="ei">🎫</div>'
            '<p>No Jira issues found with label <code>Prod_Issue</code> in the active statuses.</p>'
            '<p class="hint">Check that your JIRA_BASE_URL, JIRA_EMAIL and JIRA_API_TOKEN are set.</p>'
            '</div>'
        )

    rows = ""
    for t in tickets:
        itype    = t.get("issue_type", "")
        icon     = _TYPE_ICON_SVG.get(itype.lower(), _TYPE_ICON_DEFAULT)
        key      = t.get("key", "")
        url      = t.get("url", "")
        key_link = f'<a href="{e(url)}" target="_blank" class="key-link">{e(key)}</a>' if url else e(key)
        priority = t.get("priority", "—")
        status   = t.get("status", "—")
        sprint   = t.get("sprint", "") or "—"
        assignee = t.get("assignee", "Unassigned") or "Unassigned"
        reporter = t.get("reporter", "") or "—"
        customer = t.get("customer_name", "") or "—"
        created  = _fmt_date(t.get("created", ""))
        summary  = t.get("summary", "")

        rows += (
            f"<tr>"
            f'<td class="sm text-m" style="white-space:nowrap;min-width:80px">{icon} {e(itype)}</td>'
            f'<td class="sm">{e(customer)}</td>'
            f'<td class="mono sm" style="white-space:nowrap">{key_link}</td>'
            f'<td>{_priority_badge(priority)}</td>'
            f'<td class="ts">{e(created)}</td>'
            f'<td class="sm text-m">{e(sprint)}</td>'
            f'<td class="sm">{e(assignee)}</td>'
            f'<td class="sm text-m">{e(reporter)}</td>'
            f'<td>{_status_badge(status)}</td>'
            f'<td class="expand-cell sm" title="{e(summary)}">{e(summary)}</td>'
            f"</tr>"
        )

    return (
        '<div class="tw"><table class="dt">'
        '<thead><tr>'
        '<th>Type</th><th>Customer</th><th>Key</th><th>Priority</th>'
        '<th>Created</th><th>Sprint</th><th>Assignee</th><th>Reporter</th>'
        '<th>Status</th><th>Summary</th>'
        '</tr></thead>'
        f'<tbody>{rows}</tbody></table></div>'
    )
