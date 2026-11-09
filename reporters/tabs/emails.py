"""
reporters/tabs/emails.py
─────────────────────────
Support Emails tab renderer.
"""
from __future__ import annotations

from reporters.components import e


def render(emails: list) -> str:
    if not emails:
        return (
            '<div class="empty-state"><div class="ei">📧</div>'
            '<p>No emails from the last 2 days.</p>'
            '<p class="hint">Check that EMAIL_HOST, EMAIL_USER and EMAIL_PASSWORD are set in .env</p>'
            '</div>'
        )

    rows = ""
    for em in emails:
        subject      = getattr(em, "subject", "") or "(no subject)"
        sender       = getattr(em, "sender", "") or "—"
        date         = getattr(em, "date", "") or "—"
        body         = getattr(em, "body", "") or ""
        has_att      = getattr(em, "has_attachments", False)
        att_icon     = "📎 " if has_att else ""
        body_preview = body.replace("\r\n", "\n").replace("\r", "\n").strip()
        rows += (
            f"<tr>"
            f'<td class="expand-cell sm" title="{e(sender)}">{e(sender)}</td>'
            f'<td class="expand-cell sm" title="{e(subject)}">{e(att_icon)}{e(subject)}</td>'
            f'<td class="ts sm" style="white-space:nowrap">{e(date)}</td>'
            f'<td class="expand-cell sm text-m" title="{e(body_preview)}">{e(body_preview[:300])}</td>'
            f"</tr>"
        )

    return (
        '<div class="tw"><table class="dt">'
        '<thead><tr><th>From</th><th>Subject</th><th>Date</th><th>Preview</th></tr></thead>'
        f'<tbody>{rows}</tbody></table></div>'
    )
