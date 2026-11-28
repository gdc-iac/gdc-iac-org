-- Copyright 2026 Google LLC
--
-- Licensed under the Apache License, Version 2.0 (the "License");
-- you may not use this file except in compliance with the License.
-- You may obtain a copy of the License at
--
--     http://www.apache.org/licenses/LICENSE-2.0
--
-- Unless required by applicable law or agreed to in writing, software
-- distributed under the License is distributed on an "AS IS" BASIS,
-- WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
-- See the License for the specific language governing permissions and
-- limitations under the License.

CREATE SCHEMA IF NOT EXISTS platform_jobs;

CREATE TABLE IF NOT EXISTS platform_jobs.job_definitions (
    job_id                  TEXT PRIMARY KEY,
    namespace               TEXT NOT NULL,
    persona                 TEXT NOT NULL CHECK (persona IN ('PA', 'AO')),
    job_class               TEXT NOT NULL CHECK (job_class IN ('batch', 'monitor', 'enforce')),
    template_name           TEXT NOT NULL DEFAULT 'gdc-standard-job-runner-v1',
    worker_image            TEXT NOT NULL,
    worker_mode             TEXT NOT NULL,
    enforcement_mode        TEXT NOT NULL DEFAULT 'audit' CHECK (enforcement_mode IN ('audit', 'dry-run', 'hitl-approval', 'auto-remediate')),
    schedule_cron           TEXT NOT NULL,
    timezone                TEXT NOT NULL DEFAULT 'UTC',
    suspended               BOOLEAN NOT NULL DEFAULT FALSE,
    concurrency_policy      TEXT NOT NULL DEFAULT 'Forbid' CHECK (concurrency_policy IN ('Forbid', 'Replace', 'Allow')),
    starting_deadline_secs  INTEGER NOT NULL DEFAULT 300,
    active_deadline_secs    INTEGER NOT NULL DEFAULT 900,
    sla_seconds             INTEGER NOT NULL DEFAULT 900,
    max_shards              INTEGER NOT NULL DEFAULT 10,
    parallelism             INTEGER NOT NULL DEFAULT 5,
    max_actions_per_run     INTEGER NOT NULL DEFAULT 5,
    cooldown_seconds        INTEGER NOT NULL DEFAULT 3600,
    consecutive_failures    INTEGER NOT NULL DEFAULT 0,
    circuit_breaker_open    BOOLEAN NOT NULL DEFAULT FALSE,
    gitops_managed          BOOLEAN NOT NULL DEFAULT FALSE,
    gitops_annotations      JSONB NOT NULL DEFAULT '{}'::jsonb,
    parameters              JSONB NOT NULL DEFAULT '{}'::jsonb,
    notification_sinks      JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_by              TEXT NOT NULL,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS platform_jobs.job_runs (
    run_id                  TEXT PRIMARY KEY,
    job_id                  TEXT NOT NULL REFERENCES platform_jobs.job_definitions(job_id) ON DELETE CASCADE,
    namespace               TEXT NOT NULL,
    engine_mode             TEXT NOT NULL CHECK (engine_mode IN ('argo', 'k8s-native')),
    engine_ref              TEXT NOT NULL,
    trigger_type            TEXT NOT NULL CHECK (trigger_type IN ('schedule', 'manual', 'backfill', 'self-heal')),
    window_start            TIMESTAMPTZ NOT NULL,
    window_end              TIMESTAMPTZ NOT NULL,
    shard_key               TEXT NOT NULL DEFAULT 'all',
    status                  TEXT NOT NULL CHECK (status IN ('Pending', 'Running', 'Succeeded', 'Failed', 'TimedOut', 'Cancelled', 'AwaitingApproval')),
    attempt                 INTEGER NOT NULL DEFAULT 1,
    exit_code               INTEGER,
    artifact_uri            TEXT,
    summary_json            JSONB NOT NULL DEFAULT '{}'::jsonb,
    requested_by            TEXT NOT NULL DEFAULT 'system',
    started_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at             TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_job_runs_job_status
    ON platform_jobs.job_runs (job_id, status, started_at DESC);

CREATE TABLE IF NOT EXISTS platform_jobs.watermarks (
    job_id                  TEXT NOT NULL,
    shard_key               TEXT NOT NULL DEFAULT 'all',
    last_window_end         TIMESTAMPTZ NOT NULL,
    last_object_uri         TEXT,
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (job_id, shard_key)
);

CREATE TABLE IF NOT EXISTS platform_jobs.enforcement_findings (
    finding_id              TEXT PRIMARY KEY,
    run_id                  TEXT NOT NULL,
    job_id                  TEXT NOT NULL,
    namespace               TEXT NOT NULL,
    target_kind             TEXT NOT NULL,
    target_namespace        TEXT NOT NULL,
    target_name             TEXT NOT NULL,
    target_resource_version TEXT NOT NULL,
    rule_id                 TEXT NOT NULL,
    severity                TEXT NOT NULL CHECK (severity IN ('info', 'warning', 'high', 'critical')),
    planned_patch_json      JSONB NOT NULL DEFAULT '{}'::jsonb,
    planned_patch_sha256    TEXT NOT NULL,
    snapshot_uri            TEXT,
    status                  TEXT NOT NULL CHECK (status IN ('open', 'pending_approval', 'approved', 'rejected', 'remediated', 'rolled_back', 'suppressed')),
    requested_by            TEXT NOT NULL,
    remediated_at           TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_enforcement_findings_target
    ON platform_jobs.enforcement_findings (target_kind, target_namespace, target_name, created_at DESC);

CREATE TABLE IF NOT EXISTS platform_jobs.remediation_approvals (
    approval_id             TEXT PRIMARY KEY,
    finding_id              TEXT NOT NULL REFERENCES platform_jobs.enforcement_findings(finding_id) ON DELETE CASCADE,
    job_id                  TEXT NOT NULL,
    requester               TEXT NOT NULL,
    approver                TEXT NOT NULL,
    decision                TEXT NOT NULL CHECK (decision IN ('approved', 'rejected', 'rolled_back')),
    reason                  TEXT NOT NULL,
    planned_patch_sha256    TEXT NOT NULL,
    target_resource_version TEXT NOT NULL,
    expires_at              TIMESTAMPTZ NOT NULL,
    decided_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS platform_jobs.notification_outbox (
    outbox_id               TEXT PRIMARY KEY,
    event_id                TEXT NOT NULL,
    dedup_key               TEXT NOT NULL,
    sink_name               TEXT NOT NULL,
    sink_type               TEXT NOT NULL,
    namespace               TEXT NOT NULL,
    job_id                  TEXT NOT NULL,
    event_type              TEXT NOT NULL,
    severity                TEXT NOT NULL,
    payload_json            JSONB NOT NULL,
    status                  TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'delivered', 'deduplicated', 'suppressed_quiet_hours', 'dead_letter')),
    attempts                INTEGER NOT NULL DEFAULT 0,
    next_retry_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_status_code        INTEGER,
    last_error              TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    delivered_at            TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_notification_outbox_pending
    ON platform_jobs.notification_outbox (status, next_retry_at)
    WHERE status = 'pending';

CREATE TABLE IF NOT EXISTS platform_jobs.notification_sinks (
    sink_name               TEXT PRIMARY KEY,
    namespace               TEXT NOT NULL,
    sink_type               TEXT NOT NULL,
    url                     TEXT NOT NULL,
    config_json             JSONB NOT NULL DEFAULT '{}'::jsonb,
    enabled                 BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
