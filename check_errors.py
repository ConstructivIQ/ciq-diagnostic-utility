"""
check_errors.py
───────────────
Fetch and rank top N errors/warnings from the last X hours across
Auth, Integration, Report Engine, and Audit Listener.
Optionally generates a full HTML report with Customer Issues + Environment tabs.

Usage:
  python check_errors.py --env prod --hours 1 --top 10
  python check_errors.py --env prod --hours 1 --html
  python check_errors.py --all-envs --hours 1 --html
"""
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import boto3
import click
import config
from reporters.cw_report import generate_cw_report
from collectors.infra_collector import collect_infra

# ── Log group map ─────────────────────────────────────────────────────────────
LOG_GROUPS = {
    "dev": {
        "Auth":              "/ecs/dev-ciq-auth",
        "Integration":       "/ecs/dev-ciq-dataintegration",
        "Report Engine":     "/ecs/dev-ciq-reportengine",
        "Audit Listener":    "/ecs/dev-ciq-auditlistener",
        "Date Block Engine": "/ecs/dev-ciq-dateblockengine",
        "PDF Processor":     "/ecs/dev-ciq-pdfprocessor-parent",
        "Gateway":           "/ecs/dev-ciq-gateway",
    },
    "qa": {
        "Auth":              "/ecs/qa-ciq-auth",
        "Integration":       "/ecs/qa-ciq-dataintegration",
        "Report Engine":     "/ecs/qa-ciq-reportengine",
        "Audit Listener":    "/ecs/qa-ciq-auditlistener",
        "Date Block Engine": "/ecs/qa-ciq-dateblockengine",
        "PDF Processor":     "/ecs/qa-ciq-pdfprocessor-parent",
        "Gateway":           "/ecs/qa-ciq-gateway",
    },
    "perf": {
        "Auth":              "/ecs/perf-ciq-auth",
        "Integration":       "/ecs/perf-ciq-dataintegration",
        "Report Engine":     "/ecs/perf-ciq-reportengine",
        "Audit Listener":    "/ecs/perf-ciq-auditlistener",
        "Date Block Engine": "/ecs/perf-ciq-dateblockengine",
        "PDF Processor":     "/ecs/perf-ciq-pdfprocessor-parent",
        "Gateway":           "/ecs/perf-ciq-gateway",
    },
    "prod": {
        "Auth":              "/ecs/ciq-prod-useast1-task-authentication",
        "Integration":       "/ecs/ciq-prod-useast1-data-integration-job",
        "Report Engine":     "/ecs/ciq-prod-useast1-task-report-engine",
        "Audit Listener":    "/ecs/ciq-prod-useast1-task-audit_event_listener",
        # TODO: verify these prod log group names — prod uses a different naming
        # convention from nonprod; confirm in AWS Console or with the DevOps team
        "Date Block Engine": "/ecs/ciq-prod-useast1-task-date-block-engine",
        "PDF Processor":     "/ecs/ciq-prod-pdfprocessor-parent",
        "Gateway":           "/ecs/ciq-prod-useast1-task-api_gateway",
    },
}

ENV_CONFIG = {
    "dev":   ("nonprod", "us-east-2"),
    "qa":    ("nonprod", "us-east-2"),
    "perf":  ("nonprod", "us-east-2"),
    "prod":  ("prod",    "us-east-1"),
}

FILTER = (
    "?ERROR ?error ?Error "
    "?WARN ?warn ?warning ?WARNING "
    "?CRITICAL ?critical "
    "?EXCEPTION ?exception ?Exception "
    "?FATAL ?fatal "
    "?Traceback ?traceback "
    "?stacktrace ?StackTrace"
)

