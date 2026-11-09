"""
collectors/project_collector.py
─────────────────────────────────
Fetches all CloudWatch Insights errors for a given project_id across
the ECS (JOB) and Lambda log groups for the requested environment.

Returns a dict:
{
    "project_id":   str,
    "env":          str,
    "hours":        int,
    "region":       str,
    "log_groups":   {"ecs": str|None, "lambda": str|None},
    "errors":       [{"ts": str, "import_log_id": str, "level": str,
                      "message": str, "error_name": str, "raw": str}],
    "total":        int,
    "unknown_groups": bool,   # True when prod log groups couldn't be resolved
    "group_errors": {log_group: error_msg},  # any log groups that failed
}
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any

# ── Log group map (matches debugging guide + check_errors.py conventions) ──────
_LOG_GROUPS: dict[str, dict] = {
    "dev": {
        "region": "us-east-2",
        "ecs":    "/ecs/dev-ciq-dataintegration",
        "lambda": "/aws/lambda/ciq-dev-ciq-dataintegration",
    },
    "qa": {
        "region": "us-east-2",
        "ecs":    "/ecs/qa-ciq-dataintegration",
        "lambda": "/aws/lambda/ciq-qa-ciq-dataintegration",
    },
    "perf": {
        "region": "us-east-2",
        "ecs":    "/ecs/perf-ciq-dataintegration",
        "lambda": "/aws/lambda/ciq-perf-ciq-dataintegration",
    },
    "demo": {
        "region": "us-east-1",
        "ecs":    "/ecs/ciq-demo2-useast1-data-integration-job",
        "lambda": "/aws/lambda/ciq-demo2-useast1-lambda-data-integration",
    },
    "prod": {
        "region": "us-east-1",
        "ecs":    "/ecs/ciq-prod-useast1-data-integration-job",
        "lambda": "/aws/lambda/ciq-prod-useast1-lambda-data-integration",
    },
}

# Keywords used to identify the right groups when scanning all log groups
# For ECS: prefix /ecs/, must contain all keywords in at least one set
# For Lambda: prefix /aws/lambda/, same logic
_SCAN_KEYWORDS = {
    "ecs":    [["data", "integr"], ["di-job"], ["dataintegration"]],
    "lambda": [["data", "integr"], ["di-lambda"], ["dataintegration"]],
}

# Key service keyword sets — a log group matches if its name (lowercased)
# contains ALL keywords in at least one set.
_KEY_SERVICE_PATTERNS: list[list[str]] = [
    ["auth"],
    ["data", "integr"],   # data-integration / dataintegration
    ["date", "block"],   # date-block-engine
    ["report", "engine"],
    ["extract"],
]


# Log group name substrings that are never application logs (metrics, insights)
_EXCLUDE_LOG_GROUP_SUBSTRINGS: list[str] = [
    "containerinsights",  # ECS performance metrics, not app logs
]

# Non-prod environment markers to exclude when env == "prod"
_NON_PROD_MARKERS: list[str] = [
    "demo", "sandbox", "pilot", "-sb-", "ciq-sb-", "ciq-qa-", "ciq-dev-", "ciq-perf-",
]


def _matches_key_service(name: str, env: str = "prod") -> bool:
    lower = name.lower()
    # Skip infrastructure/metrics log groups
    if any(excl in lower for excl in _EXCLUDE_LOG_GROUP_SUBSTRINGS):
        return False
    # Env-scoped: for prod, exclude groups belonging to other envs
    if env == "prod":
        if any(marker in lower for marker in _NON_PROD_MARKERS):
            return False
    elif env == "demo":
        if "demo" not in lower:
            return False
    # dev / qa / perf are on us-east-2 so region already isolates them
    return any(all(k in lower for k in kws) for kws in _KEY_SERVICE_PATTERNS)

# CWI query: all error + warn lines for a project_id
_QUERY = """fields @timestamp, @message
| filter @message like /{project_id}/ and (@message like /level:error/ or @message like /level:warn/){extra_filter}
| sort @timestamp desc
| limit 1000"""

# Regex to extract import_log_id and error details from log lines
_IMPORT_LOG_RE = re.compile(
    r"import[_\-]?log[_\-]?id[\"']?\s*[:=]\s*[\"']?([0-9a-f\-]{36})", re.I
)
_ERR_NAME_RE  = re.compile(r'"name"\s*:\s*"([^"]+)"')
_ERR_MSG_RE   = re.compile(r'"message"\s*:\s*"([^"]{0,300})"')
_LEVEL_RE     = re.compile(r'level\s*:\s*(error|warn|info|debug|critical|fatal)', re.I)


def _boto3_client(region: str, env: str = "prod"):
    import boto3
    import config as _cfg
    if env == "prod" or region == "us-east-1":
        key_id = _cfg.AWS_ACCESS_KEY_ID_PROD
        secret = _cfg.AWS_SECRET_ACCESS_KEY_PROD
    else:
        key_id = _cfg.AWS_ACCESS_KEY_ID_NONPROD
        secret = _cfg.AWS_SECRET_ACCESS_KEY_NONPROD
    return boto3.client(
        "logs", region_name=region,
        aws_access_key_id=key_id,
        aws_secret_access_key=secret,
    )


def _discover_prod_group(client, kind: str) -> str | None:
    """
    Discover the right prod log group for `kind` ("ecs" or "lambda").

    Strategy:
      1. Check the hardcoded name in _LOG_GROUPS["prod"] — already verified to exist.
      2. If that's None (env override), scan ALL log groups under the matching prefix
         (/ecs/ for ECS, /aws/lambda/ for Lambda) and pick the best match using
         keyword heuristics.  Prefers groups with "prod" in the name.
    """
    prefix = "/ecs/" if kind == "ecs" else "/aws/lambda/"
    keyword_sets = _SCAN_KEYWORDS.get(kind, [])

    all_groups: list[str] = []
    try:
        paginator = client.get_paginator("describe_log_groups")
        for page in paginator.paginate(logGroupNamePrefix=prefix):
            for g in page.get("logGroups", []):
                all_groups.append(g["logGroupName"])
    except Exception:
        return None

    if not all_groups:
        return None

    # Score each group: +2 for containing "prod", +1 per matching keyword set
    def _score(name: str) -> int:
        lower = name.lower()
        score = 2 if "prod" in lower else 0
        for kws in keyword_sets:
            if all(k in lower for k in kws):
                score += 1
        return score

    candidates = [(g, _score(g)) for g in all_groups]
    best_name, best_score = max(candidates, key=lambda x: x[1])
    return best_name if best_score > 0 else None


def _run_insights_query(client, log_group: str, project_id: str, hours: int,
                        message_filter: str | None = None) -> list[dict]:
    """Run a CWI query and return parsed rows. Returns [] on any error."""
    end_time   = int(time.time())
    start_time = end_time - hours * 3600
    extra = f" and @message like /{message_filter}/" if message_filter else ""
    query = _QUERY.format(project_id=project_id, extra_filter=extra)

    try:
        resp     = client.start_query(
            logGroupName=log_group,
            startTime=start_time,
            endTime=end_time,
            queryString=query,
        )
        query_id = resp["queryId"]

        # Poll until complete (max 180s with back-off: 1s × 30, then 3s × 50)
        for tick in range(80):
            time.sleep(1 if tick < 30 else 3)
            status_resp = client.get_query_results(queryId=query_id)
            status      = status_resp.get("status", "")
            if status in ("Complete", "Failed", "Cancelled", "Timeout"):
                break

        if status != "Complete":
            raise RuntimeError(
                f"CWI query ended with status '{status}' "
                f"(log group: {log_group}, window: {hours}h)"
            )

        rows = []
        for result in status_resp.get("results", []):
            row: dict[str, str] = {}
            for field in result:
                row[field["field"]] = field["value"]
            rows.append(row)
        return rows

    except Exception:
        raise


def _parse_row(row: dict) -> dict:
    """Extract structured fields from a raw CWI result row."""
    raw = row.get("@message", "")
    ts_raw = row.get("@timestamp", "")

    # Normalise timestamp
    ts = ts_raw
    try:
        dt = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
        ts = dt.astimezone(timezone(timedelta(hours=5, minutes=30))).strftime(
            "%d %b %Y %H:%M:%S IST"
        )
    except Exception:
        pass

    import_log_id = ""
    m = _IMPORT_LOG_RE.search(raw)
    if m:
        import_log_id = m.group(1)

    error_name = ""
    m = _ERR_NAME_RE.search(raw)
    if m:
        error_name = m.group(1)

    message = ""
    m = _ERR_MSG_RE.search(raw)
    if m:
        message = m.group(1)
    if not message:
        # Fallback: take text after "message:"
        idx = raw.lower().find("message:")
        if idx >= 0:
            message = raw[idx + 8:idx + 200].strip().rstrip(";")

    level = "ERROR"
    m = _LEVEL_RE.search(raw)
    if m:
        level = m.group(1).upper()

    return {
        "ts":            ts,
        "ts_raw":        ts_raw,
        "import_log_id": import_log_id,
        "level":         level,
        "error_name":    error_name,
        "message":       message,
        "raw":           raw,
    }


def _list_all_log_groups(client) -> list[str]:
    """Return every log group name visible to the client."""
    groups: list[str] = []
    try:
        paginator = client.get_paginator("describe_log_groups")
        for page in paginator.paginate():
            for g in page.get("logGroups", []):
                groups.append(g["logGroupName"])
    except Exception:
        pass
    return groups


def collect_project_key_services(
    project_id: str,
    env: str = "prod",
    hours: int = 24,
    message_filter: str | None = None,
    max_workers: int = 8,
    progress_cb=None,
) -> dict:
    """
    Query only the key service log groups (auth, data-integration, dateblock,
    report-engine, extraction) for project_id errors/warns.
    Groups are discovered dynamically by keyword matching so the function works
    across dev / qa / perf / prod without hardcoded names.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    cfg    = _LOG_GROUPS.get(env, _LOG_GROUPS["prod"])
    region = cfg["region"]
    client = _boto3_client(region, env=env)

    all_groups   = _list_all_log_groups(client)
    key_groups   = [g for g in all_groups if _matches_key_service(g, env=env)]

    if not key_groups:
        return {
            "project_id": project_id, "env": env, "hours": hours,
            "region": region, "message_filter": message_filter,
            "log_groups_scanned": [], "errors": [], "total": 0,
            "group_hits": {}, "group_errors": {}, "key_services_mode": True,
        }

    group_hits:   dict[str, int] = {}
    group_errors: dict[str, str] = {}
    all_rows:     list[dict]     = []

    def _query_one(group: str) -> tuple[str, list[dict], str | None]:
        try:
            rows = _run_insights_query(client, group, project_id, hours, message_filter)
            parsed = []
            for r in rows:
                p = _parse_row(r)
                p["source"]    = group
                p["log_group"] = group
                parsed.append(p)
            return group, parsed, None
        except Exception as exc:
            return group, [], str(exc)

    total = len(key_groups)
    done  = 0
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_query_one, g): g for g in key_groups}
        for fut in as_completed(futures):
            group, rows, err = fut.result()
            done += 1
            if err:
                group_errors[group] = err
            else:
                group_hits[group] = len(rows)
                all_rows.extend(rows)
            if progress_cb:
                progress_cb(done, total, group)

    all_rows.sort(key=lambda r: r.get("ts_raw", ""), reverse=True)

    return {
        "project_id":         project_id,
        "env":                env,
        "hours":              hours,
        "region":             region,
        "message_filter":     message_filter,
        "log_groups_scanned": key_groups,
        "errors":             all_rows,
        "total":              len(all_rows),
        "group_hits":         group_hits,
        "group_errors":       group_errors,
        "key_services_mode":  True,
    }


