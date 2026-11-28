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
"""Dual-Profile Execution Compiler (`argo` vs `k8s-native`) & Anti-ClickOps `GITOPS_MODE` Guard."""

from __future__ import annotations

import json
from typing import Any
import yaml

from .config import ControlPlaneConfig
from .security import SecurityValidationError

GITOPS_MANAGED_ANNOTATIONS = (
    "argocd.argoproj.io/tracking-id",
    "kustomize.toolkit.fluxcd.io/name",
    "helm.toolkit.fluxcd.io/name",
)


def is_gitops_protected(job: dict[str, Any], gitops_mode: str) -> tuple[bool, str]:
    """Determine whether direct cluster mutation must be blocked in favour of YAML/MR export."""
    if gitops_mode == "gitops-mr":
        return True, "Namespace GITOPS_MODE='gitops-mr' requires declarative YAML / Merge Request export."
    annotations = job.get("gitops_annotations") or {}
    if job.get("gitops_managed"):
        return True, "Schedule is flagged gitops_managed=true."
    if annotations.get("argocd.argoproj.io/tracking-id"):
        return True, "Resource carries Argo CD annotation 'argocd.argoproj.io/tracking-id'."
    if annotations.get("kustomize.toolkit.fluxcd.io/name"):
        return True, "Resource carries Flux Kustomization annotation 'kustomize.toolkit.fluxcd.io/name'."
    if annotations.get("helm.toolkit.fluxcd.io/name"):
        return True, "Resource carries Flux HelmRelease annotation 'helm.toolkit.fluxcd.io/name'."
    return False, ""


def resolve_priority_class(persona: str, job_class: str) -> str:
    """Map persona + job_class to `REQ-REL-004` Kubernetes `PriorityClass` tiers."""
    if persona == "PA" and job_class in ("monitor", "enforce"):
        return "p15-pa-critical"
    if job_class == "batch" and persona == "AO":
        return "p15-batch-low"
    return "p15-ao-standard"


def _restricted_pod_security_context() -> dict[str, Any]:
    return {
        "runAsNonRoot": True,
        "runAsUser": 65532,
        "runAsGroup": 65532,
        "fsGroup": 65532,
        "seccompProfile": {"type": "RuntimeDefault"},
    }


def _restricted_container_security_context() -> dict[str, Any]:
    return {
        "allowPrivilegeEscalation": False,
        "readOnlyRootFilesystem": True,
        "runAsNonRoot": True,
        "runAsUser": 65532,
        "runAsGroup": 65532,
        "capabilities": {"drop": ["ALL"]},
    }


def _argo_worker_volumes() -> list[dict[str, Any]]:
    """Shared PSS-Restricted writable /tmp, /home/appuser & optional GDC CA volumes for Argo templates."""
    return [
        {"name": "tmp", "emptyDir": {}},
        {"name": "appuser-home", "emptyDir": {}},
        {"name": "gdc-ca-bundle", "secret": {"secretName": "gdc-ca-bundle", "optional": True}},
    ]


def _worker_cli_args(
    job: dict[str, Any],
    run_id: str,
    window_start: str,
    window_end: str,
    shard_key: str,
    sink_uri: str,
) -> list[str]:
    enf_flag = "enforce" if job.get("enforcement_mode") == "auto-remediate" else job.get("enforcement_mode", "audit")
    return [
        "python3",
        "-m",
        "p15_jobs.runner",
        "--mode",
        str(job["worker_mode"]),
        "--job-id",
        str(job["job_id"]),
        "--run-id",
        run_id,
        "--window-start",
        window_start,
        "--window-end",
        window_end,
        "--shard-key",
        shard_key,
        "--sink-uri",
        sink_uri,
        "--enforcement-mode",
        str(enf_flag),
    ]


