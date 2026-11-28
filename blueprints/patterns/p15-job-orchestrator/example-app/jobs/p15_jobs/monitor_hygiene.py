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
"""Starter Worker 2: `monitor-platform-hygiene` (PSS, Certificate Expiry & Storage/DB Health)."""

from __future__ import annotations

from typing import Any


def execute_monitor_platform_hygiene(
    job_id: str,
    run_id: str,
    window_start: str,
    window_end: str,
    targets: list[dict[str, Any]] | None = None,
    cert_warn_days: int = 30,
) -> dict[str, Any]:
    """Evaluate platform & namespace hygiene probes and produce structured observation metrics."""
    observed = targets if targets is not None else [
        {
            "kind": "Namespace",
            "name": "test-project",
            "pss_enforce": "restricted",
            "cert_days_remaining": 75,
            "healthy": True,
        },
        {
            "kind": "DBCluster",
            "name": "p15-jobs-db",
            "auto_failover_enabled": True,
            "cert_days_remaining": 90,
            "healthy": True,
        },
    ]

    findings: list[dict[str, Any]] = []
    healthy_count = 0
    min_cert_days = 9999

    for item in observed:
        days = int(item.get("cert_days_remaining", 365))
        min_cert_days = min(min_cert_days, days)
        if item.get("healthy", True):
            healthy_count += 1
        else:
            findings.append(
                {
                    "target_kind": item.get("kind", "Resource"),
                    "target_name": item.get("name", "unknown"),
                    "rule_id": "HYG-HEALTH-001",
                    "severity": "high",
                    "detail": "Target reported unhealthy status",
                }
            )
        if item.get("kind") == "Namespace" and item.get("pss_enforce") != "restricted":
            findings.append(
                {
                    "target_kind": "Namespace",
                    "target_name": item.get("name", "unknown"),
                    "rule_id": "HYG-PSS-001",
                    "severity": "warning",
                    "detail": f"Expected PSS 'restricted', got {item.get('pss_enforce')!r}",
                }
            )
        if days < cert_warn_days:
            findings.append(
                {
                    "target_kind": item.get("kind", "Certificate"),
                    "target_name": item.get("name", "unknown"),
                    "rule_id": "HYG-CERT-EXPIRY",
                    "severity": "warning" if days >= 7 else "critical",
                    "detail": f"Certificate expires in {days} days (< {cert_warn_days}d threshold)",
                }
            )

    return {
        "job_id": job_id,
        "run_id": run_id,
        "mode": "monitor-platform-hygiene",
        "status": "Succeeded",
        "window_start": window_start,
        "window_end": window_end,
        "items_processed": len(observed),
        "violations": findings,
        "actions_taken": [],
        "watermark_end": window_end,
        "metrics": {
            "targets_checked": len(observed),
            "targets_healthy": healthy_count,
            "min_cert_days_remaining": 0 if min_cert_days == 9999 else min_cert_days,
            "hygiene_warnings": len(findings),
        },
    }
