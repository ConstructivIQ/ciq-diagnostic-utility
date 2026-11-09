"""
reporters/tabs/sync.py
───────────────────────
Integration Sync Failures tab:
  - _SYNC_CATS / categorise() — error category classifier
  - category_panel()          — summary grid of category counts
  - sub_table()               — most-impacted subscriptions
  - proj_table()              — most-impacted projects
"""
from __future__ import annotations

import re as _re
from collections import Counter

from reporters.components import (
    SEV_ORDER, SEV_VAR, _SEV_RANK,
    _badge, _bar, _fmt_json, _fmt_ts_ms, _stat,
    e,
)

# ── Category definitions ──────────────────────────────────────────────────────
# Each entry: (display_name, hex_color, [regex patterns matched against msg.lower()])
# First match wins; "Other" is the fallback.
_SYNC_CATS: list[tuple[str, str, list[str]]] = [
    ("Auth & Token",         "#e5493a", [
        r"auth", r"token", r"credential", r"access.?denied", r"unauthorized",
        r"forbidden", r"invalid.{0,10}key", r"permission.?denied",
    ]),
    ("User Sync",            "#f77f00", [
        r"duplicate.?email", r"existing.?user", r"user.?source", r"company.?info",
        r"email.?conflict", r"recreat", r"user.*not.*found",
    ]),
    ("Submittal Sync",       "#fcbf49", [
        r"submittal", r"revision", r"stuck.?sync",
    ]),
    ("Material Sync",        "#4bade8", [
        r"material.?import", r"duplicate.?material", r"linked.?activity",
        r"\bmaterial\b",
    ]),
    ("Spec Section",         "#904ee2", [
        r"spec.?section", r"spec.?number", r"spec.?title", r"cross.?source",
    ]),
    ("Data Mapping",         "#36b37e", [
        r"vendor.?mapping", r"field.?mapping", r"external.?attribute",
        r"mapping.?mismatch",
    ]),
    ("API Pagination",       "#0e6ba8", [
        r"paginat", r"partial.?extract", r"lookup.?data",
    ]),
    ("Job Processing",       "#e85d04", [
        r"processing.?state", r"stuck.?job", r"background.?job", r"failed.?job",
        r"PROCESSING",
    ]),
    ("Timeout & Service",    "#d62828", [
        r"timeout", r"timed.?out", r"hasura", r"connectivity",
        r"transient", r"service.?unavail", r"internal.?api",
    ]),
    ("Data Quality",         "#9b2226", [
        r"invalid.?char", r"malformed", r"payload", r"data.?inconsist",
        r"ingestion.?fail",
    ]),
    ("Linking & Relations",  "#023e8a", [
        r"linking", r"relationship", r"material.{0,10}activity",
        r"deleted.?ref", r"submittal.{0,10}material",
    ]),
    ("Company & Metadata",   "#6a994e", [
        r"company.?sync", r"team.?member", r"project.?company", r"metadata",
    ]),
    ("Integration-Specific", "#7b2d8b", [
        r"\bacc\b", r"procore", r"cmic",
    ]),
    ("Platform-Wide",        "#ae2012", [
        r"outage", r"environment.?wide", r"release.{0,10}integr", r"platform",
    ]),
]
_CAT_OTHER = ("Other", "#6b778c")


def categorise(msg: str) -> tuple[str, str]:
    """Return (category_name, hex_color) for a sync error message."""
    lower = (msg or "").lower()
    for name, color, patterns in _SYNC_CATS:
        if any(_re.search(p, lower) for p in patterns):
            return name, color
    return _CAT_OTHER


def category_panel(env_data: dict) -> str:
    """Render a category-breakdown card for the Integration Sync Failures tab."""
    sub_top: dict[str, tuple[str, str]] = {}
    for d in env_data.values():
        raw_samples = d.get("raw_samples", {})
        for key, sids in d.get("sub_hits", {}).items():
            sev = d.get("severities", {}).get(key, "?")
            msg = raw_samples.get(key, key)
            for sid in sids:
                cur_sev = sub_top.get(sid, ("", "?"))[1] if isinstance(sub_top.get(sid), tuple) else "?"
                if sid not in sub_top or SEV_ORDER.index(sev) < SEV_ORDER.index(cur_sev):
                    sub_top[sid] = (msg, sev)

    cat_counts: Counter = Counter()
    for msg_sev in sub_top.values():
        msg = msg_sev[0] if isinstance(msg_sev, tuple) else str(msg_sev)
        cat_name, _ = categorise(msg)
        cat_counts[cat_name] += 1

    if not cat_counts:
        return ""

    total = sum(cat_counts.values())
    chips = ""
    for name, color, _ in _SYNC_CATS:
        cnt = cat_counts.get(name, 0)
        if cnt == 0:
            continue
        pct   = round(cnt / total * 100)
        bar_w = max(4, pct)
        chips += (
            f'<div class="cat-card">'
            f'<div class="cat-top">'
            f'<span class="cat-name" style="color:{color}">{e(name)}</span>'
            f'<span class="cat-count">{cnt}</span>'
            f'</div>'
            f'<div class="cat-bar-bg"><div class="cat-bar" style="width:{bar_w}%;background:{color}"></div></div>'
            f'<div class="cat-pct">{pct}% of affected subs</div>'
            f'</div>'
        )
    other_cnt = cat_counts.get("Other", 0)
    if other_cnt:
        chips += (
            f'<div class="cat-card">'
            f'<div class="cat-top"><span class="cat-name" style="color:#6b778c">Other</span>'
            f'<span class="cat-count">{other_cnt}</span></div>'
            f'<div class="cat-bar-bg"><div class="cat-bar" style="width:{max(4,round(other_cnt/total*100))}%;background:#6b778c"></div></div>'
            f'<div class="cat-pct">{round(other_cnt/total*100)}% of affected subs</div>'
            f'</div>'
        )

    return (
        '<div class="card" style="margin-bottom:16px">'
        '<div class="card-hd"><h2>Issue Category Breakdown</h2>'
        f'<span class="chip">{total} subscriptions classified</span></div>'
        f'<div class="cat-grid">{chips}</div>'
        '</div>'
    )


