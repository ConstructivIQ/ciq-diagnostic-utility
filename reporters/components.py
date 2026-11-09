"""
reporters/components.py
───────────────────────
Shared building blocks used by every tab renderer:
  - HTML escape helper
  - JSON formatter
  - Severity constants (SEV_ORDER, SEV_VAR, _SEV_RANK, ENV_ICON)
  - Jira icon helpers (_jira_icon, _TYPE_ICON_SVG, _TYPE_ICON_DEFAULT)
  - Micro-components (_badge, _bar, _stat, _status_badge, _priority_badge)
  - Date/time formatters (_fmt_date, _fmt_ts_ms)
"""
from __future__ import annotations

import html as html_lib
import json as _json
from datetime import datetime, timedelta, timezone
from typing import Any

# Indian Standard Time — UTC+5:30
_IST = timezone(timedelta(hours=5, minutes=30))

# ── Severity ordering ─────────────────────────────────────────────────────────
SEV_ORDER = ["FATAL", "CRITICAL", "ERROR", "EXCEPTION", "WARN", "?"]
SEV_VAR = {
    "FATAL":     "var(--sev-fatal)",
    "CRITICAL":  "var(--sev-crit)",
    "ERROR":     "var(--sev-err)",
    "EXCEPTION": "var(--sev-err)",
    "WARN":      "var(--sev-warn)",
    "?":         "var(--muted)",
}
_SEV_RANK = {s: i for i, s in enumerate(SEV_ORDER)}
ENV_ICON  = {"prod": "🔴", "dev": "🟢", "qa": "🟡", "perf": "🔵", "demo": "🟣"}

# ── Jira display config ───────────────────────────────────────────────────────
_STATUS_MAP = {
    "backlog":       ("Backlog",       "#7d8590"),
    "readyfordev":   ("Ready For Dev", "#388bfd"),
    "ready for dev": ("Ready For Dev", "#388bfd"),
    "underdev":      ("Under Dev",     "#d29922"),
    "under dev":     ("Under Dev",     "#d29922"),
    "in progress":   ("In Progress",   "#d29922"),
    "devcomplete":   ("Dev Complete",  "#3fb950"),
    "dev complete":  ("Dev Complete",  "#3fb950"),
    "underqa":       ("Under QA",      "#a371f7"),
    "under qa":      ("Under QA",      "#a371f7"),
    "qacomplete":    ("QA Complete",   "#7ee787"),
    "qa complete":   ("QA Complete",   "#7ee787"),
    "uat/stg":       ("UAT/STG",       "#f78166"),
    "uatstg":        ("UAT/STG",       "#f78166"),
    "uat stg":       ("UAT/STG",       "#f78166"),
    "done":          ("Done",          "#3fb950"),
}
_PRIORITY_COLOR = {
    "highest":  "#f85149",
    "critical": "#f85149",
    "high":     "#e3b341",
    "medium":   "#d29922",
    "low":      "#3fb950",
    "lowest":   "#7d8590",
}


def _jira_icon(inner: str, alt: str, size: int = 18) -> str:
    """Wrap SVG strokes in a data-URI <img>. No background — just the icon in its type colour."""
    import urllib.parse as _ul
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" '
        f'width="{size}" height="{size}">{inner}</svg>'
    )
    return (
        f'<img src="data:image/svg+xml,{_ul.quote(svg, safe="")}" alt="{alt}" '
        f'width="{size}" height="{size}" style="vertical-align:middle">'
    )


