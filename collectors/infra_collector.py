"""
collectors/infra_collector.py
──────────────────────────────
Discover AWS infrastructure resources for a given environment:
  ECS services/tasks, EC2 instances, RDS instances, ELB load balancers,
  ElastiCache clusters, Lambda functions, S3 buckets.

All describe_* / list_* calls are FREE.
Cost Explorer (get_cost_and_usage) costs $0.01 per API call — only
invoked when include_cost=True is explicitly passed.

Returns a dict with structure:
  {
    "env":       str,
    "account":   str,
    "region":    str,
    "collected_at": str (ISO),
    "services": {
      "ecs":          list[dict],  # {name, status, task_count, running, age_days, cluster}
      "ec2":          list[dict],  # {id, name, type, state, az, age_days}
      "rds":          list[dict],  # {id, engine, status, class, az, age_days, storage_gb}
      "elb":          list[dict],  # {name, type, scheme, state, age_days}
      "elasticache":  list[dict],  # {id, engine, status, node_type, nodes, age_days}
      "lambda":       list[dict],  # {name, runtime, memory_mb, age_days, last_modified}
      "s3":           list[dict],  # {name, age_days, region}
    },
    "cost": None | {
      "warning": str,
      "period": {"start": str, "end": str},
      "by_service": list[{"service": str, "amount": float, "unit": str}],
      "total_usd": float,
      "weekly_usd": float | None,
    }
  }
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import boto3


def _age_days(dt: datetime | None) -> float | None:
    """Return age in days from a datetime (UTC) to now, or None."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return round((datetime.now(tz=timezone.utc) - dt).total_seconds() / 86400, 1)


def _session(account: str, region: str) -> boto3.Session:
    """Build a boto3 session from env-vars for the given account slug."""
    # .env must export: PROD_AWS_ACCESS_KEY_ID / PROD_AWS_SECRET_ACCESS_KEY
    #                   NONPROD_AWS_ACCESS_KEY_ID / NONPROD_AWS_SECRET_ACCESS_KEY
    slug = account.upper().replace("-", "_")
    key    = os.environ.get(f"{slug}_AWS_ACCESS_KEY_ID")    or os.environ.get("AWS_ACCESS_KEY_ID")
    secret = os.environ.get(f"{slug}_AWS_SECRET_ACCESS_KEY") or os.environ.get("AWS_SECRET_ACCESS_KEY")
    token  = os.environ.get(f"{slug}_AWS_SESSION_TOKEN")    or os.environ.get("AWS_SESSION_TOKEN")
    return boto3.Session(
        aws_access_key_id=key,
        aws_secret_access_key=secret,
        aws_session_token=token,
        region_name=region,
    )


def _collect_ecs(boto_sess: boto3.Session, env: str) -> list[dict]:
    client = boto_sess.client("ecs")
    results: list[dict] = []
    try:
        cluster_arns = client.list_clusters().get("clusterArns", [])
        if not cluster_arns:
            return results

        for cluster_arn in cluster_arns:
            cluster_name = cluster_arn.split("/")[-1]
            # Only include clusters relevant to this env
            if env.lower() not in cluster_name.lower() and "ciq" not in cluster_name.lower():
                continue

            paginator = client.get_paginator("list_services")
            service_arns: list[str] = []
            for page in paginator.paginate(cluster=cluster_arn):
                service_arns.extend(page.get("serviceArns", []))

            if not service_arns:
                continue

            # describe in batches of 10
            for i in range(0, len(service_arns), 10):
                batch = service_arns[i:i+10]
                resp = client.describe_services(cluster=cluster_arn, services=batch)
                for svc in resp.get("services", []):
                    created = svc.get("createdAt")
                    results.append({
                        "name":        svc.get("serviceName", ""),
                        "cluster":     cluster_name,
                        "status":      svc.get("status", ""),
                        "desired":     svc.get("desiredCount", 0),
                        "running":     svc.get("runningCount", 0),
                        "pending":     svc.get("pendingCount", 0),
                        "task_def":    svc.get("taskDefinition", "").split("/")[-1],
                        "age_days":    _age_days(created),
                        "created_at":  created.isoformat() if created else None,
                    })
    except Exception as exc:
        results.append({"_error": str(exc)})
    return results


