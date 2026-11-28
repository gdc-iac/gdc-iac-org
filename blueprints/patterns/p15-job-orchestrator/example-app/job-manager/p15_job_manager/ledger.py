# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Bounded PostgreSQL Pool (`pool_pre_ping` + keepalives) & SQLite-Compatible State Ledger (`REQ-SCH-002`, `REQ-REL-003`)."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import threading
import time
from typing import Any, Iterator
import uuid

from .config import ControlPlaneConfig
from .cron_utils import normalize_utc_iso

SQL_INIT_FILE = Path(__file__).resolve().parent.parent / "sql" / "001_init_schemas.sql"

_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS job_definitions (
    job_id                  TEXT PRIMARY KEY,
    namespace               TEXT NOT NULL,
    persona                 TEXT NOT NULL,
    job_class               TEXT NOT NULL,
    template_name           TEXT NOT NULL DEFAULT 'gdc-standard-job-runner-v1',
    worker_image            TEXT NOT NULL,
    worker_mode             TEXT NOT NULL,
    enforcement_mode        TEXT NOT NULL DEFAULT 'audit',
    schedule_cron           TEXT NOT NULL,
    timezone                TEXT NOT NULL DEFAULT 'UTC',
    suspended               INTEGER NOT NULL DEFAULT 0,
    concurrency_policy      TEXT NOT NULL DEFAULT 'Forbid',
    starting_deadline_secs  INTEGER NOT NULL DEFAULT 300,
    active_deadline_secs    INTEGER NOT NULL DEFAULT 900,
    sla_seconds             INTEGER NOT NULL DEFAULT 900,
    max_shards              INTEGER NOT NULL DEFAULT 10,
    parallelism             INTEGER NOT NULL DEFAULT 5,
    max_actions_per_run     INTEGER NOT NULL DEFAULT 5,
    cooldown_seconds        INTEGER NOT NULL DEFAULT 3600,
    consecutive_failures    INTEGER NOT NULL DEFAULT 0,
    circuit_breaker_open    INTEGER NOT NULL DEFAULT 0,
    gitops_managed          INTEGER NOT NULL DEFAULT 0,
    gitops_annotations      TEXT NOT NULL DEFAULT '{}',
    parameters              TEXT NOT NULL DEFAULT '{}',
    notification_sinks      TEXT NOT NULL DEFAULT '[]',
    created_by              TEXT NOT NULL,
    created_at              TEXT NOT NULL,
    updated_at              TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS job_runs (
    run_id                  TEXT PRIMARY KEY,
    job_id                  TEXT NOT NULL,
    namespace               TEXT NOT NULL,
    engine_mode             TEXT NOT NULL,
    engine_ref              TEXT NOT NULL,
    trigger_type            TEXT NOT NULL,
    window_start            TEXT NOT NULL,
    window_end              TEXT NOT NULL,
    shard_key               TEXT NOT NULL DEFAULT 'all',
    status                  TEXT NOT NULL,
    attempt                 INTEGER NOT NULL DEFAULT 1,
    exit_code               INTEGER,
    artifact_uri            TEXT,
    summary_json            TEXT NOT NULL DEFAULT '{}',
    requested_by            TEXT NOT NULL DEFAULT 'system',
    started_at              TEXT NOT NULL,
    finished_at             TEXT
);

CREATE TABLE IF NOT EXISTS watermarks (
    job_id                  TEXT NOT NULL,
    shard_key               TEXT NOT NULL DEFAULT 'all',
    last_window_end         TEXT NOT NULL,
    last_object_uri         TEXT,
    updated_at              TEXT NOT NULL,
    PRIMARY KEY (job_id, shard_key)
);

CREATE TABLE IF NOT EXISTS enforcement_findings (
    finding_id              TEXT PRIMARY KEY,
    run_id                  TEXT NOT NULL,
    job_id                  TEXT NOT NULL,
    namespace               TEXT NOT NULL,
    target_kind             TEXT NOT NULL,
    target_namespace        TEXT NOT NULL,
    target_name             TEXT NOT NULL,
    target_resource_version TEXT NOT NULL,
    rule_id                 TEXT NOT NULL,
    severity                TEXT NOT NULL,
    planned_patch_json      TEXT NOT NULL DEFAULT '{}',
    planned_patch_sha256    TEXT NOT NULL,
    snapshot_uri            TEXT,
    status                  TEXT NOT NULL,
    requested_by            TEXT NOT NULL,
    remediated_at           TEXT,
    created_at              TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS remediation_approvals (
    approval_id             TEXT PRIMARY KEY,
    finding_id              TEXT NOT NULL,
    job_id                  TEXT NOT NULL,
    requester               TEXT NOT NULL,
    approver                TEXT NOT NULL,
    decision                TEXT NOT NULL,
    reason                  TEXT NOT NULL,
    planned_patch_sha256    TEXT NOT NULL,
    target_resource_version TEXT NOT NULL,
    expires_at              TEXT NOT NULL,
    decided_at              TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notification_outbox (
    outbox_id               TEXT PRIMARY KEY,
    event_id                TEXT NOT NULL,
    dedup_key               TEXT NOT NULL,
    sink_name               TEXT NOT NULL,
    sink_type               TEXT NOT NULL,
    namespace               TEXT NOT NULL,
    job_id                  TEXT NOT NULL,
    event_type              TEXT NOT NULL,
    severity                TEXT NOT NULL,
    payload_json            TEXT NOT NULL,
    status                  TEXT NOT NULL DEFAULT 'pending',
    attempts                INTEGER NOT NULL DEFAULT 0,
    next_retry_at           TEXT NOT NULL,
    last_status_code        INTEGER,
    last_error              TEXT,
    created_at              TEXT NOT NULL,
    delivered_at            TEXT
);

CREATE TABLE IF NOT EXISTS notification_sinks (
    sink_name               TEXT PRIMARY KEY,
    namespace               TEXT NOT NULL,
    sink_type               TEXT NOT NULL,
    url                     TEXT NOT NULL,
    config_json             TEXT NOT NULL DEFAULT '{}',
    enabled                 INTEGER NOT NULL DEFAULT 1,
    updated_at              TEXT NOT NULL
);
"""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _json_loads_safe(val: Any, default: Any) -> Any:
    if val is None:
        return default
    if isinstance(val, (dict, list)):
        return val
    try:
        return json.loads(val)
    except Exception:
        return default


class LedgerStore:
    """Unified state, watermark, approval, and transactional outbox ledger (`PostgreSQL` + `SQLite`).

    Enforces `REQ-REL-003` bounded PostgreSQL pools (`min=1, max=10` per replica), TCP keepalives
    (`15s/5s/3`), `connect_timeout=5`, `statement_timeout=30000`, and `SELECT 1` `pool_pre_ping`
    so connections recover within `< 15s` once PostgreSQL returns after a GDC-ag `v1.16.2+`
    `DBCluster` HA automatic failover (`~90s` 3x30s detection + standby promotion, `~2+ min` RTO)
    or planned maintenance window.
    """

    POOL_MIN_CONN = 1
    POOL_MAX_CONN = 10
    CONNECT_TIMEOUT = 5
    STATEMENT_TIMEOUT_MS = 30000
    KEEPALIVES_IDLE = 15
    KEEPALIVES_INTERVAL = 5
    KEEPALIVES_COUNT = 3

    def __init__(self, config: ControlPlaneConfig) -> None:
        self.config = config
        self._lock = threading.RLock()
        self._pg_pool: Any = None
        self._sqlite_conn: sqlite3.Connection | None = None
        self.backend = "postgres" if (config.db_dsn or config.db_host) else "sqlite"

        # Runtime PA governance state (persisted in memory + exported via Admin API)
        self.emergency_pause_all: bool = False
        self.namespace_quotas: dict[str, dict[str, int]] = {}
        self.registered_sinks: dict[str, dict[str, Any]] = {
            "portal-default": {
                "name": "portal-default",
                "namespace": "*",
                "type": "portal-feed",
                "url": "internal://portal-feed",
                "events": [
                    "OnFailure",
                    "OnRecovery",
                    "OnSLAExceeded",
                    "OnViolationDetected",
                    "OnApprovalRequired",
                    "OnAutoHealExecuted",
                    "OnCircuitBreakerOpen",
                ],
                "enabled": True,
            }
        }
        self._init_backend()

    def _build_pg_kwargs(self) -> dict[str, Any]:
        # Strip ":5432" if projected from GDC DBCluster .status.primary.url (potential-gotchas-on-gdc-ag.md)
        host = self.config.db_host
        port = self.config.db_port
        if ":" in host and not host.startswith("["):
            h_part, p_part = host.rsplit(":", 1)
            if p_part.isdigit():
                host = h_part
                port = int(p_part)
        kwargs: dict[str, Any] = {
            "host": host,
            "port": port,
            "dbname": self.config.db_name,
            "user": self.config.db_user,
            "password": self.config.db_password,
            "connect_timeout": self.CONNECT_TIMEOUT,
            "options": f"-c statement_timeout={self.STATEMENT_TIMEOUT_MS}",
            "keepalives": 1,
            "keepalives_idle": self.KEEPALIVES_IDLE,
            "keepalives_interval": self.KEEPALIVES_INTERVAL,
            "keepalives_count": self.KEEPALIVES_COUNT,
        }
        if self.config.db_sslrootcert and Path(self.config.db_sslrootcert).exists():
            kwargs["sslmode"] = "verify-ca"
            kwargs["sslrootcert"] = self.config.db_sslrootcert
        return kwargs

    def _init_backend(self) -> None:
        if self.backend == "postgres":
            from psycopg2 import pool as pg_pool  # type: ignore

            last_exc: Exception | None = None
            for attempt in range(1, 7):
                try:
                    if self.config.db_dsn:
                        self._pg_pool = pg_pool.ThreadedConnectionPool(
                            self.POOL_MIN_CONN,
                            self.POOL_MAX_CONN,
                            dsn=self.config.db_dsn,
                            connect_timeout=self.CONNECT_TIMEOUT,
                            keepalives=1,
                            keepalives_idle=self.KEEPALIVES_IDLE,
                            keepalives_interval=self.KEEPALIVES_INTERVAL,
                            keepalives_count=self.KEEPALIVES_COUNT,
                        )
                    else:
                        self._pg_pool = pg_pool.ThreadedConnectionPool(
                            self.POOL_MIN_CONN,
                            self.POOL_MAX_CONN,
                            **self._build_pg_kwargs(),
                        )
                    ddl = SQL_INIT_FILE.read_text(encoding="utf-8")
                    with self._borrow_pg_conn() as conn:
                        with conn.cursor() as cur:
                            cur.execute(ddl)
                        conn.commit()
                    last_exc = None
                    break
                except Exception as exc:
                    last_exc = exc
                    if self._pg_pool is not None:
                        try:
                            self._pg_pool.closeall()
                        except Exception:
                            pass
                        self._pg_pool = None
                    if attempt < 6:
                        time.sleep(2.0)
            if last_exc is not None:
                raise last_exc
        else:
            self._sqlite_conn = sqlite3.connect(self.config.sqlite_path, check_same_thread=False)
            self._sqlite_conn.row_factory = sqlite3.Row
            with self._lock:
                self._sqlite_conn.executescript(_SQLITE_SCHEMA)
                self._sqlite_conn.commit()

    @contextmanager
    def _borrow_pg_conn(self) -> Iterator[Any]:
        """Borrow a pooled PostgreSQL connection with `SELECT 1` `pool_pre_ping` & jittered retry."""
        last_exc: Exception | None = None
        for attempt in range(3):
            conn = self._pg_pool.getconn()
            discard = False
            try:
                # pool_pre_ping: detect stale TCP sockets after DBCluster HA failover or maintenance
                with conn.cursor() as ping_cur:
                    ping_cur.execute("SELECT 1;")
            except Exception as exc:
                last_exc = exc
                self._pg_pool.putconn(conn, close=True)
                time.sleep(0.15 * (attempt + 1))
                continue

            try:
                yield conn
                return
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    discard = True
                raise
            finally:
                self._pg_pool.putconn(conn, close=discard)
        raise RuntimeError(f"PostgreSQL pool_pre_ping failed after 3 attempts: {last_exc}")

    def _table(self, name: str) -> str:
        return f"platform_jobs.{name}" if self.backend == "postgres" else name

    def _ph(self, count: int) -> str:
        token = "%s" if self.backend == "postgres" else "?"
        return ", ".join([token] * count)

    def _exec(self, sql: str, params: tuple[Any, ...] = (), fetch: str = "none") -> Any:
        if self.backend == "postgres":
            from psycopg2.extras import RealDictCursor  # type: ignore

            pg_sql = sql.replace("?", "%s")
            with self._borrow_pg_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(pg_sql, params)
                    if fetch == "one":
                        row = cur.fetchone()
                        conn.commit()
                        return dict(row) if row else None
                    if fetch == "all":
                        rows = [dict(r) for r in cur.fetchall()]
                        conn.commit()
                        return rows
                conn.commit()
                return None

        assert self._sqlite_conn is not None
        with self._lock:
            cur = self._sqlite_conn.execute(sql, params)
            if fetch == "one":
                row = cur.fetchone()
                self._sqlite_conn.commit()
                return dict(row) if row else None
            if fetch == "all":
                rows = [dict(r) for r in cur.fetchall()]
                self._sqlite_conn.commit()
                return rows
            self._sqlite_conn.commit()
            return None

    def health_check(self) -> bool:
        try:
            self._exec("SELECT 1 AS ok", fetch="one")
            return True
        except Exception:
            return False

    def close(self) -> None:
        if self._sqlite_conn is not None:
            try:
                self._sqlite_conn.close()
            except Exception:
                pass
            self._sqlite_conn = None
        if self._pg_pool is not None:
            try:
                self._pg_pool.closeall()
            except Exception:
                pass
            self._pg_pool = None

    def __del__(self) -> None:
        self.close()

    # -------------------------------------------------------------------------
    # Job Definitions CRUD
    # -------------------------------------------------------------------------
    def _hydrate_job(self, row: dict[str, Any] | None) -> dict[str, Any] | None:
        if not row:
            return None
        out = dict(row)
        out["suspended"] = bool(out.get("suspended"))
        out["circuit_breaker_open"] = bool(out.get("circuit_breaker_open"))
        out["gitops_managed"] = bool(out.get("gitops_managed"))
        out["gitops_annotations"] = _json_loads_safe(out.get("gitops_annotations"), {})
        out["parameters"] = _json_loads_safe(out.get("parameters"), {})
        out["notification_sinks"] = _json_loads_safe(out.get("notification_sinks"), [])
        for ts_col in ("created_at", "updated_at"):
            if isinstance(out.get(ts_col), datetime):
                out[ts_col] = normalize_utc_iso(out[ts_col])
        return out

    def upsert_job_definition(self, job: dict[str, Any]) -> dict[str, Any]:
        now = _utc_now_iso()
        tbl = self._table("job_definitions")
        params = (
            job["job_id"],
            job["namespace"],
            job["persona"],
            job["job_class"],
            job.get("template_name", "gdc-standard-job-runner-v1"),
            job["worker_image"],
            job["worker_mode"],
            job.get("enforcement_mode", "audit"),
            job["schedule_cron"],
            job.get("timezone", "UTC"),
            bool(job.get("suspended", False)) if self.backend == "postgres" else int(bool(job.get("suspended", False))),
            job.get("concurrency_policy", "Forbid"),
            int(job.get("starting_deadline_secs", 300)),
            int(job.get("active_deadline_secs", 900)),
            int(job.get("sla_seconds", 900)),
            int(job.get("max_shards", 10)),
            int(job.get("parallelism", 5)),
            int(job.get("max_actions_per_run", self.config.default_max_actions_per_run)),
            int(job.get("cooldown_seconds", self.config.default_cooldown_seconds)),
            int(job.get("consecutive_failures", 0)),
            bool(job.get("circuit_breaker_open", False))
            if self.backend == "postgres"
            else int(bool(job.get("circuit_breaker_open", False))),
            bool(job.get("gitops_managed", False))
            if self.backend == "postgres"
            else int(bool(job.get("gitops_managed", False))),
            json.dumps(job.get("gitops_annotations", {})),
            json.dumps(job.get("parameters", {})),
            json.dumps(job.get("notification_sinks", ["portal-default"])),
            job.get("created_by", "system"),
            job.get("created_at", now),
            now,
        )
        sql = f"""
        INSERT INTO {tbl} (
            job_id, namespace, persona, job_class, template_name, worker_image, worker_mode,
            enforcement_mode, schedule_cron, timezone, suspended, concurrency_policy,
            starting_deadline_secs, active_deadline_secs, sla_seconds, max_shards, parallelism,
            max_actions_per_run, cooldown_seconds, consecutive_failures, circuit_breaker_open,
            gitops_managed, gitops_annotations, parameters, notification_sinks, created_by,
            created_at, updated_at
        ) VALUES ({",".join(["?"] * 28)})
        ON CONFLICT (job_id) DO UPDATE SET
            persona = EXCLUDED.persona,
            job_class = EXCLUDED.job_class,
            template_name = EXCLUDED.template_name,
            worker_image = EXCLUDED.worker_image,
            worker_mode = EXCLUDED.worker_mode,
            enforcement_mode = EXCLUDED.enforcement_mode,
            schedule_cron = EXCLUDED.schedule_cron,
            timezone = EXCLUDED.timezone,
            suspended = EXCLUDED.suspended,
            concurrency_policy = EXCLUDED.concurrency_policy,
            starting_deadline_secs = EXCLUDED.starting_deadline_secs,
            active_deadline_secs = EXCLUDED.active_deadline_secs,
            sla_seconds = EXCLUDED.sla_seconds,
            max_shards = EXCLUDED.max_shards,
            parallelism = EXCLUDED.parallelism,
            max_actions_per_run = EXCLUDED.max_actions_per_run,
            cooldown_seconds = EXCLUDED.cooldown_seconds,
            consecutive_failures = EXCLUDED.consecutive_failures,
            circuit_breaker_open = EXCLUDED.circuit_breaker_open,
            gitops_managed = EXCLUDED.gitops_managed,
            gitops_annotations = EXCLUDED.gitops_annotations,
            parameters = EXCLUDED.parameters,
            notification_sinks = EXCLUDED.notification_sinks,
            updated_at = EXCLUDED.updated_at
        """
        self._exec(sql, params)
        res = self.get_job_definition(job["job_id"])
        assert res is not None
        return res

    def get_job_definition(self, job_id: str) -> dict[str, Any] | None:
        tbl = self._table("job_definitions")
        row = self._exec(f"SELECT * FROM {tbl} WHERE job_id = ?", (job_id,), fetch="one")
        return self._hydrate_job(row)

    def list_job_definitions(
        self,
        allowed_namespaces: tuple[str, ...] | None = None,
        persona: str | None = None,
        job_class: str | None = None,
    ) -> list[dict[str, Any]]:
        tbl = self._table("job_definitions")
        rows = self._exec(f"SELECT * FROM {tbl} ORDER BY job_id ASC", fetch="all")
        out = [self._hydrate_job(r) for r in rows]
        filtered: list[dict[str, Any]] = []
        for item in out:
            if not item:
                continue
            if allowed_namespaces and "*" not in allowed_namespaces and item["namespace"] not in allowed_namespaces:
                continue
            if persona and item["persona"] != persona:
                continue
            if job_class and item["job_class"] != job_class:
                continue
            filtered.append(item)
        return filtered

    def delete_job_definition(self, job_id: str) -> bool:
        existing = self.get_job_definition(job_id)
        if not existing:
            return False
        tbl = self._table("job_definitions")
        self._exec(f"DELETE FROM {tbl} WHERE job_id = ?", (job_id,))
        return True

    # -------------------------------------------------------------------------
    # Job Runs & Watermarks (Idempotent Upsert)
    # -------------------------------------------------------------------------
    def upsert_job_run(self, run: dict[str, Any]) -> dict[str, Any]:
        now = _utc_now_iso()
        tbl = self._table("job_runs")
        w_start = normalize_utc_iso(run.get("window_start") or now)
        w_end = normalize_utc_iso(run.get("window_end") or now)
        started = normalize_utc_iso(run.get("started_at") or now)
        finished = normalize_utc_iso(run["finished_at"]) if run.get("finished_at") else None
        params = (
            run["run_id"],
            run["job_id"],
            run["namespace"],
            run.get("engine_mode", self.config.engine_mode),
            run.get("engine_ref", run["run_id"]),
            run.get("trigger_type", "manual"),
            w_start,
            w_end,
            run.get("shard_key", "all"),
            run["status"],
            int(run.get("attempt", 1)),
            run.get("exit_code"),
            run.get("artifact_uri"),
            json.dumps(run.get("summary_json", {})),
            run.get("requested_by", "system"),
            started,
            finished,
        )
        sql = f"""
        INSERT INTO {tbl} (
            run_id, job_id, namespace, engine_mode, engine_ref, trigger_type,
            window_start, window_end, shard_key, status, attempt, exit_code,
            artifact_uri, summary_json, requested_by, started_at, finished_at
        ) VALUES ({",".join(["?"] * 17)})
        ON CONFLICT (run_id) DO UPDATE SET
            status = EXCLUDED.status,
            attempt = EXCLUDED.attempt,
            exit_code = EXCLUDED.exit_code,
            artifact_uri = COALESCE(EXCLUDED.artifact_uri, {tbl}.artifact_uri),
            summary_json = EXCLUDED.summary_json,
            finished_at = COALESCE(EXCLUDED.finished_at, {tbl}.finished_at)
        """
        self._exec(sql, params)
        res = self.get_job_run(run["run_id"])
        assert res is not None
        return res

    def _hydrate_run(self, row: dict[str, Any] | None) -> dict[str, Any] | None:
        if not row:
            return None
        out = dict(row)
        out["summary_json"] = _json_loads_safe(out.get("summary_json"), {})
        for col in ("window_start", "window_end", "started_at", "finished_at"):
            if isinstance(out.get(col), datetime):
                out[col] = normalize_utc_iso(out[col])
        return out

    def get_job_run(self, run_id: str) -> dict[str, Any] | None:
        tbl = self._table("job_runs")
        return self._hydrate_run(self._exec(f"SELECT * FROM {tbl} WHERE run_id = ?", (run_id,), fetch="one"))

    def list_job_runs(
        self,
        job_id: str | None = None,
        allowed_namespaces: tuple[str, ...] | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        tbl = self._table("job_runs")
        rows = self._exec(
            f"SELECT * FROM {tbl} ORDER BY started_at DESC LIMIT ?", (int(limit),), fetch="all"
        )
        out: list[dict[str, Any]] = []
        for r in rows:
            item = self._hydrate_run(r)
            if not item:
                continue
            if job_id and item["job_id"] != job_id:
                continue
            if status and item["status"] != status:
                continue
            if allowed_namespaces and "*" not in allowed_namespaces and item["namespace"] not in allowed_namespaces:
                continue
            out.append(item)
        return out

    def advance_watermark(
        self, job_id: str, shard_key: str, window_end_utc: str, object_uri: str | None = None
    ) -> dict[str, Any]:
        """Idempotently advance `(job_id, shard_key)` watermark without regressing on historical backfills."""
        w_end = normalize_utc_iso(window_end_utc)
        now = _utc_now_iso()
        cur = self.get_watermark(job_id, shard_key)
        if cur and cur["last_window_end"] > w_end:
            return cur
        tbl = self._table("watermarks")
        sql = f"""
        INSERT INTO {tbl} (job_id, shard_key, last_window_end, last_object_uri, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (job_id, shard_key) DO UPDATE SET
            last_window_end = EXCLUDED.last_window_end,
            last_object_uri = COALESCE(EXCLUDED.last_object_uri, {tbl}.last_object_uri),
            updated_at = EXCLUDED.updated_at
        """
        self._exec(sql, (job_id, shard_key, w_end, object_uri, now))
        res = self.get_watermark(job_id, shard_key)
        assert res is not None
        return res

    def get_watermark(self, job_id: str, shard_key: str = "all") -> dict[str, Any] | None:
        tbl = self._table("watermarks")
        row = self._exec(
            f"SELECT * FROM {tbl} WHERE job_id = ? AND shard_key = ?", (job_id, shard_key), fetch="one"
        )
        if not row:
            return None
        out = dict(row)
        for col in ("last_window_end", "updated_at"):
            if isinstance(out.get(col), datetime):
                out[col] = normalize_utc_iso(out[col])
        return out

    # -------------------------------------------------------------------------
    # Enforcement Findings & HITL Approvals
    # -------------------------------------------------------------------------
    def upsert_finding(self, finding: dict[str, Any]) -> dict[str, Any]:
        now = _utc_now_iso()
        tbl = self._table("enforcement_findings")
        rem_at = normalize_utc_iso(finding["remediated_at"]) if finding.get("remediated_at") else None
        params = (
            finding["finding_id"],
            finding["run_id"],
            finding["job_id"],
            finding["namespace"],
            finding["target_kind"],
            finding["target_namespace"],
            finding["target_name"],
            str(finding["target_resource_version"]),
            finding["rule_id"],
            finding["severity"],
            json.dumps(finding.get("planned_patch_json", {}), sort_keys=True),
            finding["planned_patch_sha256"],
            finding.get("snapshot_uri"),
            finding["status"],
            finding.get("requested_by", "system"),
            rem_at,
            finding.get("created_at", now),
        )
        sql = f"""
        INSERT INTO {tbl} (
            finding_id, run_id, job_id, namespace, target_kind, target_namespace, target_name,
            target_resource_version, rule_id, severity, planned_patch_json, planned_patch_sha256,
            snapshot_uri, status, requested_by, remediated_at, created_at
        ) VALUES ({",".join(["?"] * 17)})
        ON CONFLICT (finding_id) DO UPDATE SET
            status = EXCLUDED.status,
            snapshot_uri = COALESCE(EXCLUDED.snapshot_uri, {tbl}.snapshot_uri),
            remediated_at = COALESCE(EXCLUDED.remediated_at, {tbl}.remediated_at)
        """
        self._exec(sql, params)
        res = self.get_finding(finding["finding_id"])
        assert res is not None
        return res

    def get_finding(self, finding_id: str) -> dict[str, Any] | None:
        tbl = self._table("enforcement_findings")
        row = self._exec(f"SELECT * FROM {tbl} WHERE finding_id = ?", (finding_id,), fetch="one")
        if not row:
            return None
        out = dict(row)
        out["planned_patch_json"] = _json_loads_safe(out.get("planned_patch_json"), {})
        for col in ("remediated_at", "created_at"):
            if isinstance(out.get(col), datetime):
                out[col] = normalize_utc_iso(out[col])
        return out

    def list_findings(
        self,
        allowed_namespaces: tuple[str, ...] | None = None,
        status: str | None = None,
        target_ref: tuple[str, str, str] | None = None,
    ) -> list[dict[str, Any]]:
        tbl = self._table("enforcement_findings")
        rows = self._exec(f"SELECT * FROM {tbl} ORDER BY created_at DESC", fetch="all")
        out: list[dict[str, Any]] = []
        for r in rows:
            item = dict(r)
            item["planned_patch_json"] = _json_loads_safe(item.get("planned_patch_json"), {})
            for col in ("remediated_at", "created_at"):
                if isinstance(item.get(col), datetime):
                    item[col] = normalize_utc_iso(item[col])
            if status and item["status"] != status:
                continue
            if target_ref and (
                item["target_kind"],
                item["target_namespace"],
                item["target_name"],
            ) != target_ref:
                continue
            if allowed_namespaces and "*" not in allowed_namespaces and item["namespace"] not in allowed_namespaces:
                continue
            out.append(item)
        return out

    def _hydrate_approval(self, row: dict[str, Any] | None) -> dict[str, Any] | None:
        if not row:
            return None
        out = dict(row)
        for col in ("expires_at", "decided_at"):
            if isinstance(out.get(col), datetime):
                out[col] = normalize_utc_iso(out[col])
        return out

    def append_approval(self, approval: dict[str, Any]) -> dict[str, Any]:
        now = _utc_now_iso()
        tbl = self._table("remediation_approvals")
        app_id = approval.get("approval_id") or f"apr-{uuid.uuid4().hex[:12]}"
        exp = normalize_utc_iso(approval["expires_at"])
        dec = normalize_utc_iso(approval.get("decided_at") or now)
        sql = f"""
        INSERT INTO {tbl} (
            approval_id, finding_id, job_id, requester, approver, decision, reason,
            planned_patch_sha256, target_resource_version, expires_at, decided_at
        ) VALUES ({",".join(["?"] * 11)})
        """
        self._exec(
            sql,
            (
                app_id,
                approval["finding_id"],
                approval["job_id"],
                approval["requester"],
                approval["approver"],
                approval["decision"],
                approval["reason"],
                approval["planned_patch_sha256"],
                str(approval["target_resource_version"]),
                exp,
                dec,
            ),
        )
        row = self._hydrate_approval(
            self._exec(f"SELECT * FROM {tbl} WHERE approval_id = ?", (app_id,), fetch="one")
        )
        assert row is not None
        return row

    def list_approvals(self, job_id: str | None = None) -> list[dict[str, Any]]:
        tbl = self._table("remediation_approvals")
        rows = self._exec(f"SELECT * FROM {tbl} ORDER BY decided_at DESC", fetch="all")
        return [
            hydrated
            for r in rows
            if (hydrated := self._hydrate_approval(r)) is not None
            and (not job_id or hydrated["job_id"] == job_id)
        ]

    # -------------------------------------------------------------------------
    # Transactional Notification Outbox (`SELECT ... FOR UPDATE SKIP LOCKED`)
    # -------------------------------------------------------------------------
    def has_recent_delivered_dedup(self, dedup_key: str, sink_name: str, window_seconds: int, now_utc: datetime | None = None) -> bool:
        cutoff = ((now_utc or datetime.now(timezone.utc)) - timedelta(seconds=window_seconds)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        tbl = self._table("notification_outbox")
        row = self._exec(
            f"SELECT outbox_id FROM {tbl} WHERE dedup_key = ? AND sink_name = ? "
            "AND status = 'delivered' AND created_at >= ? LIMIT 1",
            (dedup_key, sink_name, cutoff),
            fetch="one",
        )
        return row is not None

    def enqueue_outbox_item(self, item: dict[str, Any]) -> dict[str, Any]:
        now = normalize_utc_iso(item.get("created_at") or _utc_now_iso())
        next_retry = normalize_utc_iso(item.get("next_retry_at") or now)
        outbox_id = item.get("outbox_id") or f"obx-{uuid.uuid4().hex[:12]}"
        tbl = self._table("notification_outbox")
        sql = f"""
        INSERT INTO {tbl} (
            outbox_id, event_id, dedup_key, sink_name, sink_type, namespace, job_id,
            event_type, severity, payload_json, status, attempts, next_retry_at,
            last_status_code, last_error, created_at, delivered_at
        ) VALUES ({",".join(["?"] * 17)})
        """
        self._exec(
            sql,
            (
                outbox_id,
                item["event_id"],
                item["dedup_key"],
                item["sink_name"],
                item["sink_type"],
                item["namespace"],
                item["job_id"],
                item["event_type"],
                item["severity"],
                json.dumps(item["payload_json"], sort_keys=True),
                item.get("status", "pending"),
                int(item.get("attempts", 0)),
                next_retry,
                item.get("last_status_code"),
                item.get("last_error"),
                now,
                item.get("delivered_at"),
            ),
        )
        res = self.get_outbox_item(outbox_id)
        assert res is not None
        return res

    def claim_pending_outbox_batch(self, limit: int = 25, now_utc: datetime | None = None) -> list[dict[str, Any]]:
        """Claim due `pending` outbox items using `FOR UPDATE SKIP LOCKED` on PostgreSQL."""
        now_str = normalize_utc_iso(now_utc or _utc_now_iso())
        tbl = self._table("notification_outbox")
        if self.backend == "postgres":
            from psycopg2.extras import RealDictCursor  # type: ignore

            with self._borrow_pg_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        f"SELECT * FROM {tbl} WHERE status = 'pending' AND next_retry_at <= %s "
                        "ORDER BY created_at ASC LIMIT %s FOR UPDATE SKIP LOCKED",
                        (now_str, int(limit)),
                    )
                    rows = [self._hydrate_outbox(dict(r)) for r in cur.fetchall()]
                conn.commit()
                return [r for r in rows if r is not None]

        rows = self._exec(
            f"SELECT * FROM {tbl} WHERE status = 'pending' AND next_retry_at <= ? "
            "ORDER BY created_at ASC LIMIT ?",
            (now_str, int(limit)),
            fetch="all",
        )
        return [h for r in rows if (h := self._hydrate_outbox(r)) is not None]

    def update_outbox_item(
        self,
        outbox_id: str,
        status: str,
        attempts: int,
        next_retry_at: str | None = None,
        last_status_code: int | None = None,
        last_error: str | None = None,
        delivered_at: str | None = None,
    ) -> None:
        tbl = self._table("notification_outbox")
        self._exec(
            f"UPDATE {tbl} SET status = ?, attempts = ?, next_retry_at = COALESCE(?, next_retry_at), "
            "last_status_code = ?, last_error = ?, delivered_at = COALESCE(?, delivered_at) "
            "WHERE outbox_id = ?",
            (
                status,
                int(attempts),
                normalize_utc_iso(next_retry_at) if next_retry_at else None,
                last_status_code,
                last_error,
                normalize_utc_iso(delivered_at) if delivered_at else None,
                outbox_id,
            ),
        )

    def _hydrate_outbox(self, row: dict[str, Any] | None) -> dict[str, Any] | None:
        if not row:
            return None
        out = dict(row)
        out["payload_json"] = _json_loads_safe(out.get("payload_json"), {})
        for col in ("next_retry_at", "created_at", "delivered_at"):
            if isinstance(out.get(col), datetime):
                out[col] = normalize_utc_iso(out[col])
        return out

    def get_outbox_item(self, outbox_id: str) -> dict[str, Any] | None:
        tbl = self._table("notification_outbox")
        return self._hydrate_outbox(
            self._exec(f"SELECT * FROM {tbl} WHERE outbox_id = ?", (outbox_id,), fetch="one")
        )

    def list_outbox_items(
        self,
        allowed_namespaces: tuple[str, ...] | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        tbl = self._table("notification_outbox")
        rows = self._exec(
            f"SELECT * FROM {tbl} ORDER BY created_at DESC LIMIT ?", (int(limit),), fetch="all"
        )
        out: list[dict[str, Any]] = []
        for r in rows:
            item = self._hydrate_outbox(r)
            if not item:
                continue
            if status and item["status"] != status:
                continue
            if allowed_namespaces and "*" not in allowed_namespaces and item["namespace"] not in allowed_namespaces:
                continue
            out.append(item)
        return out

    # -------------------------------------------------------------------------
    # Persisted Notification Sinks (HA-shared across replicas; never store raw secrets)
    # -------------------------------------------------------------------------
    def _hydrate_sink(self, row: dict[str, Any] | None) -> dict[str, Any] | None:
        if not row:
            return None
        cfg = _json_loads_safe(row.get("config_json"), {})
        if not isinstance(cfg, dict):
            cfg = {}
        sink = {
            **cfg,
            "name": row["sink_name"],
            "namespace": row["namespace"],
            "type": row["sink_type"],
            "url": row["url"],
            "enabled": bool(row.get("enabled", True)),
        }
        mem = self.registered_sinks.get(sink["name"])
        if mem and mem.get("url") == sink["url"] and mem.get("type") == sink["type"]:
            # Preserve ephemeral in-memory test secrets without ever persisting plaintext secrets to DB
            if mem.get("hmac_secret") and not sink.get("hmac_secret_env"):
                sink["hmac_secret"] = mem["hmac_secret"]
            if mem.get("smtp_password") and not sink.get("smtp_password_env"):
                sink["smtp_password"] = mem["smtp_password"]
        return sink

    def upsert_sink(self, sink_cfg: dict[str, Any]) -> dict[str, Any]:
        name = str(sink_cfg["name"])
        now = _utc_now_iso()
        tbl = self._table("notification_sinks")
        # Persist only non-secret configuration and *_env references (never raw credentials)
        persistable = {
            k: v
            for k, v in sink_cfg.items()
            if k not in ("name", "namespace", "type", "url", "enabled", "hmac_secret", "smtp_password")
        }
        enabled_val: Any = (
            bool(sink_cfg.get("enabled", True))
            if self.backend == "postgres"
            else int(bool(sink_cfg.get("enabled", True)))
        )
        sql = f"""
        INSERT INTO {tbl} (
            sink_name, namespace, sink_type, url, config_json, enabled, updated_at
        ) VALUES ({",".join(["?"] * 7)})
        ON CONFLICT (sink_name) DO UPDATE SET
            namespace = EXCLUDED.namespace,
            sink_type = EXCLUDED.sink_type,
            url = EXCLUDED.url,
            config_json = EXCLUDED.config_json,
            enabled = EXCLUDED.enabled,
            updated_at = EXCLUDED.updated_at
        """
        self._exec(
            sql,
            (
                name,
                str(sink_cfg.get("namespace", "*")),
                str(sink_cfg["type"]),
                str(sink_cfg.get("url", "")),
                json.dumps(persistable, sort_keys=True),
                enabled_val,
                now,
            ),
        )
        self.registered_sinks[name] = dict(sink_cfg)
        return dict(sink_cfg)

    def get_sink(self, sink_name: str) -> dict[str, Any] | None:
        tbl = self._table("notification_sinks")
        row = self._exec(f"SELECT * FROM {tbl} WHERE sink_name = ?", (sink_name,), fetch="one")
        hydrated = self._hydrate_sink(row)
        if hydrated is not None:
            self.registered_sinks[sink_name] = hydrated
            return hydrated
        return self.registered_sinks.get(sink_name)

    def list_sinks(self, allowed_namespaces: tuple[str, ...] | None = None) -> list[dict[str, Any]]:
        tbl = self._table("notification_sinks")
        rows = self._exec(f"SELECT * FROM {tbl} ORDER BY sink_name ASC", fetch="all")
        sinks_by_name: dict[str, dict[str, Any]] = {}
        for k, v in self.registered_sinks.items():
            sinks_by_name[k] = dict(v)
        for r in rows:
            hydrated = self._hydrate_sink(r)
            if hydrated:
                sinks_by_name[hydrated["name"]] = hydrated
        out: list[dict[str, Any]] = []
        for s in sinks_by_name.values():
            ns = s.get("namespace", "*")
            if allowed_namespaces and "*" not in allowed_namespaces and ns != "*" and ns not in allowed_namespaces:
                continue
            pub = dict(s)
            pub.pop("hmac_secret", None)
            pub.pop("smtp_password", None)
            pub["has_hmac_secret"] = bool(s.get("hmac_secret") or s.get("hmac_secret_env"))
            out.append(pub)
        return sorted(out, key=lambda item: item["name"])