SEVERITY_KEYWORDS = [
    ("FATAL",     re.compile(r'\b(fatal|FATAL)\b')),
    ("CRITICAL",  re.compile(r'\b(critical|CRITICAL)\b')),
    ("ERROR",     re.compile(r'\b(error|ERROR|Error)\b')),
    ("EXCEPTION", re.compile(r'\b(exception|EXCEPTION|Exception|Traceback|traceback|stacktrace|StackTrace)\b')),
    ("WARN",      re.compile(r'\b(warn(?:ing)?|WARN(?:ING)?|WARNING)\b')),
]

SEVERITY_COLOR = {
    "FATAL":     "\033[1;35m",
    "CRITICAL":  "\033[1;31m",
    "ERROR":     "\033[31m",
    "EXCEPTION": "\033[35m",
    "WARN":      "\033[33m",
    "?":         "\033[90m",
}
RESET = "\033[0m"

# Indian Standard Time — UTC+5:30
_IST = timezone(timedelta(hours=5, minutes=30))

# Matches the FIRST level-like token in a plain-text log line.
# In any standard log format (Spring Boot, logback, log4j, etc.) the level
# marker comes before the message body, so the first match is the real level.
_PLAIN_LEVEL_RE = re.compile(
    r'(?:^|[\s\[\|])(FATAL|CRITICAL|ERROR|EXCEPTION|WARN(?:ING)?|INFO|DEBUG|TRACE)(?=[\s\]\|:,]|$)',
    re.IGNORECASE,
)

NORMALISE_RE = re.compile(
    r"\b(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[^\s]*)\b"
    r"|\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"
    r"|\b\d{5,}\b"
    r"|at line \d+",
    re.IGNORECASE,
)

SUBSCRIPTION_FIELDS = [
    "subscriptionId", "subscription_id", "subscriptionID",
    "tenantId", "tenant_id", "tenantID",
    "orgId", "org_id", "organizationId", "organisation_id",
    "clientId", "client_id", "accountId", "account_id",
    "customerId", "customer_id",
]
CUSTOMER_NAME_FIELDS = [
    "customerName", "customer_name", "clientName", "client_name",
    "orgName", "org_name", "organizationName", "organisation_name",
    "tenantName", "tenant_name", "companyName", "company_name",
    "accountName", "account_name",
]
PROJECT_FIELDS = [
    "projectId", "project_id", "projectID",
    "workspaceId", "workspace_id",
    "appId", "app_id", "applicationId", "application_id",
    "reportId", "report_id",
]

# UUID pattern used by text-fallback regexes — only capture real UUIDs to
# avoid false positives from User-Agent strings, HTTP headers, and JSON field
# names (e.g. "AppleWebKit" matching "app", "_id" from loose word capture).
_UUID_RE = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'

_ID_IN_TEXT_RE = re.compile(
    r'\b(?:subscription|tenant|org(?:anization)?|client|customer|account)'
    r'(?:[_\s]?id)?[\s:=\'"]*(' + _UUID_RE + r')',
    re.IGNORECASE,
)
_PROJECT_IN_TEXT_RE = re.compile(
    r'\b(?:project|workspace|report)'
    r'(?:[_\s]?id)?[\s:=\'"]*(' + _UUID_RE + r')',
    re.IGNORECASE,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def normalise(msg: str) -> str:
    return NORMALISE_RE.sub("<N>", msg)[:200].strip()


def extract_severity(raw: str) -> str:
    # ── Structured JSON logs ──────────────────────────────────────────────────
    try:
        obj = json.loads(raw)
        lvl = str(obj.get("level", "")).upper()
        if lvl:
            # Trust the explicit level field — never fall through to keyword scan.
            if lvl in {"FATAL", "CRITICAL", "ERROR", "EXCEPTION"}:
                return lvl
            if lvl in {"WARN", "WARNING"}:
                return "WARN"
            return "?"   # INFO / DEBUG / TRACE — not an error
    except (json.JSONDecodeError, AttributeError):
        pass

    # ── Plain-text logs: find the level marker by position ───────────────────
    # Standard log formats (Spring Boot, logback, log4j) always put the level
    # token before the message body, so the FIRST match of a level-like word
    # is the real level — not a word in the message body.
    m = _PLAIN_LEVEL_RE.search(raw[:300])
    if m:
        lvl = m.group(1).upper()
        if lvl in {"FATAL", "CRITICAL", "ERROR", "EXCEPTION"}:
            return lvl
        if lvl in {"WARN", "WARNING"}:
            return "WARN"
        return "?"   # INFO / DEBUG / TRACE

    # ── Last resort: full-text keyword scan (truly unstructured text) ─────────
    for sev, pat in SEVERITY_KEYWORDS:
        if pat.search(raw):
            return sev
    return "?"


def extract_message(raw: str) -> str:
    try:
        obj = json.loads(raw)
        msg = obj.get("message") or obj.get("msg") or raw
        # Guard: message field may itself be a dict/list (nested JSON object).
        # Always return a plain string so callers can safely call str methods on it.
        if isinstance(msg, str):
            return msg
        return json.dumps(msg)
    except (json.JSONDecodeError, AttributeError):
        return raw


def _search_fields(obj: dict, fields: list) -> str:
    for f in fields:
        if f in obj and obj[f]:
            return str(obj[f])
    for nested in ("context", "metadata", "extra", "request", "user",
                   "ctx", "data", "payload", "properties", "attrs"):
        sub = obj.get(nested)
        if isinstance(sub, dict):
            for f in fields:
                if f in sub and sub[f]:
                    return str(sub[f])
    return ""


_UUID_FULL_RE = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
    re.IGNORECASE,
)