_TYPE_ICON_SVG: dict[str, str] = {
    "story": _jira_icon(
        '<path d="M3 1.5h10v13l-5-3-5 3z" fill="none" stroke="#36b37e" '
        'stroke-width="1.6" stroke-linejoin="round"/>',
        "Story",
    ),
    "bug": _jira_icon(
        '<ellipse cx="8" cy="10" rx="3.5" ry="4" fill="none" stroke="#e5493a" stroke-width="1.4"/>'
        '<path d="M5.5 7c0-1.4 1.1-2.5 2.5-2.5s2.5 1.1 2.5 2.5" fill="none" stroke="#e5493a" stroke-width="1.4"/>'
        '<line x1="7" y1="4.8" x2="5.5" y2="3.2" stroke="#e5493a" stroke-width="1.2" stroke-linecap="round"/>'
        '<line x1="9" y1="4.8" x2="10.5" y2="3.2" stroke="#e5493a" stroke-width="1.2" stroke-linecap="round"/>'
        '<line x1="4.5" y1="9" x2="2.5" y2="8.5" stroke="#e5493a" stroke-width="1.2" stroke-linecap="round"/>'
        '<line x1="4.5" y1="11" x2="2.5" y2="11" stroke="#e5493a" stroke-width="1.2" stroke-linecap="round"/>'
        '<line x1="11.5" y1="9" x2="13.5" y2="8.5" stroke="#e5493a" stroke-width="1.2" stroke-linecap="round"/>'
        '<line x1="11.5" y1="11" x2="13.5" y2="11" stroke="#e5493a" stroke-width="1.2" stroke-linecap="round"/>',
        "Bug",
    ),
    "task": _jira_icon(
        '<rect x="2" y="2" width="12" height="12" rx="2" fill="none" stroke="#4bade8" stroke-width="1.6"/>'
        '<path d="M5 8l2.2 2.5L11 6" stroke="#4bade8" stroke-width="1.6" fill="none" '
        'stroke-linecap="round" stroke-linejoin="round"/>',
        "Task",
    ),
    "subtask": _jira_icon(
        '<rect x="2" y="2" width="12" height="12" rx="2" fill="none" stroke="#4bade8" stroke-width="1.6"/>'
        '<path d="M5 8l2.2 2.5L11 6" stroke="#4bade8" stroke-width="1.6" fill="none" '
        'stroke-linecap="round" stroke-linejoin="round"/>',
        "Subtask",
    ),
    "epic": _jira_icon(
        '<path d="M9.5 2l-5 7h4.5l-3 5 7-8H8.5z" fill="none" stroke="#904ee2" '
        'stroke-width="1.4" stroke-linejoin="round"/>',
        "Epic",
    ),
}
_TYPE_ICON_DEFAULT = _jira_icon(
    '<circle cx="8" cy="8" r="5.5" fill="none" stroke="#6b778c" stroke-width="1.5"/>',
    "Issue",
)


# ── Utility functions ─────────────────────────────────────────────────────────

def e(v: Any) -> str:
    return html_lib.escape(str(v or ""))


def _fmt_json(raw: str) -> str:
    """Pretty-print raw string if it's valid JSON, otherwise return as-is."""
    try:
        return _json.dumps(_json.loads(raw), indent=2, ensure_ascii=False)
    except Exception:
        return raw


def _fmt_date(iso: str) -> str:
    """Convert Jira ISO datetime to 'DD Mon YYYY HH:MM IST'."""
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(_IST)
        return dt.strftime("%d %b %Y %H:%M IST")
    except Exception:
        return iso[:10]


def _fmt_ts_ms(ts_ms: int) -> str:
    """Convert epoch milliseconds to 'DD Mon YYYY HH:MM:SS IST'."""
    if not ts_ms:
        return "—"
    try:
        return (datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
                .astimezone(_IST).strftime("%d %b %Y %H:%M:%S IST"))
    except Exception:
        return "—"


# ── Micro-components ──────────────────────────────────────────────────────────

def _badge(sev: str) -> str:
    color = SEV_VAR.get(sev, SEV_VAR["?"])
    return f'<span class="sev-badge" style="background:{color};">{e(sev)}</span>'


def _bar(value: int, max_val: int, color_var: str = "var(--accent)", h: str = "8px") -> str:
    pct = round(value / max_val * 100) if max_val else 0
    return (
        f'<div class="bar-track">'
        f'<div class="bar-fill" style="width:{pct}%;background:{color_var};height:{h};"></div>'
        f'</div>'
    )


def _stat(value: Any, label: str, color: str = "var(--accent)") -> str:
    return (
        f'<div class="stat-card">'
        f'<div class="stat-val" style="color:{color};">{e(value)}</div>'
        f'<div class="stat-lbl">{e(label)}</div>'
        f'</div>'
    )


def _status_badge(status: str) -> str:
    key = status.lower().strip()
    label, color = _STATUS_MAP.get(key, (status, "#7d8590"))
    return f'<span class="jstatus-badge" style="background:{color}22;color:{color};border-color:{color}55;">{e(label)}</span>'


def _priority_badge(priority: str) -> str:
    color = _PRIORITY_COLOR.get(priority.lower(), "#7d8590")
    return f'<span class="sev-badge" style="background:{color};">{e(priority)}</span>'