class DualProfileEngineCompiler:
    """Compiles registered jobs into Profile A (`CronWorkflow`/`Workflow`) or Profile B (`CronJob`/`Job`)."""

    def __init__(self, config: ControlPlaneConfig, cluster_applier: Any = None) -> None:
        self.config = config
        self._cluster_applier = cluster_applier
        self.applied_manifests: dict[tuple[str, str, str], dict[str, Any]] = {}

    def validate_guardrails(self, job: dict[str, Any], shard_keys: list[str] | None = None) -> None:
        max_shards = int(job.get("max_shards", 10))
        if max_shards < 1 or max_shards > self.config.max_shards_per_run:
            raise SecurityValidationError(
                f"max_shards ({max_shards}) exceeds hard ceiling ({self.config.max_shards_per_run})"
            )
        if shard_keys and len(shard_keys) > self.config.max_shards_per_run:
            raise SecurityValidationError(
                f"Requested shard fan-out ({len(shard_keys)}) exceeds maxShardsPerRun ({self.config.max_shards_per_run})"
            )
        deadline = int(job.get("active_deadline_secs", 900))
        ceiling = (
            self.config.max_monitor_deadline_seconds
            if job.get("job_class") == "monitor"
            else self.config.max_batch_deadline_seconds
        )
        if deadline < 10 or deadline > ceiling:
            raise SecurityValidationError(
                f"active_deadline_secs ({deadline}s) must be within [10..{ceiling}] for class {job.get('job_class')!r}"
            )

    def _service_account_for(self, job: dict[str, Any]) -> str:
        if self.config.engine_mode == "k8s-native":
            return "p15-ao-worker-sa"
        return "p15-pa-watcher-sa" if job.get("persona") == "PA" else "p15-ao-worker-sa"

    def _sink_uri_base(self, job: dict[str, Any]) -> str:
        scheme = "s3" if self.config.s3_endpoint else "gs"
        bucket = self.config.bucket_name.strip()
        for prefix in ("s3://", "gs://", "file://"):
            if bucket.startswith(prefix):
                bucket = bucket[len(prefix) :]
        bucket = bucket.strip("/").split("/", 1)[0]
        return f"{scheme}://{bucket}/jobs/{job['namespace']}/{job['job_id']}"

    def compile_schedule_manifest(self, job: dict[str, Any], engine_mode: str | None = None) -> dict[str, Any]:
        """Render declarative `CronWorkflow` (Profile A) or `CronJob` (Profile B) manifest."""
        self.validate_guardrails(job)
        mode = engine_mode or self.config.engine_mode
        priority_class = resolve_priority_class(job["persona"], job["job_class"])
        sa_name = self._service_account_for(job)
        sink_uri = self._sink_uri_base(job)
        labels = {
            "app.kubernetes.io/part-of": "p15-job-orchestrator",
            "p15.gdc.goog/job-id": job["job_id"],
            "p15.gdc.goog/persona": job["persona"],
            "p15.gdc.goog/job-class": job["job_class"],
        }

        if mode == "argo":
            return {
                "apiVersion": "argoproj.io/v1alpha1",
                "kind": "CronWorkflow",
                "metadata": {
                    "name": job["job_id"],
                    "namespace": job["namespace"],
                    "labels": labels,
                    "annotations": dict(job.get("gitops_annotations") or {}),
                },
                "spec": {
                    "schedule": job["schedule_cron"],
                    "timezone": job.get("timezone", "UTC"),
                    "suspend": bool(job.get("suspended", False)),
                    "concurrencyPolicy": job.get("concurrency_policy", "Forbid"),
                    "startingDeadlineSeconds": int(job.get("starting_deadline_secs", 300)),
                    "successfulJobsHistoryLimit": 3,
                    "failedJobsHistoryLimit": 3,
                    "workflowSpec": {
                        "serviceAccountName": sa_name,
                        "priorityClassName": priority_class,
                        "parallelism": min(int(job.get("parallelism", 5)), 10),
                        "activeDeadlineSeconds": int(job.get("active_deadline_secs", 900)),
                        "ttlStrategy": {
                            "secondsAfterSuccess": 86400,
                            "secondsAfterFailure": 259200,
                            "secondsAfterCompletion": 259200,
                        },
                        "podGC": {"strategy": "OnWorkflowSuccess"},
                        "archiveLogs": True,
                        "securityContext": _restricted_pod_security_context(),
                        "volumes": _argo_worker_volumes(),
                        "arguments": {
                            "parameters": [
                                {"name": "worker_image", "value": job["worker_image"]},
                                {"name": "mode", "value": job["worker_mode"]},
                                {"name": "job_id", "value": job["job_id"]},
                                {"name": "sink_uri", "value": sink_uri},
                                {"name": "enforcement_mode", "value": job.get("enforcement_mode", "audit")},
                            ]
                        },
                        "onExit": "notify-job-manager",
                        "entrypoint": "standard-runner",
                        "templates": [
                            {
                                "name": "standard-runner",
                                "steps": [
                                    [
                                        {
                                            "name": "execute-worker",
                                            "templateRef": {
                                                "name": job.get("template_name", "gdc-standard-job-runner-v1"),
                                                "template": "run-worker",
                                                "clusterScope": True,
                                            },
                                            "arguments": {
                                                "parameters": [
                                                    {"name": "worker_image", "value": job["worker_image"]},
                                                    {"name": "mode", "value": job["worker_mode"]},
                                                    {"name": "job_id", "value": job["job_id"]},
                                                    {"name": "sink_uri", "value": sink_uri},
                                                    {
                                                        "name": "enforcement_mode",
                                                        "value": job.get("enforcement_mode", "audit"),
                                                    },
                                                ]
                                            },
                                        }
                                    ],
                                    [
                                        {
                                            "name": "drain-wal-to-postgres",
                                            "continueOn": {"failed": True},
                                            "templateRef": {
                                                "name": job.get("template_name", "gdc-standard-job-runner-v1"),
                                                "template": "drain-wal",
                                                "clusterScope": True,
                                            },
                                        }
                                    ],
                                ],
                            },
                            {
                                "name": "notify-job-manager",
                                "http": {
                                    "url": f"http://p15-job-portal.{self.config.namespace}.svc.cluster.local:8080/api/v1/webhooks/argo-onexit",
                                    "method": "POST",
                                },
                            },
                        ],
                    },
                },
            }

        # Profile B: Kubernetes-native CronJob (0 Custom CRDs)
        cli = _worker_cli_args(
            job,
            run_id="$(POD_NAME)",
            window_start="",
            window_end="",
            shard_key="all",
            sink_uri=sink_uri,
        )
        return {
            "apiVersion": "batch/v1",
            "kind": "CronJob",
            "metadata": {
                "name": job["job_id"],
                "namespace": job["namespace"],
                "labels": labels,
                "annotations": dict(job.get("gitops_annotations") or {}),
            },
            "spec": {
                "schedule": job["schedule_cron"],
                "timeZone": job.get("timezone", "UTC"),
                "suspend": bool(job.get("suspended", False)),
                "concurrencyPolicy": job.get("concurrency_policy", "Forbid"),
                "startingDeadlineSeconds": int(job.get("starting_deadline_secs", 300)),
                "successfulJobsHistoryLimit": 3,
                "failedJobsHistoryLimit": 3,
                "jobTemplate": {
                    "spec": {
                        "ttlSecondsAfterFinished": 86400,
                        "backoffLimit": 4,
                        "activeDeadlineSeconds": int(job.get("active_deadline_secs", 900)),
                        "podFailurePolicy": {
                            "rules": [
                                {
                                    "action": "FailJob",
                                    "onExitCodes": {
                                        "containerName": "worker",
                                        "operator": "In",
                                        "values": [2],
                                    },
                                }
                            ]
                        },
                        "template": {
                            "metadata": {"labels": labels},
                            "spec": {
                                "serviceAccountName": sa_name,
                                "priorityClassName": priority_class,
                                # Kubernetes requires restartPolicy: Never whenever podFailurePolicy is specified
                                # (transient exit!=2 pods still retry up to backoffLimit: 4 as fresh pods).
                                "restartPolicy": "Never",
                                "securityContext": _restricted_pod_security_context(),
                                "containers": [
                                    {
                                        "name": "worker",
                                        "image": job["worker_image"],
                                        "command": cli[:3],
                                        "args": cli[3:],
                                        "securityContext": _restricted_container_security_context(),
                                        "env": [
                                            {
                                                "name": "POD_NAME",
                                                "valueFrom": {"fieldRef": {"fieldPath": "metadata.name"}},
                                            },
                                            {"name": "NAMESPACE", "value": job["namespace"]},
                                            {"name": "S3_ENDPOINT", "value": self.config.s3_endpoint},
                                            {"name": "BUCKET_NAME", "value": self.config.bucket_name},
                                            {"name": "AWS_CA_BUNDLE", "value": "/etc/gdc-certs/ca.crt"},
                                        ],
                                        "envFrom": [
                                            {"configMapRef": {"name": "p15-job-manager-config", "optional": True}},
                                            {"configMapRef": {"name": "p15-job-manager-gcp-config", "optional": True}},
                                            {"secretRef": {"name": "p15-s3-credentials", "optional": True}},
                                        ],
                                        "resources": {
                                            "requests": {"cpu": "100m", "memory": "128Mi"},
                                            "limits": {"cpu": "500m", "memory": "512Mi"},
                                        },
                                        "volumeMounts": [
                                            {"name": "tmp", "mountPath": "/tmp"},
                                            {"name": "appuser-home", "mountPath": "/home/appuser"},
                                            {"name": "gdc-ca", "mountPath": "/etc/gdc-certs", "readOnly": True},
                                        ],
                                    }
                                ],
                                "volumes": [
                                    {"name": "tmp", "emptyDir": {}},
                                    {"name": "appuser-home", "emptyDir": {}},
                                    {
                                        "name": "gdc-ca",
                                        "secret": {"secretName": "gdc-ca-bundle", "optional": True},
                                    },
                                ],
                            },
                        },
                    }
                },
            },
        }

    def compile_run_manifest(
        self,
        job: dict[str, Any],
        run_id: str,
        window_start: str,
        window_end: str,
        shard_keys: list[str] | None = None,
        engine_mode: str | None = None,
    ) -> dict[str, Any]:
        """Compile an on-demand / backfill `Workflow` (Profile A, with fan-out/fan-in) or `Job` (Profile B)."""
        shards = shard_keys or ["all"]
        self.validate_guardrails(job, shard_keys=shards)
        mode = engine_mode or self.config.engine_mode
        priority_class = resolve_priority_class(job["persona"], job["job_class"])
        sa_name = self._service_account_for(job)
        sink_uri = self._sink_uri_base(job)
        labels = {
            "app.kubernetes.io/part-of": "p15-job-orchestrator",
            "p15.gdc.goog/job-id": job["job_id"],
            "p15.gdc.goog/run-id": run_id,
        }

        if mode == "argo":
            return {
                "apiVersion": "argoproj.io/v1alpha1",
                "kind": "Workflow",
                "metadata": {"name": run_id, "namespace": job["namespace"], "labels": labels},
                "spec": {
                    "serviceAccountName": sa_name,
                    "priorityClassName": priority_class,
                    "parallelism": min(int(job.get("parallelism", 5)), 10),
                    "activeDeadlineSeconds": int(job.get("active_deadline_secs", 900)),
                    "ttlStrategy": {
                        "secondsAfterSuccess": 86400,
                        "secondsAfterFailure": 259200,
                        "secondsAfterCompletion": 259200,
                    },
                    "podGC": {"strategy": "OnWorkflowSuccess"},
                    "securityContext": _restricted_pod_security_context(),
                    "volumes": _argo_worker_volumes(),
                    "arguments": {
                        "parameters": [
                            {"name": "worker_image", "value": job["worker_image"]},
                            {"name": "mode", "value": job["worker_mode"]},
                            {"name": "job_id", "value": job["job_id"]},
                            {"name": "sink_uri", "value": sink_uri},
                            {"name": "enforcement_mode", "value": job.get("enforcement_mode", "audit")},
                        ]
                    },
                    "entrypoint": "sharded-dag",
                    "templates": [
                        {
                            "name": "sharded-dag",
                            "dag": {
                                "tasks": [
                                    {
                                        "name": "fan-out-shards",
                                        "templateRef": {
                                            "name": job.get("template_name", "gdc-standard-job-runner-v1"),
                                            "template": "run-worker",
                                            "clusterScope": True,
                                        },
                                        "arguments": {
                                            "parameters": [
                                                {"name": "worker_image", "value": job["worker_image"]},
                                                {"name": "mode", "value": job["worker_mode"]},
                                                {"name": "job_id", "value": job["job_id"]},
                                                {"name": "sink_uri", "value": sink_uri},
                                                {
                                                    "name": "enforcement_mode",
                                                    "value": job.get("enforcement_mode", "audit"),
                                                },
                                                {"name": "shard_key", "value": "{{item}}"},
                                                {"name": "window_start", "value": window_start},
                                                {"name": "window_end", "value": window_end},
                                            ]
                                        },
                                        "withParam": json.dumps(shards),
                                    },
                                    {
                                        "name": "fan-in-reconcile",
                                        "dependencies": ["fan-out-shards"],
                                        "continueOn": {"failed": True},
                                        "templateRef": {
                                            "name": job.get("template_name", "gdc-standard-job-runner-v1"),
                                            "template": "drain-wal",
                                            "clusterScope": True,
                                        },
                                    },
                                ]
                            },
                        }
                    ],
                },
            }

        cli = _worker_cli_args(
            job,
            run_id=run_id,
            window_start=window_start,
            window_end=window_end,
            shard_key=",".join(shards),
            sink_uri=sink_uri,
        )
        return {
            "apiVersion": "batch/v1",
            "kind": "Job",
            "metadata": {"name": run_id, "namespace": job["namespace"], "labels": labels},
            "spec": {
                "ttlSecondsAfterFinished": 86400,
                "backoffLimit": 4,
                "parallelism": min(len(shards), int(job.get("parallelism", 5))),
                "completions": len(shards),
                "activeDeadlineSeconds": int(job.get("active_deadline_secs", 900)),
                "template": {
                    "metadata": {"labels": labels},
                    "spec": {
                        "serviceAccountName": sa_name,
                        "priorityClassName": priority_class,
                        "restartPolicy": "OnFailure",
                        "securityContext": _restricted_pod_security_context(),
                        "containers": [
                            {
                                "name": "worker",
                                "image": job["worker_image"],
                                "command": cli[:3],
                                "args": cli[3:],
                                "securityContext": _restricted_container_security_context(),
                                "env": [
                                    {
                                        "name": "POD_NAME",
                                        "valueFrom": {"fieldRef": {"fieldPath": "metadata.name"}},
                                    },
                                    {"name": "NAMESPACE", "value": job["namespace"]},
                                    {"name": "S3_ENDPOINT", "value": self.config.s3_endpoint},
                                    {"name": "BUCKET_NAME", "value": self.config.bucket_name},
                                    {"name": "AWS_CA_BUNDLE", "value": "/etc/gdc-certs/ca.crt"},
                                ],
                                "envFrom": [
                                    {"configMapRef": {"name": "p15-job-manager-config", "optional": True}},
                                    {"configMapRef": {"name": "p15-job-manager-gcp-config", "optional": True}},
                                    {"secretRef": {"name": "p15-s3-credentials", "optional": True}},
                                ],
                                "resources": {
                                    "requests": {"cpu": "100m", "memory": "128Mi"},
                                    "limits": {"cpu": "500m", "memory": "512Mi"},
                                },
                                "volumeMounts": [
                                    {"name": "tmp", "mountPath": "/tmp"},
                                    {"name": "appuser-home", "mountPath": "/home/appuser"},
                                    {"name": "gdc-ca", "mountPath": "/etc/gdc-certs", "readOnly": True},
                                ],
                            }
                        ],
                        "volumes": [
                            {"name": "tmp", "emptyDir": {}},
                            {"name": "appuser-home", "emptyDir": {}},
                            {
                                "name": "gdc-ca",
                                "secret": {"secretName": "gdc-ca-bundle", "optional": True},
                            },
                        ],
                    },
                },
            },
        }

    def reconcile_schedule(self, job: dict[str, Any]) -> dict[str, Any]:
        """Apply schedule to cluster in `direct-apply` mode or export YAML/MR when GitOps-protected."""
        manifest = self.compile_schedule_manifest(job)
        manifest_yaml = yaml.safe_dump(manifest, sort_keys=False)
        protected, reason = is_gitops_protected(job, self.config.gitops_mode)
        if protected:
            return {
                "applied_to_cluster": False,
                "gitops_protected": True,
                "reason": reason,
                "manifest_kind": manifest["kind"],
                "manifest_yaml": manifest_yaml,
                "merge_request_export": {
                    "target_branch": "main",
                    "source_branch": f"p15/schedule-{job['job_id']}",
                    "file_path": f"clusters/{job['namespace']}/schedules/{job['job_id']}.yaml",
                    "commit_message": f"chore(p15): update schedule {job['job_id']}",
                    "content": manifest_yaml,
                },
            }

        key = (manifest["kind"], job["namespace"], job["job_id"])
        self.applied_manifests[key] = manifest
        applied_ok = True
        cluster_error = ""
        if self._cluster_applier is not None:
            try:
                self._cluster_applier(manifest)
            except Exception as exc:
                applied_ok = False
                cluster_error = str(exc)
        out: dict[str, Any] = {
            "applied_to_cluster": applied_ok,
            "gitops_protected": False,
            "manifest_kind": manifest["kind"],
            "manifest_yaml": manifest_yaml,
        }
        if cluster_error:
            out["cluster_error"] = cluster_error
        return out