def _collect_ec2(boto_sess: boto3.Session, env: str) -> list[dict]:
    client = boto_sess.client("ec2")
    results: list[dict] = []
    try:
        paginator = client.get_paginator("describe_instances")
        for page in paginator.paginate(
            Filters=[{"Name": "instance-state-name", "Values": ["running", "stopped", "stopping"]}]
        ):
            for res in page.get("Reservations", []):
                for inst in res.get("Instances", []):
                    name = next(
                        (t["Value"] for t in inst.get("Tags", []) if t["Key"] == "Name"),
                        inst.get("InstanceId", ""),
                    )
                    # filter by env name if possible
                    if env.lower() not in name.lower() and "ciq" not in name.lower():
                        continue
                    launched = inst.get("LaunchTime")
                    results.append({
                        "id":         inst.get("InstanceId", ""),
                        "name":       name,
                        "type":       inst.get("InstanceType", ""),
                        "state":      inst.get("State", {}).get("Name", ""),
                        "az":         inst.get("Placement", {}).get("AvailabilityZone", ""),
                        "age_days":   _age_days(launched),
                        "created_at": launched.isoformat() if launched else None,
                    })
    except Exception as exc:
        results.append({"_error": str(exc)})
    return results


def _collect_rds(boto_sess: boto3.Session, env: str) -> list[dict]:
    client = boto_sess.client("rds")
    results: list[dict] = []
    try:
        paginator = client.get_paginator("describe_db_instances")
        for page in paginator.paginate():
            for inst in page.get("DBInstances", []):
                iid = inst.get("DBInstanceIdentifier", "")
                if env.lower() not in iid.lower() and "ciq" not in iid.lower():
                    continue
                created = inst.get("InstanceCreateTime")
                results.append({
                    "id":         iid,
                    "engine":     f"{inst.get('Engine','')} {inst.get('EngineVersion','')}".strip(),
                    "status":     inst.get("DBInstanceStatus", ""),
                    "class":      inst.get("DBInstanceClass", ""),
                    "az":         inst.get("AvailabilityZone", ""),
                    "storage_gb": inst.get("AllocatedStorage", 0),
                    "multi_az":   inst.get("MultiAZ", False),
                    "age_days":   _age_days(created),
                    "created_at": created.isoformat() if created else None,
                })
    except Exception as exc:
        results.append({"_error": str(exc)})
    return results


def _collect_elb(boto_sess: boto3.Session, env: str) -> list[dict]:
    client = boto_sess.client("elbv2")
    results: list[dict] = []
    try:
        paginator = client.get_paginator("describe_load_balancers")
        for page in paginator.paginate():
            for lb in page.get("LoadBalancers", []):
                name = lb.get("LoadBalancerName", "")
                if env.lower() not in name.lower() and "ciq" not in name.lower():
                    continue
                created = lb.get("CreatedTime")
                results.append({
                    "name":       name,
                    "arn":        lb.get("LoadBalancerArn", ""),
                    "type":       lb.get("Type", ""),
                    "scheme":     lb.get("Scheme", ""),
                    "state":      lb.get("State", {}).get("Code", ""),
                    "dns":        lb.get("DNSName", ""),
                    "age_days":   _age_days(created),
                    "created_at": created.isoformat() if created else None,
                })
    except Exception as exc:
        results.append({"_error": str(exc)})
    return results


def _collect_elasticache(boto_sess: boto3.Session, env: str) -> list[dict]:
    client = boto_sess.client("elasticache")
    results: list[dict] = []
    try:
        paginator = client.get_paginator("describe_cache_clusters")
        for page in paginator.paginate(ShowCacheNodeInfo=True):
            for cluster in page.get("CacheClusters", []):
                cid = cluster.get("CacheClusterId", "")
                if env.lower() not in cid.lower() and "ciq" not in cid.lower():
                    continue
                created = cluster.get("CacheClusterCreateTime")
                results.append({
                    "id":         cid,
                    "engine":     f"{cluster.get('Engine','')} {cluster.get('EngineVersion','')}".strip(),
                    "status":     cluster.get("CacheClusterStatus", ""),
                    "node_type":  cluster.get("CacheNodeType", ""),
                    "nodes":      cluster.get("NumCacheNodes", 0),
                    "az":         cluster.get("PreferredAvailabilityZone", ""),
                    "age_days":   _age_days(created),
                    "created_at": created.isoformat() if created else None,
                })
    except Exception as exc:
        results.append({"_error": str(exc)})
    return results


def _collect_lambda(boto_sess: boto3.Session, env: str) -> list[dict]:
    client = boto_sess.client("lambda")
    results: list[dict] = []
    try:
        paginator = client.get_paginator("list_functions")
        for page in paginator.paginate():
            for fn in page.get("Functions", []):
                name = fn.get("FunctionName", "")
                if env.lower() not in name.lower() and "ciq" not in name.lower():
                    continue
                mod_str = fn.get("LastModified", "")
                try:
                    mod_dt = datetime.fromisoformat(mod_str.replace("Z", "+00:00")) if mod_str else None
                except Exception:
                    mod_dt = None
                results.append({
                    "name":          name,
                    "runtime":       fn.get("Runtime", ""),
                    "memory_mb":     fn.get("MemorySize", 0),
                    "timeout_s":     fn.get("Timeout", 0),
                    "last_modified": mod_str[:10] if mod_str else None,
                    "age_days":      _age_days(mod_dt),
                    "description":   fn.get("Description", ""),
                })
    except Exception as exc:
        results.append({"_error": str(exc)})
    return results


