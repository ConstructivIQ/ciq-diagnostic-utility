"""
collectors/waste_collector.py
──────────────────────────────
Identifies unused / idle AWS resources by cross-referencing the infra
inventory with CloudWatch utilisation metrics.

All CloudWatch GetMetricStatistics calls for standard AWS metrics are FREE
(AWS does not charge for reading built-in service metrics).

Checks performed (14-day look-back by default):
  • RDS:          zero DatabaseConnections → idle or explicitly stopped
  • EC2:          stopped state OR avg CPUUtilisation < 2 %
  • Lambda:       zero Invocations (CloudWatch doesn't emit 0-values for Lambda
                  so None == confirmed zero usage)
  • ELB (ALB):    zero RequestCount; state ≠ active → stopped
  • ELB (NLB):    zero ActiveFlowCount
  • ElastiCache:  avg CurrConnections < 1 OR status ≠ available
  • ECS:          desiredCount == 0 (explicitly scaled to zero)
  • S3:           bucket has zero objects (list_objects_v2 MaxKeys=1)

Returns:
  {
    "env":          str,
    "account":      str,
    "region":       str,
    "days_checked": int,
    "collected_at": str (ISO),
    "total":        int,
    "findings": [
      {
        "resource_type": str,   # "RDS" | "EC2" | "Lambda" | "ELB" | "ElastiCache" | "ECS" | "S3"
        "resource_id":   str,
        "name":          str,   # human-readable name (may equal resource_id)
        "reason":        str,   # plain-English explanation
        "metric":        str | None,
        "metric_value":  float | None,
        "age_days":      float | None,
        "class":         str,   # instance/node type, runtime, etc.
        "severity":      str,   # "stopped" | "idle" | "empty" | "no-data" | "error"
        "cost_hint":     str,   # rough cost guidance ("high" | "medium" | "low" | "free")
      }, …
    ]
  }
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import boto3


# ── CloudWatch helpers ────────────────────────────────────────────────────────

def _cw_sum(cw, namespace: str, metric: str, dimensions: list[dict],
            days: int, period: int = 86400) -> float | None:
    """
    Sum of a metric over the last `days` days using `period`-second buckets.
    Returns the total (may be 0.0), or None if no datapoints came back.
    None usually means the metric was never emitted (e.g. Lambda Invocations
    with zero calls, or basic monitoring disabled).
    """
    end   = datetime.now(tz=timezone.utc)
    start = end - timedelta(days=days)
    try:
        resp = cw.get_metric_statistics(
            Namespace=namespace,
            MetricName=metric,
            Dimensions=dimensions,
            StartTime=start,
            EndTime=end,
            Period=period,
            Statistics=["Sum"],
        )
        pts = resp.get("Datapoints", [])
        if not pts:
            return None
        return sum(p["Sum"] for p in pts)
    except Exception:
        return None


def _cw_avg(cw, namespace: str, metric: str, dimensions: list[dict],
            days: int, period: int = 86400) -> float | None:
    """
    Average of a metric over the last `days` days.
    Returns the mean of all datapoint averages, or None if no data.
    """
    end   = datetime.now(tz=timezone.utc)
    start = end - timedelta(days=days)
    try:
        resp = cw.get_metric_statistics(
            Namespace=namespace,
            MetricName=metric,
            Dimensions=dimensions,
            StartTime=start,
            EndTime=end,
            Period=period,
            Statistics=["Average"],
        )
        pts = resp.get("Datapoints", [])
        if not pts:
            return None
        return sum(p["Average"] for p in pts) / len(pts)
    except Exception:
        return None


# ── Cost hint lookup ──────────────────────────────────────────────────────────

_HIGH_COST_RDS_FAMILIES   = ("r5", "r6g", "r6i", "r7g", "x1", "x2", "m5", "m6")
_HIGH_COST_EC2_FAMILIES   = ("m5", "m6", "c5", "c6", "r5", "r6", "x1", "p3")
_HIGH_COST_CACHE_FAMILIES = ("r5", "r6g", "r7g", "m6g")

def _rds_cost_hint(cls: str) -> str:
    if any(cls.startswith(f"db.{f}") for f in _HIGH_COST_RDS_FAMILIES):
        return "high"
    return "medium"

def _ec2_cost_hint(itype: str) -> str:
    if any(itype.startswith(f) for f in _HIGH_COST_EC2_FAMILIES):
        return "high"
    return "medium"

def _cache_cost_hint(ntype: str) -> str:
    if any(ntype.startswith(f"cache.{f}") for f in _HIGH_COST_CACHE_FAMILIES):
        return "high"
    return "medium"


# ── Session builder (mirrors infra_collector) ─────────────────────────────────

def _session(account: str, region: str) -> boto3.Session:
    slug   = account.upper().replace("-", "_")
    key    = os.environ.get(f"{slug}_AWS_ACCESS_KEY_ID")    or os.environ.get("AWS_ACCESS_KEY_ID")
    secret = os.environ.get(f"{slug}_AWS_SECRET_ACCESS_KEY") or os.environ.get("AWS_SECRET_ACCESS_KEY")
    token  = os.environ.get(f"{slug}_AWS_SESSION_TOKEN")    or os.environ.get("AWS_SESSION_TOKEN")
    return boto3.Session(
        aws_access_key_id=key,
        aws_secret_access_key=secret,
        aws_session_token=token,
        region_name=region,
    )


# ── Per-service check functions ───────────────────────────────────────────────

def _check_rds(cw, services: dict, days: int) -> list[dict]:
    findings = []
    for r in services.get("rds", []):
        if "_error" in r:
            continue
        rid = r.get("id", "")

        if r.get("status") == "stopped":
            findings.append(dict(
                resource_type="RDS", resource_id=rid, name=rid,
                reason="Instance is stopped",
                metric=None, metric_value=None,
                age_days=r.get("age_days"), class_=r.get("class", ""),
                severity="stopped", cost_hint=_rds_cost_hint(r.get("class", "")),
            ))
            continue

        val = _cw_sum(cw, "AWS/RDS", "DatabaseConnections",
                      [{"Name": "DBInstanceIdentifier", "Value": rid}], days)
        if val == 0:
            findings.append(dict(
                resource_type="RDS", resource_id=rid, name=rid,
                reason=f"Zero DB connections in the last {days} days",
                metric="DatabaseConnections", metric_value=0.0,
                age_days=r.get("age_days"), class_=r.get("class", ""),
                severity="idle", cost_hint=_rds_cost_hint(r.get("class", "")),
            ))
        elif val is None:
            findings.append(dict(
                resource_type="RDS", resource_id=rid, name=rid,
                reason=f"No CloudWatch connection metric in the last {days} days (monitoring may be off)",
                metric="DatabaseConnections", metric_value=None,
                age_days=r.get("age_days"), class_=r.get("class", ""),
                severity="no-data", cost_hint=_rds_cost_hint(r.get("class", "")),
            ))
    return findings


def _check_ec2(cw, services: dict, days: int) -> list[dict]:
    findings = []
    for r in services.get("ec2", []):
        if "_error" in r:
            continue
        iid   = r.get("id", "")
        name  = r.get("name", iid)
        itype = r.get("type", "")

        if r.get("state") == "stopped":
            findings.append(dict(
                resource_type="EC2", resource_id=iid, name=name,
                reason="Instance is stopped (EBS cost still accruing)",
                metric=None, metric_value=None,
                age_days=r.get("age_days"), class_=itype,
                severity="stopped", cost_hint=_ec2_cost_hint(itype),
            ))
            continue

        avg_cpu = _cw_avg(cw, "AWS/EC2", "CPUUtilization",
                          [{"Name": "InstanceId", "Value": iid}], days)
        if avg_cpu is not None and avg_cpu < 2.0:
            findings.append(dict(
                resource_type="EC2", resource_id=iid, name=name,
                reason=f"Avg CPU {avg_cpu:.2f}% over last {days} days — likely idle",
                metric="CPUUtilization", metric_value=round(avg_cpu, 3),
                age_days=r.get("age_days"), class_=itype,
                severity="idle", cost_hint=_ec2_cost_hint(itype),
            ))
    return findings


def _check_lambda(cw, services: dict, days: int) -> list[dict]:
    findings = []
    for r in services.get("lambda", []):
        if "_error" in r:
            continue
        name = r.get("name", "")

        # Lambda Invocations metric is only emitted on actual invocations,
        # so None === confirmed zero invocations (not a missing-monitoring issue).
        val = _cw_sum(cw, "AWS/Lambda", "Invocations",
                      [{"Name": "FunctionName", "Value": name}], days)
        if val is None or val == 0:
            findings.append(dict(
                resource_type="Lambda", resource_id=name, name=name,
                reason=f"Zero invocations in the last {days} days",
                metric="Invocations", metric_value=0.0,
                age_days=r.get("age_days"), class_=r.get("runtime", ""),
                severity="idle", cost_hint="free",  # Lambda is pay-per-invoke; idle = $0
            ))
    return findings


def _check_elb(cw, services: dict, days: int) -> list[dict]:
    findings = []
    for r in services.get("elb", []):
        if "_error" in r:
            continue
        name     = r.get("name", "")
        arn      = r.get("arn", "")
        lb_type  = r.get("type", "")

        if r.get("state") != "active":
            findings.append(dict(
                resource_type="ELB", resource_id=name, name=name,
                reason=f"Load balancer state is '{r.get('state')}' (not active)",
                metric=None, metric_value=None,
                age_days=r.get("age_days"), class_=lb_type,
                severity="stopped", cost_hint="medium",
            ))
            continue

        # ARN format: arn:aws:elasticloadbalancing:region:account:loadbalancer/app/name/id
        # CloudWatch dimension wants the suffix after "loadbalancer/" → "app/name/id"
        lb_suffix = ""
        if arn:
            parts = arn.split("loadbalancer/")
            lb_suffix = parts[1] if len(parts) > 1 else ""

        if lb_type == "application":
            namespace, metric = "AWS/ApplicationELB", "RequestCount"
        elif lb_type == "network":
            namespace, metric = "AWS/NetworkELB", "ActiveFlowCount"
        else:
            continue

        val = _cw_sum(cw, namespace, metric,
                      [{"Name": "LoadBalancer", "Value": lb_suffix}], days)
        if val == 0 or val is None:
            findings.append(dict(
                resource_type="ELB", resource_id=name, name=name,
                reason=f"Zero {metric} in the last {days} days",
                metric=metric, metric_value=val or 0.0,
                age_days=r.get("age_days"), class_=lb_type,
                severity="idle", cost_hint="medium",  # ALB baseline ~$16-25/month
            ))
    return findings


def _check_elasticache(cw, services: dict, days: int) -> list[dict]:
    findings = []
    for r in services.get("elasticache", []):
        if "_error" in r:
            continue
        cid   = r.get("id", "")
        ntype = r.get("node_type", "")

        if r.get("status") not in ("available", None, ""):
            findings.append(dict(
                resource_type="ElastiCache", resource_id=cid, name=cid,
                reason=f"Cluster status is '{r.get('status')}'",
                metric=None, metric_value=None,
                age_days=r.get("age_days"), class_=ntype,
                severity="stopped", cost_hint=_cache_cost_hint(ntype),
            ))
            continue

        val = _cw_avg(cw, "AWS/ElastiCache", "CurrConnections",
                      [{"Name": "CacheClusterId", "Value": cid}], days)
        if val is not None and val < 1.0:
            findings.append(dict(
                resource_type="ElastiCache", resource_id=cid, name=cid,
                reason=f"Avg connections {val:.2f} over last {days} days — likely unused",
                metric="CurrConnections", metric_value=round(val, 3),
                age_days=r.get("age_days"), class_=ntype,
                severity="idle", cost_hint=_cache_cost_hint(ntype),
            ))
    return findings


def _check_ecs(services: dict) -> list[dict]:
    findings = []
    for r in services.get("ecs", []):
        if "_error" in r:
            continue
        if r.get("desired", 1) == 0:
            findings.append(dict(
                resource_type="ECS", resource_id=r.get("name", ""), name=r.get("name", ""),
                reason="Service desired count is 0 (explicitly scaled to zero)",
                metric=None, metric_value=None,
                age_days=r.get("age_days"), class_=r.get("cluster", ""),
                severity="stopped", cost_hint="low",  # ECS tasks stopped = no compute cost
            ))
    return findings


def _check_s3(s3_client, services: dict) -> list[dict]:
    findings = []
    for r in services.get("s3", []):
        if "_error" in r:
            continue
        bname = r.get("name", "")
        try:
            resp = s3_client.list_objects_v2(Bucket=bname, MaxKeys=1)
            if resp.get("KeyCount", 0) == 0:
                findings.append(dict(
                    resource_type="S3", resource_id=bname, name=bname,
                    reason="Bucket is empty (zero objects)",
                    metric=None, metric_value=None,
                    age_days=r.get("age_days"), class_="bucket",
                    severity="empty", cost_hint="free",  # Empty bucket = $0
                ))
        except Exception as exc:
            findings.append(dict(
                resource_type="S3", resource_id=bname, name=bname,
                reason=f"Could not check bucket contents: {exc}",
                metric=None, metric_value=None,
                age_days=r.get("age_days"), class_="bucket",
                severity="error", cost_hint="unknown",
            ))
    return findings


# ── Public entry point ────────────────────────────────────────────────────────

# Severity sort order (most actionable first)
_SEV_ORDER = {"stopped": 0, "idle": 1, "empty": 2, "no-data": 3, "error": 4, "unknown": 5}
_COST_ORDER = {"high": 0, "medium": 1, "low": 2, "free": 3, "unknown": 4}


def collect_waste(infra_data: dict, days: int = 14) -> dict:
    """
    Given infra_data from collect_infra(), check CloudWatch metrics to
    identify unused / idle resources.

    Args:
        infra_data:  Dict returned by collectors.infra_collector.collect_infra().
        days:        Look-back window in days for CloudWatch queries (default 14).

    Returns:
        Structured dict with a 'findings' list — see module docstring for schema.
    """
    account  = infra_data.get("account", "prod")
    region   = infra_data.get("region",  "us-east-1")
    env      = infra_data.get("env",     "prod")
    services = infra_data.get("services", {})

    sess      = _session(account, region)
    cw        = sess.client("cloudwatch")
    s3_client = sess.client("s3")

    raw_findings: list[dict] = []
    raw_findings += _check_rds(cw, services, days)
    raw_findings += _check_ec2(cw, services, days)
    raw_findings += _check_lambda(cw, services, days)
    raw_findings += _check_elb(cw, services, days)
    raw_findings += _check_elasticache(cw, services, days)
    raw_findings += _check_ecs(services)
    raw_findings += _check_s3(s3_client, services)

    # Normalise key name (internal used class_ to avoid Python keyword clash)
    findings: list[dict] = []
    for f in raw_findings:
        findings.append({
            "resource_type": f["resource_type"],
            "resource_id":   f["resource_id"],
            "name":          f.get("name", f["resource_id"]),
            "reason":        f["reason"],
            "metric":        f.get("metric"),
            "metric_value":  f.get("metric_value"),
            "age_days":      f.get("age_days"),
            "class":         f.get("class_", ""),
            "severity":      f.get("severity", "unknown"),
            "cost_hint":     f.get("cost_hint", "unknown"),
        })

    # Sort: by severity tier first, then by cost impact descending, then by age
    findings.sort(key=lambda x: (
        _SEV_ORDER.get(x["severity"], 99),
        _COST_ORDER.get(x["cost_hint"], 99),
        -(x.get("age_days") or 0),
    ))

    return {
        "env":          env,
        "account":      account,
        "region":       region,
        "days_checked": days,
        "collected_at": datetime.now(tz=timezone.utc).isoformat(),
        "total":        len(findings),
        "findings":     findings,
    }