def collect_project_all_groups(
    project_id: str,
    env: str = "prod",
    hours: int = 24,
    message_filter: str | None = None,
    max_workers: int = 8,
    progress_cb=None,
) -> dict:
    """
    Query EVERY log group in the region for project_id errors/warns.
    Runs up to max_workers queries in parallel (AWS limit is ~10 concurrent).
    progress_cb(done, total, group_name) is called after each group finishes.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    cfg    = _LOG_GROUPS.get(env, _LOG_GROUPS["prod"])
    region = cfg["region"]
    client = _boto3_client(region, env=env)

    all_groups = _list_all_log_groups(client)
    if not all_groups:
        return {
            "project_id": project_id, "env": env, "hours": hours,
            "region": region, "message_filter": message_filter,
            "log_groups_scanned": [], "errors": [], "total": 0,
            "group_hits": {}, "group_errors": {}, "all_groups_mode": True,
        }

    group_hits:   dict[str, int] = {}
    group_errors: dict[str, str] = {}
    all_rows:     list[dict]     = []

    def _query_one(group: str) -> tuple[str, list[dict], str | None]:
        try:
            rows = _run_insights_query(client, group, project_id, hours, message_filter)
            parsed = []
            for r in rows:
                p = _parse_row(r)
                p["source"]    = group
                p["log_group"] = group
                parsed.append(p)
            return group, parsed, None
        except Exception as exc:
            return group, [], str(exc)

    total = len(all_groups)
    done  = 0
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_query_one, g): g for g in all_groups}
        for fut in as_completed(futures):
            group, rows, err = fut.result()
            done += 1
            if err:
                group_errors[group] = err
            else:
                group_hits[group] = len(rows)
                all_rows.extend(rows)
            if progress_cb:
                progress_cb(done, total, group)

    all_rows.sort(key=lambda r: r.get("ts_raw", ""), reverse=True)

    return {
        "project_id":       project_id,
        "env":              env,
        "hours":            hours,
        "region":           region,
        "message_filter":   message_filter,
        "log_groups_scanned": all_groups,
        "errors":           all_rows,
        "total":            len(all_rows),
        "group_hits":       group_hits,
        "group_errors":     group_errors,
        "all_groups_mode":  True,
    }


def collect_project(project_id: str, env: str = "prod", hours: int = 24,
                    message_filter: str | None = None) -> dict:
    """
    Fetch all error + warn log lines for *project_id* from ECS + Lambda log groups.

    If the log group names for the environment aren't hardcoded, automatically
    scans all log groups in the region and picks the best match — so it always
    queries something rather than failing with an "unknown groups" state.
    """
    cfg    = _LOG_GROUPS.get(env, _LOG_GROUPS["prod"])
    region = cfg["region"]
    client = _boto3_client(region, env=env)

    # Use hardcoded group names; fall back to auto-discovery for any that are None
    ecs_group    = cfg["ecs"]
    lambda_group = cfg["lambda"]
    unknown_groups = False

    if ecs_group is None:
        ecs_group = _discover_prod_group(client, "ecs")
    if lambda_group is None:
        lambda_group = _discover_prod_group(client, "lambda")
    if ecs_group is None or lambda_group is None:
        unknown_groups = True

    group_errors: dict[str, str] = {}
    all_rows: list[dict] = []

    for kind, group in [("ecs", ecs_group), ("lambda", lambda_group)]:
        if not group:
            continue
        try:
            raw_rows = _run_insights_query(client, group, project_id, hours, message_filter)
            for r in raw_rows:
                parsed = _parse_row(r)
                parsed["source"] = kind.upper()
                parsed["log_group"] = group
                all_rows.append(parsed)
        except Exception as exc:
            group_errors[group] = str(exc)

    # Sort merged rows newest-first
    all_rows.sort(key=lambda r: r.get("ts_raw", ""), reverse=True)

    return {
        "project_id":     project_id,
        "env":            env,
        "hours":          hours,
        "region":         region,
        "message_filter": message_filter,
        "log_groups":     {"ecs": ecs_group, "lambda": lambda_group},
        "errors":         all_rows,
        "total":          len(all_rows),
        "unknown_groups": unknown_groups,
        "group_errors":   group_errors,
    }