_ROW_CLS = {"FATAL": "row-fatal", "CRITICAL": "row-crit",
            "ERROR": "row-error", "EXCEPTION": "row-error", "WARN": "row-warn"}


def sub_table(env_data: dict, show_env_col: bool = True, show_cust_col: bool = True) -> str:
    """Most-impacted subscriptions table."""
    sub_errors:       Counter = Counter()
    sub_envs:         dict[str, set] = {}
    sub_svcs:         dict[str, set] = {}
    sub_top_err:      dict[str, str] = {}
    sub_top_raw_json: dict[str, str] = {}
    sub_top_sev:      dict[str, str] = {}
    sub_last_ms:      dict[str, int] = {}
    cust_name_map:    dict[str, str] = {}

    for env, d in env_data.items():
        rjs = d.get("raw_json_samples", {})
        for sid, cnt in d.get("sub_errors", {}).items():
            sub_errors[sid] += cnt
            sub_envs.setdefault(sid, set()).add(env.upper())
        for key, sids in d.get("sub_hits", {}).items():
            sev    = d.get("severities", {}).get(key, "?")
            sample = d.get("raw_samples", {}).get(key, key)
            svcs   = d.get("service_hits", {}).get(key, set())
            for sid in sids:
                if (sid not in sub_top_sev or
                        SEV_ORDER.index(sev) < SEV_ORDER.index(sub_top_sev[sid])):
                    sub_top_err[sid]      = sample
                    sub_top_raw_json[sid] = rjs.get(key, "")
                    sub_top_sev[sid]      = sev
                sub_svcs.setdefault(sid, set()).update(svcs)
        for sid, ts_ms in d.get("sub_latest", {}).items():
            if ts_ms > sub_last_ms.get(sid, 0):
                sub_last_ms[sid] = ts_ms
        for sid, name in d.get("cust_names", {}).items():
            if name and sid not in cust_name_map:
                cust_name_map[sid] = name

    if not sub_errors:
        return (
            '<div class="empty-state"><div class="ei">🔍</div>'
            '<p>No subscription IDs extracted from logs.</p>'
            '<p class="hint">Paste a sample log line so the extractor can be tuned.</p></div>'
        )

    mx           = max(sub_errors.values())
    sorted_subs  = sorted(
        sub_errors.items(),
        key=lambda kv: (_SEV_RANK.get(sub_top_sev.get(kv[0], "?"), len(SEV_ORDER)), -kv[1]),
    )
    rows = ""
    for i, (sid, cnt) in enumerate(sorted_subs[:25], 1):
        sev       = sub_top_sev.get(sid, "?")
        full_msg  = sub_top_err.get(sid, "—")
        msg       = full_msg.split("\n")[0]
        raw_json  = _fmt_json(sub_top_raw_json.get(sid, ""))
        cat_name, cat_color = categorise(full_msg)
        last_seen = _fmt_ts_ms(sub_last_ms.get(sid, 0))
        cust      = cust_name_map.get(sid, "—")
        env_cell  = (
            f'<td class="sm text-m">{e(", ".join(sorted(sub_envs.get(sid, set()))))}</td>'
            if show_env_col else ""
        )
        cust_cell = f'<td class="sm">{e(cust)}</td>' if show_cust_col else ""
        rc        = _ROW_CLS.get(sev, "")
        row_cls   = f' class="{rc}"' if rc else ""
        rows += (
            f"<tr{row_cls}>"
            f'<td class="rank">{i}</td>'
            f'<td class="mono">{e(sid)}</td>'
            f'{cust_cell}'
            f'<td class="num">{cnt:,}</td>'
            f'<td>{_bar(cnt, mx, SEV_VAR.get(sev, "var(--accent)"), "6px")}</td>'
            f'<td>{_badge(sev)}</td>'
            f'{env_cell}'
            f'<td class="ts">{e(last_seen)}</td>'
            f'<td class="sm text-m">{e(", ".join(sorted(sub_svcs.get(sid, set()))))}</td>'
            f'<td><span class="cat-chip" style="background:{cat_color}22;color:{cat_color};border-color:{cat_color}55">{e(cat_name)}</span></td>'
            f'<td class="expand-cell mono sm text-m" title="{e(full_msg)}">{e(msg)}</td>'
            f'<td class="json-cell"><pre>{e(raw_json)}</pre></td>'
            f"</tr>"
        )
    env_th  = "<th>Envs</th>" if show_env_col else ""
    cust_th = "<th>Customer</th>" if show_cust_col else ""
    return (
        '<div class="tw"><table class="dt">'
        '<thead><tr>'
        f'<th>#</th><th>Subscription ID</th>{cust_th}<th>Errors</th><th>Volume</th>'
        f'<th>Worst</th>{env_th}<th>Last seen</th><th>Services</th>'
        '<th>Category</th><th>Message ↕ click to expand</th><th>Raw JSON ↕ click to expand</th>'
        '</tr></thead>'
        f'<tbody>{rows}</tbody></table></div>'
    )


