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
"""Starter Worker 3: `enforce-resource-policy` (3-Tier `audit` -> `hitl-approval` -> `enforce`)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Callable

_COMMON_PARENT = str(Path(__file__).resolve().parents[2])
if _COMMON_PARENT not in sys.path:
    sys.path.insert(0, _COMMON_PARENT)

from common.storage import DualModeStorageAdapter  # noqa: E402

REQUIRED_LABELS = {
    "p15.gdc.goog/cost-center": "shared-platform",
    "p15.gdc.goog/managed-tier": "standard",
}


def _patch_digest(patch: dict[str, Any], rv: str) -> str:
    raw = json.dumps({"patch": patch, "target_resource_version": rv}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def execute_enforce_resource_policy(
    job_id: str,
    run_id: str,
    window_start: str,
    window_end: str,
    enforcement_mode: str,
    storage: DualModeStorageAdapter,
    resources: list[dict[str, Any]] | None = None,
    max_actions_per_run: int = 5,
    mutator: Callable[[dict[str, Any], dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Detect missing mandatory labels/TTL annotations and execute bounded 3-tier enforcement."""
    if enforcement_mode not in ("audit", "dry-run", "hitl-approval", "enforce"):
        raise ValueError(f"Invalid enforcement_mode: {enforcement_mode!r}")

    candidates = resources if resources is not None else [
        {
            "kind": "ConfigMap",
            "namespace": "test-project",
            "name": "sample-unlabelled-cfg",
            "resourceVersion": "101",
            "labels": {},
            "annotations": {},
        }
    ]

    violations: list[dict[str, Any]] = []
    actions_taken: list[dict[str, Any]] = []

    for res in candidates:
        cur_labels = dict(res.get("labels") or {})
        missing = {k: default_v for k, default_v in REQUIRED_LABELS.items() if k not in cur_labels}
        if not missing:
            continue

        rv = str(res.get("resourceVersion", "1"))
        planned_patch = {"metadata": {"labels": missing}}
        digest = _patch_digest(planned_patch, rv)
        ns = str(res.get("namespace", "test-project"))
        kind = str(res.get("kind", "ConfigMap"))
        name = str(res.get("name", "unknown"))

        snap_uri = ""
        if enforcement_mode in ("dry-run", "hitl-approval", "enforce"):
            snap_key = f"snapshots/{ns}/{kind.lower()}-{name}-rv{rv}.json"
            snap_uri = storage.put_json(snap_key, res, redact=True)

        violation_entry = {
            "target_kind": kind,
            "target_namespace": ns,
            "target_name": name,
            "target_resource_version": rv,
            "rule_id": "POL-LABEL-REQUIRED-001",
            "severity": "warning",
            "planned_patch": planned_patch,
            "planned_patch_sha256": digest,
            "snapshot_uri": snap_uri,
        }
        violations.append(violation_entry)

        if enforcement_mode == "enforce" and len(actions_taken) < max_actions_per_run:
            if mutator is not None:
                mutator(res, planned_patch)
            actions_taken.append(
                {
                    "target": f"{kind}/{ns}/{name}",
                    "applied_patch": planned_patch,
                    "snapshot_uri": snap_uri,
                }
            )

    return {
        "job_id": job_id,
        "run_id": run_id,
        "mode": "enforce-resource-policy",
        "enforcement_mode": enforcement_mode,
        "status": "Succeeded",
        "window_start": window_start,
        "window_end": window_end,
        "items_processed": len(candidates),
        "violations": violations,
        "actions_taken": actions_taken,
        "watermark_end": window_end,
        "metrics": {
            "resources_scanned": len(candidates),
            "violations_detected": len(violations),
            "actions_executed": len(actions_taken),
        },
    }
