"""
Synthetic demo data for running the diagnostic utility without real credentials.
Run: python diagnose.py --demo
"""
from dataclasses import dataclass, field
from typing import Optional


JIRA_ISSUE = {
    "key": "CIQ-4891",
    "summary": "Dashboard fails to load for enterprise customers after 18:00 UTC",
    "status": "In Progress",
    "priority": "High",
    "issue_type": "Bug",
    "reporter": "Sarah Mitchell",
    "assignee": "Dev Team",
    "created": "2026-08-23T09:12:00.000+0000",
    "updated": "2026-08-24T07:45:00.000+0000",
    "labels": ["prod-incident", "enterprise", "dashboard"],
    "components": ["Dashboard Service", "Auth Gateway"],
    "url": "https://constructiviq.atlassian.net/browse/CIQ-4891",
    "description": (
        "Enterprise customers (Tier 1 and Tier 2) are reporting that the main dashboard "
        "fails to load after approximately 18:00 UTC each day. The page spins indefinitely "
        "and then shows a generic 'Something went wrong' error.\n\n"
        "Affected customers: Acme Corp, GlobalDyn, NovaTech\n"
        "First reported: 2026-08-22\n"
        "Frequency: Every day since 2026-08-20 (post-deploy of v2.14.1)"
    ),
    "comments": [
        {
            "author": "Sarah Mitchell",
            "created": "2026-08-23T09:15:00.000+0000",
            "body": "Confirmed by CS team. Multiple enterprise accounts affected. Seems to be time-based.",
        },
        {
            "author": "James Okafor",
            "created": "2026-08-23T11:30:00.000+0000",
            "body": (
                "Looked at the auth gateway logs. Seeing 'JWT validation timeout' errors around 18:00 UTC. "
                "Could be related to the token refresh cron job introduced in v2.14.1."
            ),
        },
        {
            "author": "Priya Sharma",
            "created": "2026-08-24T07:40:00.000+0000",
            "body": "Redis cache is also showing high memory usage around that time. Possible eviction cascade?",
        },
    ],
}


@dataclass
class _LogEntry:
    timestamp: Optional[str]
    level: str
    message: str
    source_file: str
    line_number: int
    raw_lines: list = field(default_factory=list)


LOG_ENTRIES = [
    _LogEntry(
        timestamp="2026-08-23T18:00:14.877Z", level="CRITICAL",
        message="Circuit breaker OPEN: DashboardDataService -> downstream service unhealthy\nConsecutive failures: 10  Threshold: 10\n  at CircuitBreaker.trip (infra/circuit_breaker.py:77)",
        source_file="/var/log/constructiviq/app.log", line_number=5302,
    ),
    _LogEntry(
        timestamp="2026-08-23T18:00:12.441Z", level="ERROR",
        message="JWTValidationError: Token verification timed out after 5000ms\n  at AuthGateway.validateToken (auth/gateway.py:234)\n  at DashboardController.load (dashboard/controller.py:88)",
        source_file="/var/log/constructiviq/auth.log", line_number=1847,
    ),
    _LogEntry(
        timestamp="2026-08-23T18:00:13.002Z", level="ERROR",
        message="RedisTimeoutError: GETEX command timed out (key=session:enterprise:*)\n  at CacheLayer.get (cache/redis.py:112)",
        source_file="/var/log/constructiviq/app.log", line_number=5291,
    ),
    _LogEntry(
        timestamp="2026-08-23T18:00:14.910Z", level="ERROR",
        message="HTTP 503 returned to client: Dashboard load failed - service unavailable",
        source_file="/var/log/constructiviq/access.log", line_number=22011,
    ),
    _LogEntry(
        timestamp="2026-08-23T18:01:00.850Z", level="ERROR",
        message="Cron job 'token-refresh' failed to acquire lock after 30s. Another instance may be running. Aborting.",
        source_file="/var/log/constructiviq/cron.log", line_number=451,
    ),
    _LogEntry(
        timestamp="2026-08-23T17:59:58.003Z", level="WARNING",
        message="Redis memory usage at 89% (7.1GB / 8GB). High eviction rate detected: 2400 keys/sec.",
        source_file="/var/log/constructiviq/redis.log", line_number=6103,
    ),
    _LogEntry(
        timestamp="2026-08-23T18:01:00.120Z", level="WARNING",
        message="Token refresh cron job started - acquiring distributed lock on Redis",
        source_file="/var/log/constructiviq/cron.log", line_number=442,
    ),
]


@dataclass
class _ApiResult:
    url: str
    status_code: int
    ok: bool
    latency_ms: float
    body_snippet: str
    error: Optional[str] = None
    timestamp: str = "2026-08-24T08:00:00Z"


API_RESULTS = [
    _ApiResult(
        url="https://api.constructiviq.com/health", status_code=200, ok=True,
        latency_ms=42.1, body_snippet='{"status":"ok","version":"2.14.1"}',
    ),
    _ApiResult(
        url="https://api.constructiviq.com/api/v1/dashboard/health", status_code=503, ok=False,
        latency_ms=5021.0, body_snippet='{"error":"circuit_breaker_open","message":"DashboardDataService is unavailable"}',
    ),
    _ApiResult(
        url="https://api.constructiviq.com/api/v1/auth/health", status_code=200, ok=True,
        latency_ms=3980.5, body_snippet='{"status":"degraded","warning":"JWT validation latency high (3950ms avg)"}',
    ),
]


@dataclass
class _Email:
    uid: str
    subject: str
    sender: str
    date: str
    body: str
    has_attachments: bool = False


EMAIL_MESSAGES = [
    _Email(
        uid="10041", subject="Dashboard not loading - urgent",
        sender="admin@acmecorp.com", date="Sat, 23 Aug 2026 18:45:00 +0000",
        body="Hi Support,\n\nOur entire team has been unable to load the ConstructivIQ dashboard since about 6pm today. We see a spinner and then 'Something went wrong'.\n\nThis is blocking our end-of-day reporting. Please escalate urgently.\n\nBest,\nTom @ Acme Corp",
    ),
    _Email(
        uid="10042", subject="Re: Dashboard not loading - urgent",
        sender="support@constructiviq.com", date="Sat, 23 Aug 2026 19:10:00 +0000",
        body="Hi Tom,\n\nThank you for reaching out. We are aware of the issue and our engineering team is actively investigating. We will provide an update within 30 minutes.\n\nConstructivIQ Support",
    ),
    _Email(
        uid="10047", subject="CIQ dashboard broken again",
        sender="it@globalDyn.io", date="Sat, 23 Aug 2026 18:52:00 +0000",
        body="Second night in a row. Dashboard completely broken after 6pm UTC. Started happening after your last update. We need a hotfix or rollback ASAP.",
    ),
]
