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
"""Example Custom Job Worker: `inventory-audit-report` (`gdc-standard-job-runner-v1`).

Demonstrates how an Application Operator (AO) or platform team packages a domain-specific
Python workload that:
  1. Accesses live Kubernetes resources (`Service` objects in its namespace) using its
     attached Kubernetes ServiceAccount token (`/var/run/secrets/kubernetes.io/serviceaccount/token`)
     and cluster CA bundle (falling back cleanly to a deterministic local fixture when run
     outside a cluster for local testing).
  2. Persists WAL-first and canonical `result.json` bundles to Object Storage (`s3://` on
     GDC-ag via `Secret/p15-s3-credentials` + `AWS_CA_BUNDLE`, or `gs://` on GKE Stepping-Stone
     via Workload Identity) with automatic pre-archive secret redaction (`[REDACTED_TOKEN]`).
  3. Enforces exit-code `2` non-retryable configuration validation across both Profile B
     (`k8s-native`) and Profile A (`argo`).
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import ssl
import sys
import time
from typing import Any, Callable
import urllib.request

# Support both containerized layout (`/app/common`) and local repo layout (`../../example-app/common`)
_HERE = Path(__file__).resolve()
for _parent in _HERE.parents:
    for _candidate in (_parent, _parent / "example-app"):
        if (_candidate / "common").is_dir() and str(_candidate) not in sys.path:
            sys.path.insert(0, str(_candidate))

from common.redaction import redact_payload  # noqa: E402
from common.storage import DualModeStorageAdapter, build_job_artifact_key  # noqa: E402

DEFAULT_RESULT_PATH = Path("/tmp/job-out/result.json")
SUPPORTED_MODES = ("inventory-audit-report",)
SA_TOKEN_PATH = Path("/var/run/secrets/kubernetes.io/serviceaccount/token")
SA_CA_PATH = Path("/var/run/secrets/kubernetes.io/serviceaccount/ca.crt")
SA_NS_PATH = Path("/var/run/secrets/kubernetes.io/serviceaccount/namespace")


def _window_slug(window_start: str, window_end: str) -> str:
    digest = hashlib.sha256(f"{window_start}..{window_end}".encode("utf-8")).hexdigest()[:16]
    safe_end = window_end.replace(":", "").replace("-", "")
    return f"{safe_end}-{digest}"


def discover_live_k8s_services(namespace: str) -> list[dict[str, Any]] | None:
    """Query live namespace `Service` resources via the pod's attached ServiceAccount token.

    Requires `services: [get, list]` on the attached ServiceAccount (granted by default to
    `p15-ao-worker-sa` via `Role/p15-ao-worker-role`). Returns `None` when running locally
    outside Kubernetes so local smoke tests fall back cleanly to the deterministic fixture.
    """
    if not SA_TOKEN_PATH.is_file() or not SA_CA_PATH.is_file():
        return None
    k8s_host = os.getenv("KUBERNETES_SERVICE_HOST", "").strip()
    k8s_port = os.getenv("KUBERNETES_SERVICE_PORT", "443").strip()
    if not k8s_host:
        return None

    token = SA_TOKEN_PATH.read_text(encoding="utf-8").strip()
    pod_ns = SA_NS_PATH.read_text(encoding="utf-8").strip() if SA_NS_PATH.is_file() else namespace
    target_ns = namespace or pod_ns
    host_fmt = f"[{k8s_host}]" if ":" in k8s_host else k8s_host
    url = f"https://{host_fmt}:{k8s_port}/api/v1/namespaces/{target_ns}/services"

    ctx = ssl.create_default_context(cafile=str(SA_CA_PATH))
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        sys.stderr.write(f"Warning: Kubernetes API Service discovery skipped ({exc}); using fixture.\n")
        return None

    assets: list[dict[str, Any]] = []
    for svc in payload.get("items", []):
        meta = svc.get("metadata") or {}
        labels = meta.get("labels") or {}
        annotations = meta.get("annotations") or {}
        owner = str(
            labels.get("owner")
            or labels.get("app.kubernetes.io/part-of")
            or ""
        ).strip()
        tls_days_raw = annotations.get("p15.gdc.goog/tls-days-left", "90")
        try:
            tls_days = int(tls_days_raw)
        except ValueError:
            tls_days = 90
        assets.append(
            {
                "asset_id": str(meta.get("name") or "unknown-service"),
                "owner_label": owner,
                "tls_days_left": tls_days,
                "cluster_ip": str((svc.get("spec") or {}).get("clusterIP") or ""),
            }
        )
    return assets or None


def run_inventory_audit_job(
    mode: str,
    job_id: str,
    run_id: str,
    window_start: str = "",
    window_end: str = "",
    shard_key: str = "all",
    sink_uri: str = "",
    enforcement_mode: str = "audit",
    namespace: str | None = None,
    result_path: Path = DEFAULT_RESULT_PATH,
    storage: DualModeStorageAdapter | None = None,
    k8s_service_loader: Callable[[str], list[dict[str, Any]] | None] | None = None,
) -> dict[str, Any]:
    """Execute the `inventory-audit-report` custom worker contract."""
    if mode not in SUPPORTED_MODES:
        raise ValueError(
            f"Unsupported custom worker --mode {mode!r}; expected one of {list(SUPPORTED_MODES)}"
        )
    if not job_id.strip() or not run_id.strip():
        raise ValueError("--job-id and --run-id must be non-empty")

    t0 = time.monotonic()
    now = datetime.now(timezone.utc)
    w_end = window_end.strip() or now.strftime("%Y-%m-%dT%H:%M:%SZ")
    w_start = window_start.strip() or (now - timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M:%SZ")
    ns = namespace or os.getenv("NAMESPACE", "test-project")

    store = storage or DualModeStorageAdapter(
        bucket_name=sink_uri or os.getenv("BUCKET_NAME", "p15-jobs-ledger")
    )

    # Attempt live in-cluster Kubernetes API discovery via the attached ServiceAccount;
    # fall back cleanly to the deterministic local fixture when run outside a cluster.
    loader = k8s_service_loader or discover_live_k8s_services
    live_assets = loader(ns)
    if live_assets is not None:
        inventory_slice = live_assets
        data_source = "kubernetes-api"
    else:
        inventory_slice = [
            {"asset_id": f"{shard_key}-svc-payments", "owner_label": "team-core", "tls_days_left": 142},
            {"asset_id": f"{shard_key}-svc-reporting", "owner_label": "team-data", "tls_days_left": 89},
            {"asset_id": f"{shard_key}-svc-legacy", "owner_label": "", "tls_days_left": 12},
        ]
        data_source = "local-fixture"

    violations: list[dict[str, Any]] = []
    compliant = 0
    for item in inventory_slice:
        missing_owner = not item.get("owner_label")
        expiring_tls = int(item.get("tls_days_left", 90)) < 30
        if missing_owner or expiring_tls:
            violations.append(
                {
                    "target_kind": "Service",
                    "target_namespace": ns,
                    "target_name": item["asset_id"],
                    "rule_id": "CUSTOM-INV-001",
                    "severity": "medium" if not expiring_tls else "high",
                    "missing_owner_label": missing_owner,
                    "tls_days_left": int(item.get("tls_days_left", 90)),
                }
            )
        else:
            compliant += 1

    # 1. Write immutable WAL bundle to Object Storage FIRST (`REQ-HEAL-002` failover safety).
    slug = _window_slug(w_start, w_end)
    wal_key = f"wal/inventory/{job_id}/{shard_key}/{slug}.json"
    wal_doc = {
        "idempotency_key": f"{job_id}:{shard_key}:{w_start}:{w_end}",
        "job_id": job_id,
        "run_id": run_id,
        "mode": mode,
        "namespace": ns,
        "shard_key": shard_key,
        "data_source": data_source,
        "inventory_items_audited": len(inventory_slice),
        "compliant_count": compliant,
        "non_compliant_count": len(violations),
        # Deliberate synthetic header string to prove pre-archive redaction strips secrets!
        "diagnostic_trace": "checked endpoint with Authorization: Bearer synthetic-demo-token-do-not-persist",
    }
    wal_uri = store.put_json(wal_key, wal_doc, redact=True)

    result: dict[str, Any] = {
        "job_id": job_id,
        "run_id": run_id,
        "mode": mode,
        "status": "Succeeded",
        "namespace": ns,
        "shard_key": shard_key,
        "data_source": data_source,
        "audited_resources": [item["asset_id"] for item in inventory_slice],
        "enforcement_mode": enforcement_mode,
        "window_start": w_start,
        "window_end": w_end,
        "items_processed": len(inventory_slice),
        "violations": violations,
        "actions_taken": [],
        "watermark_end": w_end,
        "wal_uri": wal_uri,
        "metrics": {
            "inventory_items_audited": len(inventory_slice),
            "compliant_count": compliant,
            "non_compliant_count": len(violations),
            "compliance_pct": round((compliant / len(inventory_slice)) * 100.0, 2)
            if inventory_slice
            else 100.0,
            "duration_ms": round((time.monotonic() - t0) * 1000.0, 2),
        },
        "notes": wal_doc["diagnostic_trace"],
    }

    # 2. Persist redacted canonical result to `/tmp/job-out/result.json` and Object Storage.
    sanitized = redact_payload(result)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    obj_key = build_job_artifact_key(ns, job_id, run_id, "result.json", ts=now)
    sanitized["artifact_uri"] = store.put_json(obj_key, sanitized, redact=True)
    result_path.write_text(json.dumps(sanitized, sort_keys=True, indent=2), encoding="utf-8")
    return sanitized


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Pattern 15 Example Custom Job Worker (inventory-audit-report)"
    )
    parser.add_argument("--mode", required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--window-start", default="")
    parser.add_argument("--window-end", default="")
    parser.add_argument("--shard-key", default="all")
    parser.add_argument("--sink-uri", default="")
    parser.add_argument(
        "--enforcement-mode",
        default="audit",
        choices=["audit", "dry-run", "hitl-approval", "enforce"],
    )
    parser.add_argument("--output-file", default=str(DEFAULT_RESULT_PATH))

    try:
        args = parser.parse_args(argv)
        res = run_inventory_audit_job(
            mode=args.mode,
            job_id=args.job_id,
            run_id=args.run_id,
            window_start=args.window_start,
            window_end=args.window_end,
            shard_key=args.shard_key,
            sink_uri=args.sink_uri,
            enforcement_mode=args.enforcement_mode,
            result_path=Path(args.output_file),
        )
        print(
            json.dumps(
                {
                    "status": res["status"],
                    "data_source": res["data_source"],
                    "artifact_uri": res["artifact_uri"],
                    "wal_uri": res["wal_uri"],
                    "metrics": res["metrics"],
                }
            )
        )
        return 0
    except ValueError as exc:
        # Exit code 2 signals a non-retryable configuration error (`REQ-HEAL-001`)
        sys.stderr.write(f"Configuration error (non-retryable): {exc}\n")
        return 2


if __name__ == "__main__":
    sys.exit(main())
