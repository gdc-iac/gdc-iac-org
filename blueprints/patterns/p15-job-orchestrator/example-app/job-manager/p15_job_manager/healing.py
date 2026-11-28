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
"""Two-Layer Self-Healing, Bounded Enforcement, Cryptographic TOCTOU & Four-Eyes Gate (`REQ-JOB-003`, `REQ-HEAL-001`–`004`)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Callable
import uuid

_COMMON_PARENT = str(Path(__file__).resolve().parents[2])
if _COMMON_PARENT not in sys.path:
    sys.path.insert(0, _COMMON_PARENT)

from common.storage import DualModeStorageAdapter  # noqa: E402
from .config import ControlPlaneConfig
from .cron_utils import normalize_utc_iso
from .ledger import LedgerStore
from .metrics import MetricsRegistry
from .notifications import JobNotificationEvent, NotificationRouter
from .security import AuthPrincipal, AuthorizationError

NON_RETRYABLE_EXIT_CODES = frozenset({2})


class TOCTOUConflictError(Exception):
    """Raised (`409 Conflict`) when a target mutated between enforcement planning and HITL approval."""


def compute_retry_decision(
    exit_code: int,
    attempt: int,
    max_attempts: int = 4,
    base_backoff_seconds: int = 15,
    max_backoff_seconds: int = 600,
) -> tuple[bool, int, str]:
    """Evaluate Layer 1A retry eligibility (`REQ-HEAL-001`): abort immediately on exit code `2`."""
    if exit_code == 0:
        return False, 0, "succeeded"
    if exit_code in NON_RETRYABLE_EXIT_CODES:
        return False, 0, f"non_retryable_exit_code_{exit_code}"
    if attempt >= max_attempts:
        return False, 0, "retry_budget_exhausted"
    delay = min(max_backoff_seconds, base_backoff_seconds * (2 ** max(0, attempt - 1)))
    return True, int(delay), "transient_error_backoff"


def compute_patch_sha256(planned_patch: dict[str, Any], target_resource_version: str) -> str:
    """Compute deterministic SHA-256 digest binding `planned_patch` + `target_resource_version`."""
    canonical = json.dumps(
        {
            "patch": planned_patch,
            "target_resource_version": str(target_resource_version),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


class SelfHealingAndEnforcementEngine:
    """Coordinates Layer 1 execution self-healing and Layer 2 bounded target-resource remediation."""

    def __init__(
        self,
        config: ControlPlaneConfig,
        ledger: LedgerStore,
        storage: DualModeStorageAdapter,
        metrics: MetricsRegistry,
        notifier: NotificationRouter,
        target_inspector: Callable[[str, str, str], dict[str, Any]] | None = None,
        target_mutator: Callable[[str, str, str, dict[str, Any]], dict[str, Any]] | None = None,
    ) -> None:
        self.config = config
        self.ledger = ledger
        self.storage = storage
        self.metrics = metrics
        self.notifier = notifier
        # Pluggable KRM target state inspector & mutator (mockable in unit tests; K8s API in cluster)
        self._live_targets: dict[tuple[str, str, str], dict[str, Any]] = {}
        self._target_inspector = target_inspector or self._default_inspect_target
        self._target_mutator = target_mutator or self._default_mutate_target

    def register_mock_target(self, kind: str, namespace: str, name: str, state: dict[str, Any]) -> None:
        self._live_targets[(kind, namespace, name)] = json.loads(json.dumps(state))

    def _default_inspect_target(self, kind: str, namespace: str, name: str) -> dict[str, Any]:
        cur = self._live_targets.get((kind, namespace, name))
        if cur is None:
            return {
                "kind": kind,
                "metadata": {"name": name, "namespace": namespace, "resourceVersion": "1", "labels": {}},
            }
        return json.loads(json.dumps(cur))

    def _default_mutate_target(
        self, kind: str, namespace: str, name: str, patch: dict[str, Any]
    ) -> dict[str, Any]:
        cur = self._default_inspect_target(kind, namespace, name)
        meta = cur.setdefault("metadata", {})
        cur_rv = int(str(meta.get("resourceVersion", "1")))
        if "labels" in patch.get("metadata", {}):
            meta.setdefault("labels", {}).update(patch["metadata"]["labels"])
        if "annotations" in patch.get("metadata", {}):
            meta.setdefault("annotations", {}).update(patch["metadata"]["annotations"])
        if "restore_snapshot" in patch:
            restored = json.loads(json.dumps(patch["restore_snapshot"]))
            restored.setdefault("metadata", {})["resourceVersion"] = str(cur_rv + 1)
            self._live_targets[(kind, namespace, name)] = restored
            return restored
        meta["resourceVersion"] = str(cur_rv + 1)
        self._live_targets[(kind, namespace, name)] = cur
        return cur

    # -------------------------------------------------------------------------
    # Layer 1: Execution Outcome, Reaper & Consecutive-Failure Circuit Breaker
    # -------------------------------------------------------------------------
    def record_run_outcome(
        self,
        job_id: str,
        run_id: str,
        exit_code: int,
        summary: dict[str, Any] | None = None,
        artifact_uri: str | None = None,
        now_utc: datetime | None = None,
    ) -> dict[str, Any]:
        """Update run status, retry transient errors, or open circuit breaker after M failures."""
        when = (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
        now_iso = normalize_utc_iso(when)
        job = self.ledger.get_job_definition(job_id)
        run = self.ledger.get_job_run(run_id)
        if not job or not run:
            raise KeyError(f"Unknown job/run: {job_id}/{run_id}")

        attempt = int(run.get("attempt", 1))
        if exit_code == 0:
            updated_run = self.ledger.upsert_job_run(
                {
                    **run,
                    "status": "Succeeded",
                    "exit_code": 0,
                    "artifact_uri": artifact_uri or run.get("artifact_uri"),
                    "summary_json": summary or {},
                    "finished_at": now_iso,
                }
            )
            was_failing = int(job.get("consecutive_failures", 0)) > 0 or bool(job.get("circuit_breaker_open"))
            job["consecutive_failures"] = 0
            job["circuit_breaker_open"] = False
            self.ledger.upsert_job_definition(job)
            self.metrics.set_circuit_breaker(job["namespace"], job_id, False)
            self.metrics.record_job_run(
                job["namespace"],
                job_id,
                job["job_class"],
                job["persona"],
                "Succeeded",
                run["trigger_type"],
                finished_epoch=when.timestamp(),
            )
            if was_failing:
                self.notifier.enqueue_event(
                    JobNotificationEvent(
                        event_id=f"evt-{uuid.uuid4().hex[:12]}",
                        timestamp_utc=now_iso,
                        event_type="OnRecovery",
                        severity="info",
                        persona=job["persona"],
                        namespace=job["namespace"],
                        job_name=job_id,
                        run_id=run_id,
                        summary=f"Job '{job_id}' recovered and succeeded.",
                        details={"attempt": attempt},
                        artifact_uri=updated_run.get("artifact_uri") or "",
                    ),
                    sink_names=job.get("notification_sinks"),
                    now_utc=when,
                )
            return {"run": updated_run, "retried": False, "circuit_breaker_open": False}

        should_retry, backoff_secs, reason = compute_retry_decision(exit_code=exit_code, attempt=attempt)
        if should_retry:
            next_run = self.ledger.upsert_job_run(
                {
                    **run,
                    "status": "Running",
                    "attempt": attempt + 1,
                    "exit_code": exit_code,
                    "summary_json": {"retry_reason": reason, "backoff_seconds": backoff_secs},
                }
            )
            self.metrics.inc_self_heal(job["namespace"], job_id, "layer1", "transient_retry")
            return {
                "run": next_run,
                "retried": True,
                "backoff_seconds": backoff_secs,
                "circuit_breaker_open": bool(job.get("circuit_breaker_open")),
            }

        # Non-retryable or exhausted retry budget -> Failed
        failed_run = self.ledger.upsert_job_run(
            {
                **run,
                "status": "Failed",
                "exit_code": exit_code,
                "artifact_uri": artifact_uri or run.get("artifact_uri"),
                "summary_json": {**(summary or {}), "failure_reason": reason},
                "finished_at": now_iso,
            }
        )
        self.metrics.record_job_run(
            job["namespace"], job_id, job["job_class"], job["persona"], "Failed", run["trigger_type"]
        )

        prev_circuit_open = bool(job.get("circuit_breaker_open"))
        consec = int(job.get("consecutive_failures", 0)) + 1
        job["consecutive_failures"] = consec
        threshold = self.config.consecutive_failure_threshold

        if consec >= threshold and not prev_circuit_open:
            job["circuit_breaker_open"] = True
            # Suspend noisy failing batch jobs automatically while letting critical dead-man monitors probe
            if job["job_class"] == "batch":
                job["suspended"] = True
            self.ledger.upsert_job_definition(job)
            self.metrics.set_circuit_breaker(job["namespace"], job_id, True)
            self.notifier.enqueue_event(
                JobNotificationEvent(
                    event_id=f"evt-{uuid.uuid4().hex[:12]}",
                    timestamp_utc=now_iso,
                    event_type="OnCircuitBreakerOpen",
                    severity="critical",
                    persona=job["persona"],
                    namespace=job["namespace"],
                    job_name=job_id,
                    run_id=run_id,
                    summary=(
                        f"Circuit breaker OPEN for '{job_id}' after {consec} consecutive failures "
                        f"(reason={reason})."
                    ),
                    details={"consecutive_failures": consec, "suspended": job["suspended"]},
                ),
                sink_names=job.get("notification_sinks"),
                error_signature="circuit_open",
                now_utc=when,
            )
        else:
            self.ledger.upsert_job_definition(job)
            if not prev_circuit_open:
                self.notifier.enqueue_event(
                    JobNotificationEvent(
                        event_id=f"evt-{uuid.uuid4().hex[:12]}",
                        timestamp_utc=now_iso,
                        event_type="OnFailure",
                        severity="high",
                        persona=job["persona"],
                        namespace=job["namespace"],
                        job_name=job_id,
                        run_id=run_id,
                        summary=f"Job '{job_id}' run '{run_id}' failed with exit code {exit_code} ({reason}).",
                        details={"exit_code": exit_code, "attempt": attempt, "reason": reason},
                    ),
                    sink_names=job.get("notification_sinks"),
                    error_signature=f"exit_{exit_code}_{reason}",
                    now_utc=when,
                )

        return {"run": failed_run, "retried": False, "circuit_breaker_open": bool(job["circuit_breaker_open"])}

    def reap_stuck_runs(self, now_utc: datetime | None = None) -> list[dict[str, Any]]:
        """Detect hung `Running`/`Pending` runs exceeding `active_deadline_secs` (`REQ-HEAL-001`)."""
        when = (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
        now_iso = normalize_utc_iso(when)
        reaped: list[dict[str, Any]] = []
        for run in self.ledger.list_job_runs(limit=200):
            if run["status"] not in ("Running", "Pending"):
                continue
            job = self.ledger.get_job_definition(run["job_id"])
            if not job:
                continue
            started_dt = datetime.fromisoformat(run["started_at"].replace("Z", "+00:00"))
            deadline_secs = int(job.get("active_deadline_secs", 900))
            if (when - started_dt).total_seconds() > deadline_secs:
                updated = self.ledger.upsert_job_run(
                    {
                        **run,
                        "status": "TimedOut",
                        "summary_json": {
                            **run.get("summary_json", {}),
                            "reaped_reason": f"Exceeded activeDeadlineSeconds ({deadline_secs}s)",
                        },
                        "finished_at": now_iso,
                    }
                )
                self.metrics.inc_self_heal(job["namespace"], job["job_id"], "layer1", "zombie_reaped")
                self.notifier.enqueue_event(
                    JobNotificationEvent(
                        event_id=f"evt-{uuid.uuid4().hex[:12]}",
                        timestamp_utc=now_iso,
                        event_type="OnSLAExceeded",
                        severity="high",
                        persona=job["persona"],
                        namespace=job["namespace"],
                        job_name=job["job_id"],
                        run_id=run["run_id"],
                        summary=f"Zombie/hung run '{run['run_id']}' terminated after exceeding {deadline_secs}s deadline.",
                        details={"active_deadline_secs": deadline_secs},
                    ),
                    sink_names=job.get("notification_sinks"),
                    error_signature="active_deadline_exceeded",
                    now_utc=when,
                )
                reaped.append(updated)
        return reaped

    # -------------------------------------------------------------------------
    # Layer 2: Target-Resource Enforcement, TOCTOU, Four-Eyes & Rollback
    # -------------------------------------------------------------------------
    def _save_snapshot(self, namespace: str, kind: str, name: str, rv: str, state: dict[str, Any]) -> str:
        snap_key = f"snapshots/{namespace}/{kind.lower()}-{name}-rv{rv}.json"
        return self.storage.put_json(snap_key, state, redact=True)

    def evaluate_violations(
        self,
        job_id: str,
        run_id: str,
        violations: list[dict[str, Any]],
        requested_by: str = "scheduler",
        now_utc: datetime | None = None,
    ) -> dict[str, Any]:
        """Process detected policy violations through the 3-tier enforcement maturity ladder."""
        when = (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
        now_iso = normalize_utc_iso(when)
        job = self.ledger.get_job_definition(job_id)
        if not job:
            raise KeyError(f"Unknown job '{job_id}'")

        mode = job.get("enforcement_mode", "audit")
        max_actions = int(job.get("max_actions_per_run", self.config.default_max_actions_per_run))
        cooldown_secs = int(job.get("cooldown_seconds", self.config.default_cooldown_seconds))

        actions_taken = 0
        findings_out: list[dict[str, Any]] = []
        escalated_count = 0
        tug_of_war_tripped = False

        for v in violations:
            t_kind = str(v["target_kind"])
            t_ns = str(v.get("target_namespace") or job["namespace"])
            t_name = str(v["target_name"])
            rule_id = str(v.get("rule_id") or "P15-POLICY-001")
            severity = str(v.get("severity") or "warning")
            planned_patch = dict(v.get("planned_patch") or {})

            live_state = self._target_inspector(t_kind, t_ns, t_name)
            t_rv = str(
                v.get("target_resource_version")
                or live_state.get("metadata", {}).get("resourceVersion", "1")
            )
            patch_sha = compute_patch_sha256(planned_patch, t_rv)
            finding_id = str(v.get("finding_id") or f"fnd-{uuid.uuid4().hex[:12]}")

            self.metrics.inc_violation(job["namespace"], job_id, severity, mode)

            # Check GitOps Tug-of-War (`< 3600s` repeat drift after a prior remediation!) & Cooldown
            prior = self.ledger.list_findings(target_ref=(t_kind, t_ns, t_name))
            recent_remediated = [
                p
                for p in prior
                if p["status"] == "remediated"
                and p.get("remediated_at")
                and (
                    when - datetime.fromisoformat(p["remediated_at"].replace("Z", "+00:00"))
                ).total_seconds()
                < 3600
            ]

            if mode == "auto-remediate" and recent_remediated:
                if v.get("reverted_after_remediation", True):
                    # GitOps Tug-of-War Circuit Breaker! Downgrade job to `audit` immediately.
                    tug_of_war_tripped = True
                    mode = "audit"
                    job["enforcement_mode"] = "audit"
                    job["circuit_breaker_open"] = True
                    self.ledger.upsert_job_definition(job)
                    self.metrics.set_circuit_breaker(job["namespace"], job_id, True)
                    self.metrics.inc_self_heal(job["namespace"], job_id, "layer2", "tug_of_war_circuit_open")
                    self.notifier.enqueue_event(
                        JobNotificationEvent(
                            event_id=f"evt-{uuid.uuid4().hex[:12]}",
                            timestamp_utc=now_iso,
                            event_type="OnCircuitBreakerOpen",
                            severity="critical",
                            persona=job["persona"],
                            namespace=job["namespace"],
                            job_name=job_id,
                            run_id=run_id,
                            summary=(
                                f"GitOps tug-of-war detected on {t_kind}/{t_ns}/{t_name} (drifted again within <1h); "
                                f"job '{job_id}' automatically downgraded to 'audit' mode."
                            ),
                            details={"target": f"{t_kind}/{t_ns}/{t_name}", "rule_id": rule_id},
                        ),
                        sink_names=job.get("notification_sinks"),
                        error_signature=f"tug_of_war_{t_kind}_{t_ns}_{t_name}",
                        now_utc=when,
                    )

            # Check explicit per-resource cooldown (>1h custom cooldown windows)
            in_cooldown = any(
                p["status"] == "remediated"
                and p.get("remediated_at")
                and (
                    when - datetime.fromisoformat(p["remediated_at"].replace("Z", "+00:00"))
                ).total_seconds()
                < cooldown_secs
                for p in prior
            )

            if mode == "audit":
                f_rec = self.ledger.upsert_finding(
                    {
                        "finding_id": finding_id,
                        "run_id": run_id,
                        "job_id": job_id,
                        "namespace": job["namespace"],
                        "target_kind": t_kind,
                        "target_namespace": t_ns,
                        "target_name": t_name,
                        "target_resource_version": t_rv,
                        "rule_id": rule_id,
                        "severity": severity,
                        "planned_patch_json": planned_patch,
                        "planned_patch_sha256": patch_sha,
                        "status": "open",
                        "requested_by": requested_by,
                        "created_at": now_iso,
                    }
                )
                findings_out.append(f_rec)
                continue

            if mode in ("dry-run", "hitl-approval"):
                snap_uri = self._save_snapshot(job["namespace"], t_kind, t_name, t_rv, live_state)
                f_rec = self.ledger.upsert_finding(
                    {
                        "finding_id": finding_id,
                        "run_id": run_id,
                        "job_id": job_id,
                        "namespace": job["namespace"],
                        "target_kind": t_kind,
                        "target_namespace": t_ns,
                        "target_name": t_name,
                        "target_resource_version": t_rv,
                        "rule_id": rule_id,
                        "severity": severity,
                        "planned_patch_json": planned_patch,
                        "planned_patch_sha256": patch_sha,
                        "snapshot_uri": snap_uri,
                        "status": "pending_approval",
                        "requested_by": requested_by,
                        "created_at": now_iso,
                    }
                )
                findings_out.append(f_rec)
                self.notifier.enqueue_event(
                    JobNotificationEvent(
                        event_id=f"evt-{uuid.uuid4().hex[:12]}",
                        timestamp_utc=now_iso,
                        event_type="OnApprovalRequired",
                        severity="warning",
                        persona=job["persona"],
                        namespace=job["namespace"],
                        job_name=job_id,
                        run_id=run_id,
                        summary=f"HITL approval required for {t_kind}/{t_ns}/{t_name} ({rule_id}).",
                        details={"finding_id": finding_id, "planned_patch_sha256": patch_sha},
                        artifact_uri=snap_uri,
                    ),
                    sink_names=job.get("notification_sinks"),
                    error_signature=f"hitl_{finding_id}",
                    now_utc=when,
                )
                continue

            # mode == "auto-remediate"
            if in_cooldown or actions_taken >= max_actions:
                escalated_count += 1
                f_rec = self.ledger.upsert_finding(
                    {
                        "finding_id": finding_id,
                        "run_id": run_id,
                        "job_id": job_id,
                        "namespace": job["namespace"],
                        "target_kind": t_kind,
                        "target_namespace": t_ns,
                        "target_name": t_name,
                        "target_resource_version": t_rv,
                        "rule_id": rule_id,
                        "severity": severity,
                        "planned_patch_json": planned_patch,
                        "planned_patch_sha256": patch_sha,
                        "status": "open",
                        "requested_by": requested_by,
                        "created_at": now_iso,
                    }
                )
                findings_out.append(f_rec)
                continue

            snap_uri = self._save_snapshot(job["namespace"], t_kind, t_name, t_rv, live_state)
            self._target_mutator(t_kind, t_ns, t_name, planned_patch)
            actions_taken += 1
            self.metrics.inc_self_heal(job["namespace"], job_id, "layer2", "auto_remediated")
            f_rec = self.ledger.upsert_finding(
                {
                    "finding_id": finding_id,
                    "run_id": run_id,
                    "job_id": job_id,
                    "namespace": job["namespace"],
                    "target_kind": t_kind,
                    "target_namespace": t_ns,
                    "target_name": t_name,
                    "target_resource_version": t_rv,
                    "rule_id": rule_id,
                    "severity": severity,
                    "planned_patch_json": planned_patch,
                    "planned_patch_sha256": patch_sha,
                    "snapshot_uri": snap_uri,
                    "status": "remediated",
                    "requested_by": requested_by,
                    "remediated_at": now_iso,
                    "created_at": now_iso,
                }
            )
            findings_out.append(f_rec)

        if actions_taken > 0:
            self.notifier.enqueue_event(
                JobNotificationEvent(
                    event_id=f"evt-{uuid.uuid4().hex[:12]}",
                    timestamp_utc=now_iso,
                    event_type="OnAutoHealExecuted",
                    severity="warning",
                    persona=job["persona"],
                    namespace=job["namespace"],
                    job_name=job_id,
                    run_id=run_id,
                    summary=f"Auto-remediated {actions_taken} compliance violation(s); {escalated_count} capped/escalated.",
                    details={"actions_taken": actions_taken, "escalated_to_audit": escalated_count},
                ),
                sink_names=job.get("notification_sinks"),
                error_signature=f"autoheal_{run_id}",
                now_utc=when,
            )
        elif violations and mode == "audit" and not tug_of_war_tripped:
            self.notifier.enqueue_event(
                JobNotificationEvent(
                    event_id=f"evt-{uuid.uuid4().hex[:12]}",
                    timestamp_utc=now_iso,
                    event_type="OnViolationDetected",
                    severity="warning",
                    persona=job["persona"],
                    namespace=job["namespace"],
                    job_name=job_id,
                    run_id=run_id,
                    summary=f"Detected {len(violations)} compliance violation(s) in audit mode.",
                    details={"violation_count": len(violations)},
                ),
                sink_names=job.get("notification_sinks"),
                error_signature=f"audit_violations_{job_id}",
                now_utc=when,
            )

        if escalated_count > 0:
            self.notifier.enqueue_event(
                JobNotificationEvent(
                    event_id=f"evt-{uuid.uuid4().hex[:12]}",
                    timestamp_utc=now_iso,
                    event_type="OnViolationDetected",
                    severity="high",
                    persona=job["persona"],
                    namespace=job["namespace"],
                    job_name=job_id,
                    run_id=run_id,
                    summary=(
                        f"Blast-radius cap ({max_actions}) reached for '{job_id}'; "
                        f"{escalated_count} violation(s) downgraded to audit."
                    ),
                    details={"max_actions_per_run": max_actions, "escalated_count": escalated_count},
                ),
                sink_names=job.get("notification_sinks"),
                error_signature=f"blast_cap_{job_id}",
                now_utc=when,
            )

        return {
            "findings": findings_out,
            "actions_taken": actions_taken,
            "escalated_count": escalated_count,
            "tug_of_war_tripped": tug_of_war_tripped,
        }

    def decide_approval(
        self,
        finding_id: str,
        approver: AuthPrincipal,
        decision: str,
        reason: str,
        expected_patch_sha256: str | None = None,
        now_utc: datetime | None = None,
    ) -> dict[str, Any]:
        """Approve or reject a `pending_approval` finding with Four-Eyes + TOCTOU `409` checks."""
        if not reason or not reason.strip():
            raise ValueError("Approval/rejection reason is mandatory for audit trail")
        finding = self.ledger.get_finding(finding_id)
        if not finding:
            raise KeyError(f"Finding '{finding_id}' not found")
        approver.check_namespace_access(finding["namespace"], require_write=True)

        if finding["status"] != "pending_approval":
            raise TOCTOUConflictError(
                f"Finding '{finding_id}' is no longer pending approval (current status={finding['status']!r})"
            )

        when = (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
        now_iso = normalize_utc_iso(when)
        created_dt = datetime.fromisoformat(finding["created_at"].replace("Z", "+00:00"))
        expires_dt = created_dt + timedelta(seconds=self.config.approval_ttl_seconds)
        if when > expires_dt:
            raise TOCTOUConflictError(
                f"HITL approval window ({self.config.approval_ttl_seconds}s) expired; re-run enforcement plan"
            )

        if decision == "rejected":
            updated = self.ledger.upsert_finding({**finding, "status": "rejected"})
            audit = self.ledger.append_approval(
                {
                    "finding_id": finding_id,
                    "job_id": finding["job_id"],
                    "requester": finding["requested_by"],
                    "approver": approver.subject,
                    "decision": "rejected",
                    "reason": reason.strip(),
                    "planned_patch_sha256": finding["planned_patch_sha256"],
                    "target_resource_version": finding["target_resource_version"],
                    "expires_at": normalize_utc_iso(expires_dt),
                    "decided_at": now_iso,
                }
            )
            return {"finding": updated, "approval": audit}

        if decision != "approved":
            raise ValueError(f"Unsupported decision: {decision!r}")

        # Four-Eyes Dual Control (`REQ-HEAL-003`)
        if self.config.require_four_eyes_approval and approver.subject == finding["requested_by"]:
            raise AuthorizationError(
                "Four-eyes dual control violation: approver identity must differ from requester"
            )

        # Cryptographic TOCTOU Binding (`SHA-256` + live `resourceVersion`)
        if expected_patch_sha256 and expected_patch_sha256 != finding["planned_patch_sha256"]:
            raise TOCTOUConflictError("Caller-supplied planned_patch_sha256 does not match queued plan")

        live_state = self._target_inspector(
            finding["target_kind"], finding["target_namespace"], finding["target_name"]
        )
        live_rv = str(live_state.get("metadata", {}).get("resourceVersion", ""))
        live_sha = compute_patch_sha256(finding["planned_patch_json"], live_rv)
        if live_rv != finding["target_resource_version"] or live_sha != finding["planned_patch_sha256"]:
            raise TOCTOUConflictError(
                f"TOCTOU conflict: target {finding['target_kind']}/{finding['target_namespace']}/{finding['target_name']} "
                f"mutated after planning (expected resourceVersion={finding['target_resource_version']!r}, got {live_rv!r})"
            )

        self._target_mutator(
            finding["target_kind"],
            finding["target_namespace"],
            finding["target_name"],
            finding["planned_patch_json"],
        )
        self.metrics.inc_self_heal(finding["namespace"], finding["job_id"], "layer2", "hitl_remediated")
        updated = self.ledger.upsert_finding(
            {**finding, "status": "remediated", "remediated_at": now_iso}
        )
        audit = self.ledger.append_approval(
            {
                "finding_id": finding_id,
                "job_id": finding["job_id"],
                "requester": finding["requested_by"],
                "approver": approver.subject,
                "decision": "approved",
                "reason": reason.strip(),
                "planned_patch_sha256": finding["planned_patch_sha256"],
                "target_resource_version": finding["target_resource_version"],
                "expires_at": normalize_utc_iso(expires_dt),
                "decided_at": now_iso,
            }
        )
        return {"finding": updated, "approval": audit}

    def rollback_remediation(
        self, finding_id: str, actor: AuthPrincipal, reason: str, now_utc: datetime | None = None
    ) -> dict[str, Any]:
        """Execute 1-click rollback restoring the pre-action snapshot from Object Storage (`REQ-HEAL-003`)."""
        finding = self.ledger.get_finding(finding_id)
        if not finding:
            raise KeyError(f"Finding '{finding_id}' not found")
        actor.check_namespace_access(finding["namespace"], require_write=True)
        if finding["status"] != "remediated" or not finding.get("snapshot_uri"):
            raise ValueError(f"Finding '{finding_id}' has no remediated snapshot available for rollback")

        uri = str(finding["snapshot_uri"])
        prefix = f"{self.storage.uri_scheme}://{self.storage.bucket_name}/"
        obj_key = uri[len(prefix) :] if uri.startswith(prefix) else uri.split("/", 3)[-1]
        snapshot_state = self.storage.get_json(obj_key)

        restored = self._target_mutator(
            finding["target_kind"],
            finding["target_namespace"],
            finding["target_name"],
            {"restore_snapshot": snapshot_state},
        )
        when = (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
        now_iso = normalize_utc_iso(when)
        updated = self.ledger.upsert_finding({**finding, "status": "rolled_back"})
        audit = self.ledger.append_approval(
            {
                "finding_id": finding_id,
                "job_id": finding["job_id"],
                "requester": finding["requested_by"],
                "approver": actor.subject,
                "decision": "rolled_back",
                "reason": reason.strip() or "Operator snapshot rollback",
                "planned_patch_sha256": finding["planned_patch_sha256"],
                "target_resource_version": finding["target_resource_version"],
                "expires_at": now_iso,
                "decided_at": now_iso,
            }
        )
        self.metrics.inc_self_heal(finding["namespace"], finding["job_id"], "layer2", "snapshot_rollback")
        return {"finding": updated, "approval": audit, "restored_target": restored}
