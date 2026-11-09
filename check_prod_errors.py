"""
check_prod_errors.py
────────────────────
Fetches and ranks the top 10 errors/warnings from the last 1 hour
across Auth, Integration, Report Engine, and Audit Listener in prod.

Usage:
  python check_prod_errors.py
"""
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

import boto3
import config

SERVICES = {
    "Auth":           "/ecs/ciq-prod-useast1-task-authentication",
    "Integration":    "/ecs/ciq-prod-useast1-data-integration-job",
    "Report Engine":  "/ecs/ciq-prod-useast1-task-report-engine",
    "Audit Listener": "/ecs/ciq-prod-useast1-task-audit_event_listener",
}

FILTER = "?ERROR ?WARN ?CRITICAL ?EXCEPTION ?FATAL"

# Strip timestamps, UUIDs, line numbers so similar errors cluster together
NORMALISE_RE = re.compile(
    r"\b(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[^\s]*)\b"  # timestamps
    r"|\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"  # UUIDs
    r"|\b\d{5,}\b"          # long numbers (IDs, line numbers)
    r"|at line \d+"            # stack-trace line refs
, re.IGNORECASE)


def normalise(msg: str) -> str:
    msg = NORMALISE_RE.sub("<N>", msg)
    return msg[:200].strip()


def fetch(cw, log_group: str, start_ms: int, end_ms: int) -> list[dict]:
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


def main():
    cw = boto3.client(
        "logs",
        region_name="us-east-1",
        aws_access_key_id=config.AWS_ACCESS_KEY_ID_PROD,
        aws_secret_access_key=config.AWS_SECRET_ACCESS_KEY_PROD,
    )

    now = datetime.now(tz=timezone.utc)
    end_ms = int(now.timestamp() * 1000)
    start_ms = int((now - timedelta(hours=1)).timestamp() * 1000)

    # Collect events per service
    counts: Counter = Counter()
    latest: dict[str, str] = {}
    service_hits: dict[str, set] = defaultdict(set)
    total_per_service: dict[str, int] = {}

    for svc, group in SERVICES.items():
        print(f"  Fetching {svc}...", end=" ", flush=True)
        try:
            events = fetch(cw, group, start_ms, end_ms)
            total_per_service[svc] = len(events)
            print(f"{len(events)} events")
            for ev in events:
                key = normalise(ev.get("message", ""))
                counts[key] += 1
                ts = datetime.fromtimestamp(ev["timestamp"] / 1000, tz=timezone.utc).strftime("%H:%M:%S")
                if key not in latest or ts > latest[key]:
                    latest[key] = ts
                service_hits[key].add(svc)
        except Exception as exc:
            print(f"FAILED — {exc}")
            total_per_service[svc] = -1

    print()
    print(f"{'Rank':<5} {'Count':>6}  {'Last seen':>9}  {'Services':<32}  Error")
    print("-" * 110)
    for rank, (msg, count) in enumerate(counts.most_common(10), 1):
        svcs = ", ".join(sorted(service_hits[msg]))
        last = latest.get(msg, "?")
        preview = msg[:80].replace("\n", " ")
        print(f"{rank:<5} {count:>6}  {last:>9}  {svcs:<32}  {preview}")

    print()
    print("Events fetched per service (last 1 hr):")
    for svc, n in total_per_service.items():
        status = str(n) if n >= 0 else "ERROR"
        print(f"  {svc:<18} {status}")


if __name__ == "__main__":
    print(f"Fetching last 1 hour of errors from prod (us-east-1)...")
    print(f"Services: {', '.join(SERVICES)}")
    print()
    main()