def _is_uuid(val: str) -> bool:
    return bool(val and _UUID_FULL_RE.match(val))


def extract_ids(raw: str, stream_name: str = "") -> tuple:
    sub_id = proj_id = ""
    try:
        obj = json.loads(raw)
        candidate = _search_fields(obj, SUBSCRIPTION_FIELDS)
        if _is_uuid(candidate):
            sub_id = candidate
        candidate = _search_fields(obj, PROJECT_FIELDS)
        if _is_uuid(candidate):
            proj_id = candidate
        msg_text = str(obj.get("message") or obj.get("msg") or "")
    except (json.JSONDecodeError, AttributeError):
        msg_text = raw

    if not sub_id:
        m = _ID_IN_TEXT_RE.search(msg_text)
        if m:
            sub_id = m.group(1)
    if not proj_id:
        m = _PROJECT_IN_TEXT_RE.search(msg_text)
        if m:
            proj_id = m.group(1)
    if stream_name and not sub_id:
        m = _ID_IN_TEXT_RE.search(stream_name)
        if m:
            sub_id = m.group(1)

    return sub_id, proj_id


def make_client(env: str):
    account, region = ENV_CONFIG[env]
    if account == "prod":
        key_id = config.AWS_ACCESS_KEY_ID_PROD
        secret = config.AWS_SECRET_ACCESS_KEY_PROD
    else:
        key_id = config.AWS_ACCESS_KEY_ID_NONPROD
        secret = config.AWS_SECRET_ACCESS_KEY_NONPROD
    return boto3.client(
        "logs", region_name=region,
        aws_access_key_id=key_id, aws_secret_access_key=secret,
    )


def fetch_events(cw, log_group: str, start_ms: int, end_ms: int) -> list:
    events, kwargs = [], {
        "logGroupName": log_group,
        "startTime": start_ms,
        "endTime": end_ms,
        "filterPattern": FILTER,
        "limit": 500,
        "interleaved": True,
    }
    while True:
        resp = cw.filter_log_events(**kwargs)
        events.extend(resp.get("events", []))
        token = resp.get("nextToken")
        if not token or len(events) >= 2000:
            break
        kwargs["nextToken"] = token
    return events


def sev_badge(sev: str, width: int = 9) -> str:
    color = SEVERITY_COLOR.get(sev, RESET)
    return f"{color}{sev:<{width}}{RESET}"


