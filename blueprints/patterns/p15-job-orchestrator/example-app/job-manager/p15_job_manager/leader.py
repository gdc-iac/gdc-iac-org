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
"""Kubernetes `coordination.k8s.io/v1` `Lease` leader election for singleton background loops (`REQ-REL-001`)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import os
import socket
import threading
from typing import Any, Callable


@dataclass
class LeaseRecord:
    name: str
    namespace: str
    holder_identity: str
    lease_duration_seconds: int
    acquire_time: datetime
    renew_time: datetime
    lease_transitions: int
    resource_version: str


class InMemoryLeaseStore:
    """Thread-safe shared Lease store simulating `coordination.k8s.io/v1` optimistic concurrency."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._leases: dict[tuple[str, str], LeaseRecord] = {}
        self._rv_counter = 1

    def get(self, namespace: str, name: str) -> LeaseRecord | None:
        with self._lock:
            rec = self._leases.get((namespace, name))
            return LeaseRecord(**rec.__dict__) if rec else None

    def create(self, rec: LeaseRecord) -> LeaseRecord:
        with self._lock:
            key = (rec.namespace, rec.name)
            if key in self._leases:
                raise RuntimeError("409 AlreadyExists")
            self._rv_counter += 1
            stored = LeaseRecord(**{**rec.__dict__, "resource_version": str(self._rv_counter)})
            self._leases[key] = stored
            return LeaseRecord(**stored.__dict__)

    def update(self, rec: LeaseRecord) -> LeaseRecord:
        with self._lock:
            key = (rec.namespace, rec.name)
            cur = self._leases.get(key)
            if cur is None or cur.resource_version != rec.resource_version:
                raise RuntimeError("409 Conflict: resourceVersion mismatch")
            self._rv_counter += 1
            stored = LeaseRecord(**{**rec.__dict__, "resource_version": str(self._rv_counter)})
            self._leases[key] = stored
            return LeaseRecord(**stored.__dict__)


class KubernetesAPILeaseStore:
    """In-cluster Kubernetes `coordination.k8s.io/v1` Lease client using ServiceAccount credentials."""

    SA_TOKEN_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token"
    SA_CA_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"

    def __init__(self, api_server: str | None = None) -> None:
        host = os.getenv("KUBERNETES_SERVICE_HOST", "kubernetes.default.svc")
        port = os.getenv("KUBERNETES_SERVICE_PORT", "443")
        self.api_server = (api_server or f"https://{host}:{port}").rstrip("/")

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
        return httpx.Client(timeout=5.0, follow_redirects=False, trust_env=False, verify=verify), headers

    @staticmethod
    def _from_k8s(obj: dict[str, Any]) -> LeaseRecord:
        meta = obj.get("metadata", {})
        spec = obj.get("spec", {})

        def _parse_ts(val: str | None) -> datetime:
            if not val:
                return datetime.now(timezone.utc)
            cleaned = val.replace("Z", "+00:00")
            return datetime.fromisoformat(cleaned).astimezone(timezone.utc)

        return LeaseRecord(
            name=meta.get("name", ""),
            namespace=meta.get("namespace", ""),
            holder_identity=spec.get("holderIdentity") or "",
            lease_duration_seconds=int(spec.get("leaseDurationSeconds") or 30),
            acquire_time=_parse_ts(spec.get("acquireTime")),
            renew_time=_parse_ts(spec.get("renewTime")),
            lease_transitions=int(spec.get("leaseTransitions") or 0),
            resource_version=str(meta.get("resourceVersion") or "1"),
        )

    @staticmethod
    def _to_k8s(rec: LeaseRecord) -> dict[str, Any]:
        fmt = "%Y-%m-%dT%H:%M:%S.%fZ"
        meta: dict[str, Any] = {"name": rec.name, "namespace": rec.namespace}
        if rec.resource_version:
            meta["resourceVersion"] = rec.resource_version
        return {
            "apiVersion": "coordination.k8s.io/v1",
            "kind": "Lease",
            "metadata": meta,
            "spec": {
                "holderIdentity": rec.holder_identity,
                "leaseDurationSeconds": rec.lease_duration_seconds,
                "acquireTime": rec.acquire_time.astimezone(timezone.utc).strftime(fmt),
                "renewTime": rec.renew_time.astimezone(timezone.utc).strftime(fmt),
                "leaseTransitions": rec.lease_transitions,
            },
        }

    def get(self, namespace: str, name: str) -> LeaseRecord | None:
        client, headers = self._client()
        with client:
            url = f"{self.api_server}/apis/coordination.k8s.io/v1/namespaces/{namespace}/leases/{name}"
            resp = client.get(url, headers=headers)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return self._from_k8s(resp.json())

    def create(self, rec: LeaseRecord) -> LeaseRecord:
        client, headers = self._client()
        with client:
            url = f"{self.api_server}/apis/coordination.k8s.io/v1/namespaces/{rec.namespace}/leases"
            resp = client.post(url, headers=headers, json=self._to_k8s(rec))
            if resp.status_code == 409:
                raise RuntimeError("409 AlreadyExists")
            resp.raise_for_status()
            return self._from_k8s(resp.json())

    def update(self, rec: LeaseRecord) -> LeaseRecord:
        client, headers = self._client()
        with client:
            url = f"{self.api_server}/apis/coordination.k8s.io/v1/namespaces/{rec.namespace}/leases/{rec.name}"
            resp = client.put(url, headers=headers, json=self._to_k8s(rec))
            if resp.status_code == 409:
                raise RuntimeError("409 Conflict")
            resp.raise_for_status()
            return self._from_k8s(resp.json())