def _collect_s3(boto_sess: boto3.Session, env: str) -> list[dict]:
    client = boto_sess.client("s3")
    results: list[dict] = []
    try:
        resp = client.list_buckets()
        for bucket in resp.get("Buckets", []):
            name = bucket.get("Name", "")
            if env.lower() not in name.lower() and "ciq" not in name.lower():
                continue
            created = bucket.get("CreationDate")
            results.append({
                "name":       name,
                "age_days":   _age_days(created),
                "created_at": created.isoformat() if created else None,
            })
    except Exception as exc:
        results.append({"_error": str(exc)})
    return results


def _collect_cost(boto_sess: boto3.Session, days: int = 7) -> dict:
    """
    ⚠️  AWS Cost Explorer: $0.01 per API call.
    Only called when include_cost=True.
    """
    from datetime import timedelta
    # CE is global — always us-east-1.
    # Build the client from raw key/secret only: long-term IAM keys don't use
    # a session token, and passing a stale or empty one causes
    # UnrecognizedClientException.
    creds = boto_sess.get_credentials()
    frozen = creds.get_frozen_credentials() if creds else None
    if frozen and frozen.access_key:
        client = boto3.client(
            "ce",
            region_name="us-east-1",
            aws_access_key_id=frozen.access_key,
            aws_secret_access_key=frozen.secret_key,
            # aws_session_token intentionally omitted — long-term IAM keys don't
            # need one, and passing a stale/empty token causes UnrecognizedClientException
        )
    else:
        client = boto_sess.client("ce", region_name="us-east-1")

    end   = datetime.now(tz=timezone.utc).date()
    start = end - timedelta(days=days)

    resp = client.get_cost_and_usage(
        TimePeriod={"Start": str(start), "End": str(end)},
        Granularity="MONTHLY",
        Metrics=["UnblendedCost"],
        GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
    )

    by_service: list[dict] = []
    total = 0.0
    for period in resp.get("ResultsByTime", []):
        for group in period.get("Groups", []):
            svc    = group["Keys"][0]
            amount = float(group["Metrics"]["UnblendedCost"]["Amount"])
            unit   = group["Metrics"]["UnblendedCost"]["Unit"]
            if amount > 0:
                by_service.append({"service": svc, "amount": round(amount, 4), "unit": unit})
                total += amount

    by_service.sort(key=lambda x: x["amount"], reverse=True)
    weekly_usd = round(total / days * 7, 2) if days != 7 else round(total, 2)

    return {
        "warning":    f"⚠️ This cost data cost $0.01 to retrieve (AWS Cost Explorer API).",
        "period":     {"start": str(start), "end": str(end), "days": days},
        "by_service": by_service,
        "total_usd":  round(total, 2),
        "weekly_usd": weekly_usd,
    }


def collect_infra(
    env: str,
    account: str,
    region: str,
    include_cost: bool = False,
    cost_days: int = 7,
) -> dict:
    """
    Main entry point.

    Args:
        env:          e.g. "prod", "dev", "qa"
        account:      e.g. "prod" or "nonprod"  (maps to AWS key env-var prefix)
        region:       e.g. "us-east-1"
        include_cost: If True, calls Cost Explorer ($0.01/call) and adds cost breakdown
        cost_days:    Number of days for cost query (default 7 = last week)

    Returns a structured dict (see module docstring).
    """
    sess = _session(account, region)
    now  = datetime.now(tz=timezone.utc).isoformat()

    result: dict[str, Any] = {
        "env":          env,
        "account":      account,
        "region":       region,
        "collected_at": now,
        "services": {
            "ecs":         _collect_ecs(sess, env),
            "ec2":         _collect_ec2(sess, env),
            "rds":         _collect_rds(sess, env),
            "elb":         _collect_elb(sess, env),
            "elasticache": _collect_elasticache(sess, env),
            "lambda":      _collect_lambda(sess, env),
            "s3":          _collect_s3(sess, env),
        },
        "cost": None,
    }

    if include_cost:
        try:
            result["cost"] = _collect_cost(sess, days=cost_days)
        except Exception as exc:
            result["cost"] = {"_error": str(exc)}

    return result