def collect_env(env: str, hours: int, severity: str) -> dict:
    """Fetch and aggregate log data for a single environment. Returns data dict."""
    cw = make_client(env)
    services = LOG_GROUPS[env]
    _, region = ENV_CONFIG[env]

    now = datetime.now(tz=timezone.utc)
    end_ms = int(now.timestamp() * 1000)
    start_ms = int((now - timedelta(hours=hours)).timestamp() * 1000)

    print(f"\n  [{env.upper()} — {region}] fetching {len(services)} services…")

    counts           = Counter()
    latest           = {}
    service_hits     = defaultdict(set)
    raw_samples      = {}
    raw_json_samples = {}   # key → raw CloudWatch message string of latest event
    raw_json_ts      = {}   # key → timestamp ms of latest stored raw_json
    severities       = {}
    totals           = {}
    sev_totals       = Counter()
    sub_hits         = defaultdict(set)
    proj_hits        = defaultdict(set)
    sub_errors       = Counter()
    proj_errors      = Counter()
    sub_latest       = {}   # sub_id  → latest event timestamp ms (epoch)
    proj_latest      = {}   # proj_id → latest event timestamp ms (epoch)
    cust_names       = {}   # sub_id → customer display name (first match wins)
    id_found         = 0
    total_events     = 0

    for svc, group in services.items():
        print(f"    {svc}…", end=" ", flush=True)
        try:
            events = fetch_events(cw, group, start_ms, end_ms)
            totals[svc] = len(events)
            total_events += len(events)
            print(f"{len(events)} events")

            for ev in events:
                raw    = (ev.get("message") or "").rstrip()
                stream = ev.get("logStreamName", "")
                sev    = extract_severity(raw)
                sev_totals[sev] += 1

                if severity != "ALL":
                    if severity == "ERROR" and sev not in ("ERROR","CRITICAL","FATAL","EXCEPTION"):
                        continue
                    elif severity not in ("ALL","ERROR") and sev != severity:
                        continue

                sub_id, proj_id = extract_ids(raw, stream)
                if sub_id or proj_id:
                    id_found += 1

                msg = extract_message(raw)
                key = normalise(msg)
                counts[key] += 1
                service_hits[key].add(svc)
                if key not in raw_samples:
                    raw_samples[key] = msg  # store full message; CSS handles display truncation
                if key not in severities:
                    severities[key] = sev

                ts_ms_ev = ev["timestamp"]
                ts = datetime.fromtimestamp(
                    ts_ms_ev / 1000, tz=timezone.utc
                ).astimezone(_IST).strftime("%d %b %Y %H:%M:%S IST")
                if key not in latest or ts > latest[key]:
                    latest[key] = ts
                # Track the raw CloudWatch string of the *latest* event per pattern
                if ts_ms_ev > raw_json_ts.get(key, 0):
                    raw_json_ts[key]      = ts_ms_ev
                    raw_json_samples[key] = raw

                if sub_id:
                    sub_hits[key].add(sub_id)
                    sub_errors[sub_id] += 1
                    ts_ms = ev["timestamp"]
                    if ts_ms > sub_latest.get(sub_id, 0):
                        sub_latest[sub_id] = ts_ms
                    # Extract customer name once per sub_id (first occurrence wins)
                    if sub_id not in cust_names:
                        try:
                            obj = json.loads(raw)
                            cname = _search_fields(obj, CUSTOMER_NAME_FIELDS)
                            if cname:
                                cust_names[sub_id] = cname
                        except (json.JSONDecodeError, AttributeError):
                            pass
                if proj_id:
                    proj_hits[key].add(proj_id)
                    proj_errors[proj_id] += 1
                    ts_ms = ev["timestamp"]
                    if ts_ms > proj_latest.get(proj_id, 0):
                        proj_latest[proj_id] = ts_ms

        except Exception as exc:
            totals[svc] = -1
            print(f"FAILED — {exc}")

    return dict(
        counts=counts, latest=latest, service_hits=service_hits,
        raw_samples=raw_samples, raw_json_samples=raw_json_samples,
        severities=severities,
        totals=totals, sev_totals=sev_totals,
        sub_hits=sub_hits, proj_hits=proj_hits,
        sub_errors=sub_errors, proj_errors=proj_errors,
        sub_latest=sub_latest, proj_latest=proj_latest,
        cust_names=cust_names,
        id_found=id_found, total_events=total_events,
    )


