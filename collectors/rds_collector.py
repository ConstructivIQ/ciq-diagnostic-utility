"""
collectors/rds_collector.py
Connects to a PostgreSQL (RDS) instance and collects health metrics,
table sizes, active connections, and long-running queries.

Requires: psycopg2-binary  (pip install psycopg2-binary)
The RDS must be reachable from the machine running this script
(VPN or public endpoint with appropriate security group rules).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import config


@dataclass
class RdsSnapshot:
    connected: bool = False
    error: str = ""
    host: str = ""
    database: str = ""
    pg_version: str = ""
    # Connection stats
    total_connections: int = 0
    max_connections: int = 0
    active_connections: int = 0
    idle_connections: int = 0
    idle_in_tx: int = 0
    # DB stats (pg_stat_database)
    db_size_mb: float = 0.0
    commits: int = 0
    rollbacks: int = 0
    deadlocks: int = 0
    cache_hit_ratio: float = 0.0
    # Long-running queries (>5s)
    long_queries: list[dict] = field(default_factory=list)
    # Top tables by size
    top_tables: list[dict] = field(default_factory=list)
    # Replication lag (if replica)
    replication_lag_s: float | None = None


def _conn():
    """Open a psycopg2 connection using config.PG_* settings."""
    import psycopg2
    return psycopg2.connect(
        host=config.PG_HOST,
        port=config.PG_PORT,
        dbname=config.PG_DATABASE,
        user=config.PG_USER,
        password=config.PG_PASSWORD,
        connect_timeout=10,
        sslmode="require",
        options="-c statement_timeout=15000",   # 15s query timeout
    )


def _q(cur, sql: str, params=None) -> list[dict]:
    """Execute a read-only query, return list of row dicts."""
    cur.execute(sql, params)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def fetch_snapshot() -> RdsSnapshot:
    """Connect and return an RdsSnapshot with all health metrics."""
    snap = RdsSnapshot(host=config.PG_HOST, database=config.PG_DATABASE)

    if not (config.PG_HOST and config.PG_DATABASE and config.PG_USER):
        snap.error = "PG_HOST / PG_DATABASE / PG_USER not configured in .env"
        return snap

    try:
        import psycopg2
    except ImportError:
        snap.error = "psycopg2 not installed — run: pip install psycopg2-binary"
        return snap

    try:
        conn = _conn()
        conn.set_session(readonly=True, autocommit=True)
        cur = conn.cursor()

        # Version
        cur.execute("SELECT version();")
        snap.pg_version = cur.fetchone()[0].split(",")[0]
        snap.connected = True

        # Max connections setting
        cur.execute("SHOW max_connections;")
        snap.max_connections = int(cur.fetchone()[0])

        # Connection breakdown
        rows = _q(cur, """
            SELECT state, COUNT(*) AS cnt
            FROM pg_stat_activity
            WHERE datname = current_database()
            GROUP BY state
        """)
        for r in rows:
            state = (r["state"] or "").lower()
            cnt   = r["cnt"]
            snap.total_connections += cnt
            if state == "active":
                snap.active_connections = cnt
            elif state == "idle":
                snap.idle_connections = cnt
            elif "idle in transaction" in state:
                snap.idle_in_tx += cnt

        # DB stats
        rows = _q(cur, """
            SELECT
                pg_database_size(current_database()) / 1048576.0   AS size_mb,
                xact_commit,
                xact_rollback,
                deadlocks,
                CASE WHEN blks_hit + blks_read = 0 THEN 1.0
                     ELSE blks_hit::float / (blks_hit + blks_read)
                END AS cache_hit
            FROM pg_stat_database
            WHERE datname = current_database()
        """)
        if rows:
            r = rows[0]
            snap.db_size_mb       = round(float(r["size_mb"] or 0), 1)
            snap.commits          = int(r["xact_commit"] or 0)
            snap.rollbacks        = int(r["xact_rollback"] or 0)
            snap.deadlocks        = int(r["deadlocks"] or 0)
            snap.cache_hit_ratio  = round(float(r["cache_hit"] or 0) * 100, 1)

        # Long-running queries (>5 seconds, exclude idle)
        snap.long_queries = _q(cur, """
            SELECT
                pid,
                state,
                EXTRACT(EPOCH FROM (now() - query_start))::int AS duration_s,
                LEFT(query, 300) AS query
            FROM pg_stat_activity
            WHERE datname = current_database()
              AND state NOT IN ('idle', 'idle in transaction (aborted)')
              AND query_start IS NOT NULL
              AND now() - query_start > interval '5 seconds'
              AND query NOT ILIKE '%pg_stat_activity%'
            ORDER BY duration_s DESC
            LIMIT 10
        """)

        # Top 15 tables by total size
        snap.top_tables = _q(cur, """
            SELECT
                schemaname || '.' || tablename                          AS table_name,
                pg_size_pretty(pg_total_relation_size(
                    (schemaname||'.'||tablename)::regclass))            AS total_size,
                pg_total_relation_size(
                    (schemaname||'.'||tablename)::regclass) / 1048576.0 AS size_mb,
                n_live_tup                                              AS row_estimate
            FROM pg_stat_user_tables
            ORDER BY pg_total_relation_size(
                (schemaname||'.'||tablename)::regclass) DESC
            LIMIT 15
        """)

        # Replication lag (only meaningful on replicas)
        try:
            cur.execute("""
                SELECT EXTRACT(EPOCH FROM (now() - pg_last_xact_replay_timestamp()))
                AS lag_s
            """)
            row = cur.fetchone()
            if row and row[0] is not None:
                snap.replication_lag_s = round(float(row[0]), 1)
        except Exception:
            pass

        conn.close()

    except Exception as exc:
        snap.connected = False
        snap.error = str(exc)

    return snap
