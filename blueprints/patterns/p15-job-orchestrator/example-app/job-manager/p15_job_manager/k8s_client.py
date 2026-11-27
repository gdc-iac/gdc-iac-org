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
"""In-cluster Kubernetes API client for `CronJob`/`Job` (Profile B) & Argo `CronWorkflow`/`Workflow` (Profile A)."""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import quote


class InClusterK8sClient:
    """Least-privilege in-cluster K8s REST client using `p15-job-manager-sa` credentials (no extra deps)."""

    SA_TOKEN_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token"
    SA_CA_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"

    def __init__(self, api_server: str | None = None, timeout: float = 8.0) -> None:
        host = os.getenv("KUBERNETES_SERVICE_HOST", "").strip()
        port = os.getenv("KUBERNETES_SERVICE_PORT", "443").strip()
        self.api_server = (api_server or (f"https://{host}:{port}" if host else "")).rstrip("/")
        self.timeout = timeout

    @classmethod
    def detect(cls) -> InClusterK8sClient | None:
        """Return an active client only when running inside a Kubernetes pod with ServiceAccount mount."""
        if (
            os.getenv("P15_DISABLE_IN_CLUSTER_K8S", "").strip().lower() in ("1", "true", "yes")
            or not os.getenv("KUBERNETES_SERVICE_HOST")
            or not os.path.exists(cls.SA_TOKEN_PATH)
        ):
            return None
        return cls()

    def _client(self) -> tuple[Any, dict[str, str]]:
        import httpx

        token = ""
        if os.path.exists(self.SA_TOKEN_PATH):
            with open(self.SA_TOKEN_PATH, "r", encoding="utf-8") as f:
                token = f.read().strip()
        verify: str | bool = self.SA_CA_PATH if os.path.exists(self.SA_CA_PATH) else True
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return (
            httpx.Client(timeout=self.timeout, follow_redirects=False, trust_env=False, verify=verify),
            headers,
        )

    def _collection_url(self, kind: str, namespace: str) -> str:
        ns = quote(namespace, safe="")
        if kind == "CronJob":
            return f"{self.api_server}/apis/batch/v1/namespaces/{ns}/cronjobs"
        if kind == "Job":
            return f"{self.api_server}/apis/batch/v1/namespaces/{ns}/jobs"
        if kind == "CronWorkflow":
            return f"{self.api_server}/apis/argoproj.io/v1alpha1/namespaces/{ns}/cronworkflows"
        if kind == "Workflow":
            return f"{self.api_server}/apis/argoproj.io/v1alpha1/namespaces/{ns}/workflows"
        raise ValueError(f"Unsupported Kubernetes manifest kind: {kind!r}")

    @staticmethod
    def _raise_for_k8s_error(resp: Any, action: str) -> None:
        if resp.status_code < 400:
            return
        detail = ""
        try:
            body = resp.json()
            if isinstance(body, dict):
                detail = str(body.get("message") or body.get("reason") or "")
        except Exception:
            detail = (resp.text or "")[:240]
        raise RuntimeError(f"K8s {action} HTTP {resp.status_code}: {detail or resp.reason_phrase}")

    def apply_manifest(self, manifest: dict[str, Any]) -> dict[str, Any]:
        """Create a CronJob/Job/CronWorkflow/Workflow; merge-patch schedules on 409 AlreadyExists."""
        kind = str(manifest["kind"])
        meta = manifest.get("metadata") or {}
        ns = str(meta["namespace"])
        name = str(meta["name"])
        base_url = self._collection_url(kind, ns)
        client, headers = self._client()
        with client:
            resp = client.post(base_url, headers=headers, json=manifest)
            if resp.status_code in (200, 201):
                return resp.json()
            if resp.status_code == 409 and kind in ("CronJob", "CronWorkflow"):
                patch_hdrs = {**headers, "Content-Type": "application/merge-patch+json"}
                patch_body = {
                    "metadata": {
                        "labels": meta.get("labels") or {},
                        "annotations": meta.get("annotations") or {},
                    },
                    "spec": manifest.get("spec") or {},
                }
                p_resp = client.patch(
                    f"{base_url}/{quote(name, safe='')}", headers=patch_hdrs, json=patch_body
                )
                self._raise_for_k8s_error(p_resp, f"PATCH {kind}/{name}")
                return p_resp.json()
            if resp.status_code == 409 and kind in ("Job", "Workflow"):
                g_resp = client.get(f"{base_url}/{quote(name, safe='')}", headers=headers)
                if g_resp.status_code == 200:
                    return g_resp.json()
            self._raise_for_k8s_error(resp, f"POST {kind}/{name}")
            return resp.json()

    def delete_resource(self, kind: str, namespace: str, name: str) -> bool:
        """Delete a CronJob/CronWorkflow/Job/Workflow cleanly (returns False on 404)."""
        url = f"{self._collection_url(kind, namespace)}/{quote(name, safe='')}?propagationPolicy=Background"
        client, headers = self._client()
        with client:
            resp = client.delete(url, headers=headers)
            if resp.status_code == 404:
                return False
            self._raise_for_k8s_error(resp, f"DELETE {kind}/{name}")
            return True

    def get_run_status(self, engine_mode: str, namespace: str, run_id: str) -> dict[str, Any] | None:
        """Return `{phase: Running|Succeeded|Failed, exit_code: int|None}` or `None` if not found."""
        kind = "Workflow" if engine_mode == "argo" else "Job"
        url = f"{self._collection_url(kind, namespace)}/{quote(run_id, safe='')}"
        client, headers = self._client()
        with client:
            resp = client.get(url, headers=headers)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            obj = resp.json()

        status = obj.get("status") or {}
        if kind == "Workflow":
            phase = str(status.get("phase") or "Running")
            if phase == "Succeeded":
                return {"phase": "Succeeded", "exit_code": 0}
            if phase in ("Failed", "Error"):
                return {"phase": "Failed", "exit_code": 1}
            return {"phase": "Running", "exit_code": None}

        # batch/v1 Job
        conditions = status.get("conditions") or []
        for cond in conditions:
            if cond.get("type") == "Complete" and cond.get("status") == "True":
                return {"phase": "Succeeded", "exit_code": 0}
            if cond.get("type") == "Failed" and cond.get("status") == "True":
                return {"phase": "Failed", "exit_code": 1}
        if int(status.get("succeeded") or 0) >= 1:
            return {"phase": "Succeeded", "exit_code": 0}
        return {"phase": "Running", "exit_code": None}

    def get_run_logs(self, engine_mode: str, namespace: str, run_id: str) -> str:
        """Fetch stdout logs from the worker pod associated with `run_id`."""
        ns = quote(namespace, safe="")
        selector = (
            f"workflows.argoproj.io/workflow={run_id}"
            if engine_mode == "argo"
            else f"p15.gdc.goog/run-id={run_id}"
        )
        client, headers = self._client()
        with client:
            pods_resp = client.get(
                f"{self.api_server}/api/v1/namespaces/{ns}/pods?labelSelector={quote(selector, safe='')}",
                headers=headers,
            )
            if pods_resp.status_code != 200:
                return ""
            items = pods_resp.json().get("items") or []
            if not items:
                return ""
            pod_name = str(items[-1]["metadata"]["name"])
            containers = [c["name"] for c in (items[-1].get("spec", {}).get("containers") or [])]
            container = "main" if "main" in containers else (containers[0] if containers else "")
            log_url = f"{self.api_server}/api/v1/namespaces/{ns}/pods/{quote(pod_name, safe='')}/log"
            if container:
                log_url = f"{log_url}?container={quote(container, safe='')}"
            log_resp = client.get(log_url, headers=headers)
            if log_resp.status_code != 200:
                return ""
            return log_resp.text


def extract_json_summary_from_logs(log_text: str) -> dict[str, Any]:
    """Parse the final structured JSON summary emitted by `p15_jobs.runner` on stdout."""
    for line in reversed((log_text or "").splitlines()):
        stripped = line.strip()
        if not stripped.startswith("{") or not stripped.endswith("}"):
            continue
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, dict) and ("status" in parsed or "artifact_uri" in parsed):
                return parsed
        except json.JSONDecodeError:
            continue
    return {}
