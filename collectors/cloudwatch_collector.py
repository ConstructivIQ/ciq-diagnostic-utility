"""
collectors/cloudwatch_collector.py
────────────────────────────────────
Fetches log events from AWS CloudWatch Logs and returns LogEntry objects
compatible with the rest of the diagnostic pipeline.

Account selection is automatic:
  dev / qa / perf / demo  →  non-prod account (us-east-2 / us-east-1)
  prod                    →  prod account
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Optional

import boto3
import config
from collectors.log_collector import LogEntry

# ── Environment → account + region mapping ────────────────────────────────────
# Each entry: (account_name, default_region)
ENV_ACCOUNT: dict[str, tuple[str, str]] = {
    "dev":  ("nonprod", "us-east-2"),
    "qa":   ("nonprod", "us-east-2"),
    "perf": ("nonprod", "us-east-2"),
    "demo": ("nonprod", "us-east-1"),
    "prod": ("prod",    "us-east-1"),
}

# ── CloudWatch filter — pull errors/warnings only ─────────────────────────────
CW_FILTER = "?ERROR ?error ?WARN ?warn ?warning ?CRITICAL ?critical ?EXCEPTION ?exception ?FATAL ?fatal"

LEVEL_RE = re.compile(
    r"\b(CRITICAL|FATAL|ERROR|WARN(?:ING)?|EXCEPTION)\b", re.IGNORECASE
)
PRIORITY = {
    "CRITICAL": 0, "FATAL": 0,
    "ERROR": 1, "EXCEPTION": 1,
    "WARNING": 2, "WARN": 2,
}


def _credentials(account: str) -> tuple[str, str]:
    """Return (access_key_id, secret_access_key) for the given account name."""
    if account == "prod":
        return (
            config.AWS_ACCESS_KEY_ID_PROD or config.AWS_ACCESS_KEY_ID,
            config.AWS_SECRET_ACCESS_KEY_PROD or config.AWS_SECRET_ACCESS_KEY,
        )
    return (
        config.AWS_ACCESS_KEY_ID_NONPROD or config.AWS_ACCESS_KEY_ID,
        config.AWS_SECRET_ACCESS_KEY_NONPROD or config.AWS_SECRET_ACCESS_KEY,
    )


def _resolve(env: str, region_override: Optional[str]) -> tuple[str, str]:
    """Return (account_name, effective_region) for an environment name."""
    account, default_region = ENV_ACCOUNT.get(env.lower(), ("nonprod", "us-east-2"))
    # Per-account region config can override the default
    if region_override:
        region = region_override
    elif account == "prod":
        region = config.AWS_REGION_PROD or default_region
    else:
        region = config.AWS_REGION_NONPROD or default_region
    return account, region


def _client(account: str, region: str):
    key_id, secret = _credentials(account)
    return boto3.client(
        "logs",
        region_name=region,
        aws_access_key_id=key_id or None,
        aws_secret_access_key=secret or None,
    )


def _ms_to_iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S.%f"
    )[:-3] + "Z"


def _extract_level(message: str) -> str:
    m = LEVEL_RE.search(message)
    if not m:
        return "INFO"
    word = m.group(1).upper()
    return "WARNING" if word in ("WARN", "WARNING") else word


def collect(
    log_group: str,
    env: str = "dev",
    region: Optional[str] = None,
    log_stream: Optional[str] = None,
    since: Optional[datetime] = None,
    max_entries: int = 200,
    filter_pattern: Optional[str] = None,
) -> list[LogEntry]:
    """
    Fetch log events from a CloudWatch log group.
    Automatically selects non-prod or prod credentials based on env.
    Returns LogEntry objects sorted errors-first then by timestamp.
    """
    account, effective_region = _resolve(env, region)
    cw = _client(account, effective_region)

    end_ms = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
    if since:
        start_dt = since if since.tzinfo else since.replace(tzinfo=timezone.utc)
    else:
        start_dt = datetime.now(tz=timezone.utc) - timedelta(hours=24)
    start_ms = int(start_dt.timestamp() * 1000)

    kwargs: dict = {
        "logGroupName": log_group,
        "startTime": start_ms,
        "endTime": end_ms,
        "filterPattern": filter_pattern if filter_pattern is not None else CW_FILTER,
        "limit": min(max_entries, 10_000),
        "interleaved": True,
    }
    if log_stream:
        kwargs["logStreamNames"] = [log_stream]

    raw_events: list[dict] = []
    while len(raw_events) < max_entries:
        resp = cw.filter_log_events(**kwargs)
        raw_events.extend(resp.get("events", []))
        token = resp.get("nextToken")
        if not token:
            break
        kwargs["nextToken"] = token

    entries: list[LogEntry] = []
    for ev in raw_events[:max_entries]:
        msg = (ev.get("message") or "").rstrip()
        level = _extract_level(msg)
        entries.append(LogEntry(
            timestamp=_ms_to_iso(ev["timestamp"]),
            level=level,
            message=msg,
            source_file=ev.get("logStreamName", log_group),
            line_number=0,
            raw_lines=[msg],
        ))

    entries.sort(key=lambda e: (PRIORITY.get(e.level, 3), e.timestamp or ""))
    return entries


def list_log_groups(
    env: str = "dev",
    region: Optional[str] = None,
    prefix: str = "",
) -> list[str]:
    """List log group names in the account for the given environment."""
    account, effective_region = _resolve(env, region)
    cw = _client(account, effective_region)
    kwargs: dict = {"limit": 50}
    if prefix:
        kwargs["logGroupNamePrefix"] = prefix
    resp = cw.describe_log_groups(**kwargs)
    return [g["logGroupName"] for g in resp.get("logGroups", [])]
