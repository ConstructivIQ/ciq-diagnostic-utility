"""
collectors/jira_collector.py
Fetches issue details, comments, and linked issues from Jira REST API v3.
"""
from __future__ import annotations
from typing import Any
import requests
import config


def _auth() -> tuple[str, str]:
    return (config.JIRA_EMAIL, config.JIRA_API_TOKEN)


def _get(path: str, params: dict | None = None) -> Any:
    url = f"{config.JIRA_BASE_URL.rstrip('/')}/rest/api/3/{path.lstrip('/')}"
    resp = requests.get(url, auth=_auth(), params=params, timeout=20)
    resp.raise_for_status()
    return resp.json()


def _post(path: str, body: dict) -> Any:
    """POST to Jira REST API v3 with a JSON body (required for search/jql)."""
    url = f"{config.JIRA_BASE_URL.rstrip('/')}/rest/api/3/{path.lstrip('/')}"
    resp = requests.post(url, auth=_auth(), json=body, timeout=20)
    resp.raise_for_status()
    return resp.json()


# ── Customer-name field — confirmed for constructiviq.atlassian.net ───────────
# customfield_10550 is a single-select whose values look like
# [{"value": "DPR/vConstruct", "id": "10490", ...}].
# Discovery via /field is skipped because a generic name like "Account" can
# match a *different* field on this instance, returning the wrong ID and an
# empty column.  The field ID is stable across Jira Cloud instances for the
# same site, so we pin it here.

_CUSTOMER_FIELD_ID = "customfield_10550"


def _customer_field_id() -> str:
    return _CUSTOMER_FIELD_ID


def _extract_customer(fields: dict, field_id: str) -> str:
    if not field_id or field_id not in fields:
        return ""
    val = fields[field_id]
    if isinstance(val, dict):
        return val.get("name") or val.get("displayName") or val.get("value") or ""
    if isinstance(val, str):
        return val
    if isinstance(val, list) and val:
        first = val[0]
        if isinstance(first, dict):
            return first.get("name") or first.get("displayName") or first.get("value") or ""
        return str(first)
    return ""


def _extract_sprint(fields: dict) -> str:
    """Return name of active (or latest) sprint from customfield_10020."""
    sprints = fields.get("customfield_10020") or []
    if not sprints:
        return ""
    # prefer active sprint
    for sp in sprints:
        if isinstance(sp, dict) and sp.get("state") == "active":
            return sp.get("name", "")
    # fall back to last in list
    last = sprints[-1]
    return last.get("name", "") if isinstance(last, dict) else ""


# ── Public API ────────────────────────────────────────────────────────────────

def fetch_issue(issue_key: str) -> dict:
    """Return a structured dict with the core fields for a single Jira issue."""
    raw = _get(f"issue/{issue_key}", params={
        "fields": "summary,description,status,priority,assignee,reporter,"
                  "created,updated,comment,issuetype,labels,components,"
                  "customfield_10016"
    })
    fields = raw.get("fields", {})
    description_text = _adf_to_text(fields.get("description") or {})
    comments = []
    for c in (fields.get("comment") or {}).get("comments", []):
        comments.append({
            "author": (c.get("author") or {}).get("displayName", "unknown"),
            "created": c.get("created", ""),
            "body": _adf_to_text(c.get("body") or {}),
        })
    return {
        "key": raw.get("key"),
        "summary": fields.get("summary", ""),
        "status": (fields.get("status") or {}).get("name", ""),
        "priority": (fields.get("priority") or {}).get("name", ""),
        "issue_type": (fields.get("issuetype") or {}).get("name", ""),
        "reporter": (fields.get("reporter") or {}).get("displayName", ""),
        "assignee": (fields.get("assignee") or {}).get("displayName", "Unassigned"),
        "created": fields.get("created", ""),
        "updated": fields.get("updated", ""),
        "labels": fields.get("labels", []),
        "components": [c.get("name") for c in (fields.get("components") or [])],
        "description": description_text,
        "comments": comments,
        "url": f"{config.JIRA_BASE_URL.rstrip('/')}/browse/{raw.get('key')}",
    }


def search_issues(jql: str, max_results: int = 20) -> list[dict]:
    """Run a JQL query and return a list of condensed issue dicts."""
    data = _post("search/jql", {"jql": jql, "maxResults": max_results,
                                "fields": ["summary", "status", "priority",
                                           "created", "updated", "issuetype"]})
    results = []
    for issue in data.get("issues", []):
        f = issue.get("fields", {})
        results.append({
            "key": issue.get("key"),
            "summary": f.get("summary", ""),
            "status": (f.get("status") or {}).get("name", ""),
            "priority": (f.get("priority") or {}).get("name", ""),
            "issue_type": (f.get("issuetype") or {}).get("name", ""),
            "created": f.get("created", ""),
            "updated": f.get("updated", ""),
            "url": f"{config.JIRA_BASE_URL.rstrip('/')}/browse/{issue.get('key')}",
        })
    return results


def fetch_prod_issues(max_results: int = 200) -> list[dict]:
    """
    Fetch Jira issues labelled 'Prod_Issue' whose status is one of:
    Backlog, Ready For Dev, Under Dev, Dev Complete (and common casing variants).

    Returns a list of dicts with all columns needed for the Customer Tickets tab.
    """
    cf = _customer_field_id()
    extra = f",{cf}" if cf else ""

    # statusCategory != Done is simpler and more reliable than listing every
    # status name variant — it matches any status not in the "Done" category
    # (i.e. Backlog, Ready For Dev, Under Dev, Dev Complete, Under QA, etc.)
    jql = 'labels = "Prod_Issue" AND statusCategory != Done ORDER BY created DESC'

    fields = [
        "summary", "status", "priority", "created", "assignee", "reporter",
        "issuetype", "labels", "customfield_10020",
    ]
    if cf:
        fields.append(cf)

    data = _post("search/jql", {
        "jql": jql,
        "maxResults": max_results,
        "fields": fields,
    })

    results = []
    for issue in data.get("issues", []):
        f = issue.get("fields", {})
        results.append({
            "key":           issue.get("key", ""),
            "summary":       f.get("summary", ""),
            "status":        (f.get("status") or {}).get("name", ""),
            "priority":      (f.get("priority") or {}).get("name", ""),
            "issue_type":    (f.get("issuetype") or {}).get("name", ""),
            "customer_name": _extract_customer(f, cf),
            "created":       f.get("created", ""),
            "sprint":        _extract_sprint(f),
            "assignee":      (f.get("assignee") or {}).get("displayName", "Unassigned"),
            "reporter":      (f.get("reporter") or {}).get("displayName", ""),
            "labels":        f.get("labels", []),
            "url":           f"{config.JIRA_BASE_URL.rstrip('/')}/browse/{issue.get('key')}",
        })
    return results


def _adf_to_text(node: dict, depth: int = 0) -> str:
    """Recursively convert an ADF node tree to plain text."""
    if not node:
        return ""
    node_type = node.get("type", "")
    if node_type == "text":
        return node.get("text", "")
    children = node.get("content", [])
    child_text = "".join(_adf_to_text(c, depth + 1) for c in children)
    if node_type in ("paragraph", "blockquote"):
        return child_text + "\n"
    if node_type == "heading":
        return "\n" + child_text + "\n"
    if node_type == "listItem":
        return "- " + child_text.strip() + "\n"
    if node_type == "codeBlock":
        return "\n```\n" + child_text + "\n```\n"
    if node_type == "hardBreak":
        return "\n"
    return child_text
