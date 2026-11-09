"""
collectors/api_collector.py
Probes ConstructivIQ API endpoints and collects error / health data.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional
import requests
import config


@dataclass
class ApiProbeResult:
    url: str
    status_code: int
    ok: bool
    latency_ms: float
    body_snippet: str
    error: Optional[str] = None
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat() + "Z"


def _headers() -> dict:
    h = {"Accept": "application/json"}
    if config.API_AUTH_TOKEN:
        h["Authorization"] = f"Bearer {config.API_AUTH_TOKEN}"
    return h


def probe_url(url: str, method: str = "GET", payload: Any = None) -> ApiProbeResult:
    """Send a single HTTP request and return a structured result."""
    start = datetime.utcnow()
    try:
        resp = requests.request(method, url, headers=_headers(), json=payload, timeout=15, allow_redirects=True)
        latency = (datetime.utcnow() - start).total_seconds() * 1000
        return ApiProbeResult(url=url, status_code=resp.status_code, ok=resp.ok,
                              latency_ms=round(latency, 1), body_snippet=resp.text[:500])
    except requests.exceptions.ConnectionError as e:
        latency = (datetime.utcnow() - start).total_seconds() * 1000
        return ApiProbeResult(url=url, status_code=0, ok=False, latency_ms=round(latency, 1),
                              body_snippet="", error=str(e))
    except requests.exceptions.Timeout:
        latency = (datetime.utcnow() - start).total_seconds() * 1000
        return ApiProbeResult(url=url, status_code=0, ok=False, latency_ms=round(latency, 1),
                              body_snippet="", error="Request timed out")
    except Exception as e:
        latency = (datetime.utcnow() - start).total_seconds() * 1000
        return ApiProbeResult(url=url, status_code=0, ok=False, latency_ms=round(latency, 1),
                              body_snippet="", error=str(e))


def probe_standard_endpoints(base_url: str | None = None) -> list[ApiProbeResult]:
    """Probe a set of well-known health / diagnostic endpoints."""
    base = (base_url or config.API_BASE_URL or "").rstrip("/")
    if not base:
        return []
    paths = ["/health", "/healthz", "/ready", "/api/health", "/api/status", "/api/v1/health", "/ping"]
    results = []
    for path in paths:
        result = probe_url(f"{base}{path}")
        results.append(result)
        if result.ok:
            break
    return results


def fetch_recent_errors(base_url: str | None = None, limit: int = 50) -> list[dict]:
    """Attempt to fetch recent errors from a known errors endpoint."""
    base = (base_url or config.API_BASE_URL or "").rstrip("/")
    if not base:
        return []
    for path in [f"/api/errors?limit={limit}", f"/api/logs/errors?limit={limit}", f"/api/v1/errors?limit={limit}"]:
        result = probe_url(f"{base}{path}")
        if result.ok and result.body_snippet:
            try:
                import json
                data = json.loads(result.body_snippet)
                if isinstance(data, list):
                    return data[:limit]
                if isinstance(data, dict) and "errors" in data:
                    return data["errors"][:limit]
            except Exception:
                pass
    return []