def proj_table(env_data: dict) -> str:
    """Most-impacted projects table."""
    proj_errors:       Counter = Counter()
    proj_envs:         dict[str, set] = {}
    proj_svcs:         dict[str, set] = {}
    proj_top_err:      dict[str, str] = {}
    proj_top_raw_json: dict[str, str] = {}
    proj_top_sev:      dict[str, str] = {}
    proj_last_ms:      dict[str, int] = {}

    for env, d in env_data.items():
        rjs = d.get("raw_json_samples", {})
        for pid, cnt in d.get("proj_errors", {}).items():
            proj_errors[pid] += cnt
            proj_envs.setdefault(pid, set()).add(env.upper())
        for key, pids in d.get("proj_hits", {}).items():
            sev    = d.get("severities", {}).get(key, "?")
            sample = d.get("raw_samples", {}).get(key, key)
            svcs   = d.get("service_hits", {}).get(key, set())
            for pid in pids:
                if (pid not in proj_top_sev or
                        SEV_ORDER.index(sev) < SEV_ORDER.index(proj_top_sev[pid])):
                    proj_top_err[pid]      = sample
                    proj_top_raw_json[pid] = rjs.get(key, "")
                    proj_top_sev[pid]      = sev
                proj_svcs.setdefault(pid, set()).update(svcs)
        for pid, ts_ms in d.get("proj_latest", {}).items():
            if ts_ms > proj_last_ms.get(pid, 0):
                proj_last_ms[pid] = ts_ms

    if not proj_errors:
        return '<div class="empty-state"><div class="ei">🔍</div><p>No project IDs found in logs.</p></div>'

    mx           = max(proj_errors.values())
    sorted_projs = sorted(
        proj_errors.items(),
        key=lambda kv: (_SEV_RANK.get(proj_top_sev.get(kv[0], "?"), len(SEV_ORDER)), -kv[1]),
    )
    rows = ""
    for i, (pid, cnt) in enumerate(sorted_projs[:25], 1):
        sev       = proj_top_sev.get(pid, "?")
        full_msg  = proj_top_err.get(pid, "—")
        msg       = full_msg.split("\n")[0]
        raw_json  = _fmt_json(proj_top_raw_json.get(pid, ""))
        last_seen = _fmt_ts_ms(proj_last_ms.get(pid, 0))
        cat_name, cat_color = categorise(full_msg)
        rc        = _ROW_CLS.get(sev, "")
        row_cls   = f' class="{rc}"' if rc else ""
        rows += (
            f"<tr{row_cls}>"
            f'<td class="rank">{i}</td>'
            f'<td class="mono">{e(pid)}</td>'
            f'<td class="num">{cnt:,}</td>'
            f'<td>{_bar(cnt, mx, SEV_VAR.get(sev, "var(--accent)"), "6px")}</td>'
            f'<td>{_badge(sev)}</td>'
            f'<td class="sm text-m">{e(", ".join(sorted(proj_envs.get(pid, set()))))}</td>'
            f'<td class="ts">{e(last_seen)}</td>'
            f'<td class="sm text-m">{e(", ".join(sorted(proj_svcs.get(pid, set()))))}</td>'
            f'<td><span class="cat-chip" style="background:{cat_color}22;color:{cat_color};border-color:{cat_color}55">{e(cat_name)}</span></td>'
            f'<td class="expand-cell mono sm text-m" title="{e(full_msg)}">{e(msg)}</td>'
            f'<td class="json-cell"><pre>{e(raw_json)}</pre></td>'
            f"</tr>"
        )
    return (
        '<div class="tw"><table class="dt">'
        '<thead><tr>'
        '<th>#</th><th>Project ID</th><th>Errors</th><th>Volume</th>'
        '<th>Worst</th><th>Envs</th><th>Last seen</th><th>Services</th>'
        '<th>Category</th><th>Message ↕ click to expand</th><th>Raw JSON ↕ click to expand</th>'
        '</tr></thead>'
        f'<tbody>{rows}</tbody></table></div>'
    )