class LeaseElector:
    """Coordinates singleton leadership across `p15-job-manager` replicas (`<= 30s` failover)."""

    def __init__(
        self,
        namespace: str,
        lease_name: str = "p15-job-manager-leader",
        identity: str | None = None,
        lease_duration_seconds: int = 30,
        store: InMemoryLeaseStore | KubernetesAPILeaseStore | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.namespace = namespace
        self.lease_name = lease_name
        self.identity = identity or os.getenv("POD_NAME") or f"{socket.gethostname()}-{os.getpid()}"
        self.lease_duration_seconds = min(max(5, lease_duration_seconds), 30)
        if store is not None:
            self.store = store
        elif os.path.exists(KubernetesAPILeaseStore.SA_TOKEN_PATH):
            self.store = KubernetesAPILeaseStore()
        else:
            self.store = InMemoryLeaseStore()
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._is_leader = False

    @property
    def is_leader(self) -> bool:
        return self._is_leader

    def try_acquire_or_renew(self) -> bool:
        """Attempt to acquire or renew the Lease; returns `True` iff this replica holds leadership."""
        now = self._clock().astimezone(timezone.utc)
        try:
            existing = self.store.get(self.namespace, self.lease_name)
            if existing is None:
                created = LeaseRecord(
                    name=self.lease_name,
                    namespace=self.namespace,
                    holder_identity=self.identity,
                    lease_duration_seconds=self.lease_duration_seconds,
                    acquire_time=now,
                    renew_time=now,
                    lease_transitions=0,
                    resource_version="",
                )
                self.store.create(created)
                self._is_leader = True
                return True

            if existing.holder_identity == self.identity:
                renewed = LeaseRecord(
                    name=existing.name,
                    namespace=existing.namespace,
                    holder_identity=self.identity,
                    lease_duration_seconds=self.lease_duration_seconds,
                    acquire_time=existing.acquire_time,
                    renew_time=now,
                    lease_transitions=existing.lease_transitions,
                    resource_version=existing.resource_version,
                )
                self.store.update(renewed)
                self._is_leader = True
                return True

            expires_at = existing.renew_time + timedelta(seconds=existing.lease_duration_seconds)
            if now >= expires_at or not existing.holder_identity:
                taken = LeaseRecord(
                    name=existing.name,
                    namespace=existing.namespace,
                    holder_identity=self.identity,
                    lease_duration_seconds=self.lease_duration_seconds,
                    acquire_time=now,
                    renew_time=now,
                    lease_transitions=existing.lease_transitions + 1,
                    resource_version=existing.resource_version,
                )
                self.store.update(taken)
                self._is_leader = True
                return True

            self._is_leader = False
            return False
        except Exception:
            self._is_leader = False
            return False

    def run_if_leader(self, fn: Callable[[], Any]) -> tuple[bool, Any]:
        """Acquire/renew leadership before running a singleton background loop tick."""
        if not self.try_acquire_or_renew():
            return False, None
        return True, fn()