def print_env_table(env: str, d: dict, top: int, hours: int):
    """Print the terminal ranking table for one environment."""
    counts    = d["counts"]
    severities = d["severities"]
    raw_samples = d["raw_samples"]
    service_hits = d["service_hits"]
    latest    = d["latest"]
    sev_totals = d["sev_totals"]
    totals    = d["totals"]
    sub_hits  = d["sub_hits"]
    proj_hits = d["proj_hits"]
    sub_errors = d["sub_errors"]
    proj_errors = d["proj_errors"]
    total_events = d["total_events"]

    now = datetime.now(tz=timezone.utc)

    if not counts:
        print(f"\n  No matching events for {env.upper()}.")
        return

    W = 130
    print(f"\n{'─'*W}")
    print(f"  TOP {top} — {env.upper()} — last {hours}h  ({now.strftime('%Y-%m-%d %H:%M UTC')})")
    print(f"{'─'*W}")
    print(f"  {'#':<4} {'SEV':<11} {'Count':>6}  {'Last seen':>12}  {'Service(s)':<28}  Message")
    print(f"  {'─'*4} {'─'*9} {'─'*6}  {'─'*12}  {'─'*28}  {'─'*50}")

    for rank, (key, count) in enumerate(counts.most_common(top), 1):
        svcs  = ", ".join(sorted(service_hits.get(key, set())))
        last  = latest.get(key, "?")
        sev   = severities.get(key, "?")
        subs  = sorted(sub_hits.get(key, set()))
        projs = sorted(proj_hits.get(key, set()))
        sample = raw_samples.get(key, key).split("\n")[0][:80]
        badge  = sev_badge(sev)
        print(f"  {rank:<4} {badge} {count:>6}  {last:>12}  {svcs:<28}  {sample}")
        if subs:
            sub_str = ", ".join(subs[:5]) + (" …" if len(subs) > 5 else "")
            print(f"  {'':4} {'':9} {'':6}  {'':12}  \033[90m  subscriptions : {sub_str}{RESET}")
        if projs:
            proj_str = ", ".join(projs[:5]) + (" …" if len(projs) > 5 else "")
            print(f"  {'':4} {'':9} {'':6}  {'':12}  \033[90m  projects       : {proj_str}{RESET}")

    print(f"{'─'*W}")

    if sub_errors:
        print(f"\nMost impacted subscriptions:")
        for sid, cnt in sub_errors.most_common(10):
            bar = "█" * min(cnt // max(1, max(sub_errors.values()) // 20), 20)
            print(f"  {sid:<45} {cnt:>5}  {bar}")
    else:
        pct = int(d["id_found"] / total_events * 100) if total_events else 0
        print(f"\nNo subscription IDs extracted ({d['id_found']}/{total_events} events had IDs).")

    if proj_errors:
        print(f"\nMost impacted projects:")
        for pid, cnt in proj_errors.most_common(10):
            bar = "█" * min(cnt // max(1, max(proj_errors.values()) // 20), 20)
            print(f"  {pid:<45} {cnt:>5}  {bar}")

    print(f"\nSeverity breakdown:")
    for s in ("FATAL","CRITICAL","ERROR","EXCEPTION","WARN","?"):
        if sev_totals[s]:
            color = SEVERITY_COLOR.get(s, RESET)
            bar = "█" * min(sev_totals[s] // max(1, total_events // 40), 40)
            print(f"  {color}{s:<10}{RESET} {sev_totals[s]:>6}  {bar}")

    print(f"\nEvents per service:")
    for svc, n in totals.items():
        bar = "█" * min(n // 5, 40) if n > 0 else ""
        status = f"{n:>5}  {bar}" if n >= 0 else "  ERR"
        print(f"  {svc:<18} {status}")


# ── CLI ───────────────────────────────────────────────────────────────────────

@click.command()
@click.option("--env", "-e",
              type=click.Choice(["dev", "qa", "perf", "prod"], case_sensitive=False),
              default=None,
              help="Environment to query (omit with --all-envs for all)")
@click.option("--hours", "-h", default=1, show_default=True,
              help="Look back this many hours")
@click.option("--top", "-n", default=10, show_default=True,
              help="Number of top errors to display")
@click.option("--severity", "-s",
              type=click.Choice(["ALL", "ERROR", "WARN", "CRITICAL", "FATAL", "EXCEPTION"],
                                case_sensitive=False),
              default="ALL", show_default=True,
              help="Filter to a specific severity level")
@click.option("--html", "gen_html", is_flag=True, default=False,
              help="Generate a self-contained HTML report (Customer Issues + Environment tabs)")
@click.option("--all-envs", "all_envs", is_flag=True, default=False,
              help="Query all environments (dev, qa, perf, prod) — useful with --html")
@click.option("--infra", "gen_infra", is_flag=True, default=False,
              help="Collect AWS infrastructure inventory for the selected env (free — describe_*/list_* calls only)")
@click.option("--infra-cost", "infra_cost", is_flag=True, default=False,
              help="Include Cost Explorer data in Infra tab  ⚠️  costs $0.01 per run (AWS Cost Explorer API charge)")
def main(env, hours, top, severity, gen_html, all_envs, gen_infra, infra_cost):
    """
    Rank top errors/warnings across CIQ services and show impacted subscriptions & projects.

    \b
    Examples:
      python check_errors.py --env prod --hours 1
      python check_errors.py --env prod --hours 12 --top 20 --severity ERROR
      python check_errors.py --env prod --hours 1 --html
      python check_errors.py --all-envs --hours 1 --html
      python check_errors.py --env prod --hours 1 --html --infra
      python check_errors.py --env prod --hours 1 --html --infra --infra-cost
    """
    if all_envs:
        envs_to_query = list(LOG_GROUPS.keys())
    elif env:
        envs_to_query = [env]
    else:
        envs_to_query = ["prod"]
        if not gen_html:
            print("No --env specified, defaulting to prod. Use --all-envs for all environments.")

    env_results = {}

    for current_env in envs_to_query:
        env_results[current_env] = collect_env(current_env, hours, severity)
        if not gen_html or len(envs_to_query) == 1:
            print_env_table(current_env, env_results[current_env], top, hours)

    # ── Infra collection (always prod, free unless --infra-cost) ─────────────
    infra_data = None
    if gen_infra:
        infra_env = "prod"   # Infra tab always shows prod
        account, region = ENV_CONFIG[infra_env]
        if infra_cost:
            print(
                "\n  ⚠️  --infra-cost is set — this will call the AWS Cost Explorer API "
                "($0.01 per call). Collecting cost data…"
            )
        else:
            print(f"\n  Collecting AWS infra for {infra_env.upper()} ({account} / {region})…")
        try:
            infra_data = collect_infra(
                env=infra_env,
                account=account,
                region=region,
                include_cost=infra_cost,
            )
            total_res = sum(
                len([r for r in lst if not r.get("_error")])
                for lst in infra_data.get("services", {}).values()
            )
            print(f"  ✅ Infra collected — {total_res} resources found.")
        except Exception as exc:
            print(f"  ❌ Infra collection failed: {exc}")
            infra_data = None

    if gen_html:
        out = Path("cw_report.html")
        path = generate_cw_report(
            env_results, hours=hours, output_path=out,
            infra_data=infra_data,
        )
        print(f"\n✅ HTML report written: {path.resolve()}")
        print(f"   Open in your browser: file:///{path.resolve()}")


if __name__ == "__main__":
    main()
