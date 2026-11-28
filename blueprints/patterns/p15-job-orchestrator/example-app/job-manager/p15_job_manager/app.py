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
"""Dual-Port FastAPI Control Plane (`:8080` Portal & `:8081` PA Admin Console) + Test Harness."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
import json
from pathlib import Path
import re
import sys
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse
import uuid

try:
    from fastapi import FastAPI, Request, Response  # type: ignore
except ImportError:  # pragma: no cover - optional in bare stdlib unit-test environments
    FastAPI = None  # type: ignore[assignment]
    Request = None  # type: ignore[assignment]
    Response = None  # type: ignore[assignment]

_COMMON_PARENT = str(Path(__file__).resolve().parents[2])
if _COMMON_PARENT not in sys.path:
    sys.path.insert(0, _COMMON_PARENT)

from common.redaction import redact_secrets, validate_object_key  # noqa: E402
from common.storage import DualModeStorageAdapter, build_job_artifact_key  # noqa: E402
from .config import ControlPlaneConfig
from .cron_utils import (
    CronValidationError,
    generate_utc_windows,
    normalize_utc_iso,
    preview_schedule,
)
from .engine import DualProfileEngineCompiler, is_gitops_protected
from .healing import SelfHealingAndEnforcementEngine, TOCTOUConflictError
from .k8s_client import InClusterK8sClient, extract_json_summary_from_logs
from .leader import LeaseElector
from .ledger import LedgerStore
from .metrics import MetricsRegistry
from .notifications import NotificationDeliveryError, NotificationRouter
from .security import (
    AuthenticationError,
    AuthorizationError,
    AuthPrincipal,
    OIDCAuthenticator,
    SecurityValidationError,
    generate_pkce_pair,
    validate_job_security_spec,
)
from .ui_portal import render_admin_html, render_portal_html

DEFAULT_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Cache-Control": "no-store",
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; connect-src 'self'; "
        "img-src 'self' data:; frame-ancestors 'none'"
    ),
}


@dataclass
class HTTPResponseEnvelope:
    status_code: int
    body: bytes
    headers: dict[str, str]

    def json(self) -> Any:
        return json.loads(self.body.decode("utf-8"))

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


class ControlPlaneHub:
    """Shared domain coordinator backing Port `:8080` (Portal/API) and Port `:8081` (PA Admin)."""

    def __init__(
        self,
        config: ControlPlaneConfig | None = None,
        ledger: LedgerStore | None = None,
        storage: DualModeStorageAdapter | None = None,
        authenticator: OIDCAuthenticator | None = None,
        leader: LeaseElector | None = None,
        adapter_kwargs: dict[str, Any] | None = None,
        k8s_client: Any = None,
    ) -> None:
        self.config = config or ControlPlaneConfig()
        self.metrics = MetricsRegistry()
        self.ledger = ledger or LedgerStore(self.config)
        self.storage = storage or DualModeStorageAdapter(
            bucket_name=self.config.bucket_name,
            s3_endpoint=self.config.s3_endpoint,
            local_dir="/tmp/p15-default-store" if not self.config.s3_endpoint and not self.config.db_host else None,
        )
        self.auth = authenticator or OIDCAuthenticator(self.config)
        self.k8s = k8s_client if k8s_client is not None else InClusterK8sClient.detect()

        def _cluster_apply_and_log(manifest: dict[str, Any]) -> None:
            if self.k8s is None:
                return
            try:
                self.k8s.apply_manifest(manifest)
            except Exception as exc:
                sys.stderr.write(
                    f"[p15-k8s] Warning: apply {manifest.get('kind')}/{manifest.get('metadata', {}).get('name')} failed: {exc}\n"
                )
                raise

        self.engine = DualProfileEngineCompiler(
            self.config, cluster_applier=_cluster_apply_and_log if self.k8s is not None else None
        )
        self.notifier = NotificationRouter(
            self.config, self.ledger, self.metrics, adapter_kwargs=adapter_kwargs
        )
        self.healing = SelfHealingAndEnforcementEngine(
            self.config, self.ledger, self.storage, self.metrics, self.notifier
        )
        self.leader = leader or LeaseElector(namespace=self.config.namespace)

    def _extract_bucket_key(self, uri: str) -> str:
        """Convert `gs://<bucket>/<key>` or `s3://<bucket>/<key>` into a relative storage key."""
        for prefix in ("gs://", "s3://", "memstore://", "file://"):
            if uri.startswith(prefix):
                rest = uri[len(prefix) :].lstrip("/")
                if "/" in rest:
                    return rest.split("/", 1)[1]
        return ""

    def reconcile_active_cluster_runs(self, now_utc: datetime | None = None) -> list[dict[str, Any]]:
        """Sync real K8s `Job` / Argo `Workflow` terminal state, logs & `result.json` back into the ledger."""
        if self.k8s is None:
            return []
        reconciled: list[dict[str, Any]] = []
        active_runs = self.ledger.list_job_runs(status="Running", limit=100) + self.ledger.list_job_runs(
            status="Pending", limit=100
        )
        for run in active_runs:
            run_id = run["run_id"]
            job_id = run["job_id"]
            ns = run["namespace"]
            eng_mode = run.get("engine_mode") or self.config.engine_mode
            try:
                st = self.k8s.get_run_status(eng_mode, ns, run_id)
            except Exception as exc:
                sys.stderr.write(f"[p15-k8s] Status poll failed for {run_id}: {exc}\n")
                continue
            if not st or st.get("phase") not in ("Succeeded", "Failed"):
                continue

            exit_code = int(st.get("exit_code") if st.get("exit_code") is not None else (0 if st["phase"] == "Succeeded" else 1))
            pod_logs = ""
            try:
                pod_logs = self.k8s.get_run_logs(eng_mode, ns, run_id)
            except Exception as exc:
                sys.stderr.write(f"[p15-k8s] Log fetch failed for {run_id}: {exc}\n")

            if pod_logs:
                try:
                    log_key = build_job_artifact_key(ns, job_id, run_id, "stdout.log")
                    self.storage.put_text(log_key, pod_logs, redact=True)
                except Exception as exc:
                    sys.stderr.write(f"[p15-k8s] Log archive failed for {run_id}: {exc}\n")

            stdout_meta = extract_json_summary_from_logs(pod_logs)
            artifact_uri = str(stdout_meta.get("artifact_uri") or run.get("artifact_uri") or "")
            summary_doc: dict[str, Any] = dict(stdout_meta)
            if artifact_uri:
                rel_key = self._extract_bucket_key(artifact_uri)
                if rel_key:
                    try:
                        raw_res = self.storage.get_text(rel_key)
                        parsed_res = json.loads(raw_res)
                        if isinstance(parsed_res, dict):
                            summary_doc = parsed_res
                    except Exception:
                        pass

            outcome = self.healing.record_run_outcome(
                job_id=job_id,
                run_id=run_id,
                exit_code=exit_code,
                summary=summary_doc,
                artifact_uri=artifact_uri or None,
                now_utc=now_utc,
            )
            if exit_code == 0 and run.get("window_end"):
                self.ledger.advance_watermark(
                    job_id,
                    run.get("shard_key", "all"),
                    str(run["window_end"]),
                    object_uri=artifact_uri or None,
                )
            violations = summary_doc.get("violations")
            if exit_code == 0 and isinstance(violations, list) and violations:
                try:
                    outcome["enforcement"] = self.healing.evaluate_violations(
                        job_id=job_id,
                        run_id=run_id,
                        violations=violations,
                        requested_by=run.get("requested_by") or "scheduler",
                        now_utc=now_utc,
                    )
                except Exception as exc:
                    sys.stderr.write(f"[p15-k8s] Violation evaluation failed for {run_id}: {exc}\n")
            reconciled.append({"run_id": run_id, "phase": st["phase"], "artifact_uri": artifact_uri})
        return reconciled

    def run_background_maintenance_tick(self, now_utc: datetime | None = None) -> dict[str, Any]:
        """Run singleton K8s Run Reconciler, Self-Heal Reaper & Outbox Dispatcher under K8s `Lease` lock."""

        def _work() -> dict[str, Any]:
            synced = self.reconcile_active_cluster_runs(now_utc=now_utc)
            reaped = self.healing.reap_stuck_runs(now_utc=now_utc)
            outbox_stats = self.notifier.process_pending_outbox(now_utc=now_utc)
            return {"reconciled_count": len(synced), "reaped_count": len(reaped), "outbox": outbox_stats}

        ran, result = self.leader.run_if_leader(_work)
        return {"is_leader": ran, "result": result}

    def _authenticate(
        self,
        method: str,
        headers: dict[str, str],
        admin_surface: bool,
    ) -> AuthPrincipal:
        norm_headers = {k.lower(): v for k, v in headers.items()}
        authz = norm_headers.get("authorization", "")
        if authz.lower().startswith("bearer "):
            token = authz[7:].strip()
            return self.auth.verify_bearer_token(token, require_admin_surface=admin_surface)

        cookie_hdr = norm_headers.get("cookie", "")
        jar = SimpleCookie()
        if cookie_hdr:
            jar.load(cookie_hdr)
        cookie_name = (
            OIDCAuthenticator.ADMIN_COOKIE_NAME
            if admin_surface
            else OIDCAuthenticator.USER_COOKIE_NAME
        )
        morsel = jar.get(cookie_name)
        if morsel is not None:
            mutating = method.upper() in ("POST", "PUT", "PATCH", "DELETE")
            origin = norm_headers.get("origin")
            req_host = norm_headers.get("host", "").strip().lower()
            fwd_host = norm_headers.get("x-forwarded-host", "").split(",")[0].strip().lower()
            origin_netloc = urlparse(origin).netloc.lower() if origin else ""
            same_origin = bool(origin_netloc and origin_netloc in {h for h in (req_host, fwd_host) if h})
            if mutating and origin and not same_origin and origin not in self.config.cors_allowed_origins:
                raise SecurityValidationError(f"Cross-origin mutation blocked for Origin {origin!r}")
            return self.auth.verify_session_cookie(
                morsel.value,
                admin_surface=admin_surface,
                csrf_header=norm_headers.get("x-csrf-token"),
                require_csrf=mutating,
            )

        raise AuthenticationError("Missing Bearer OIDC JWT or signed session cookie")

    def _apply_cors(self, req_headers: dict[str, str], resp_headers: dict[str, str]) -> None:
        origin = {k.lower(): v for k, v in req_headers.items()}.get("origin", "")
        if origin and origin in self.config.cors_allowed_origins:
            resp_headers["Access-Control-Allow-Origin"] = origin
            resp_headers["Access-Control-Allow-Credentials"] = "true"
            resp_headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type, X-CSRF-Token"
            resp_headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
            resp_headers["Vary"] = "Origin"

    def _json_response(
        self,
        status_code: int,
        payload: Any,
        req_headers: dict[str, str],
        extra_headers: dict[str, str] | None = None,
    ) -> HTTPResponseEnvelope:
        hdrs = dict(DEFAULT_SECURITY_HEADERS)
        hdrs["Content-Type"] = "application/json; charset=utf-8"
        self._apply_cors(req_headers, hdrs)
        if extra_headers:
            hdrs.update(extra_headers)
        return HTTPResponseEnvelope(
            status_code=status_code,
            body=json.dumps(payload, sort_keys=True, default=str).encode("utf-8"),
            headers=hdrs,
        )

    def handle_http(
        self,
        surface: str,  # "portal" (:8080) or "admin" (:8081)
        method: str,
        raw_path: str,
        headers: dict[str, str] | None = None,
        body: bytes = b"",
    ) -> HTTPResponseEnvelope:
        """Unified HTTP dispatcher shared by FastAPI/ASGI and hermetic local test harnesses."""
        req_headers = headers or {}
        correlation_id = f"corr-{uuid.uuid4().hex[:12]}"
        parsed_url = urlparse(raw_path)
        path = parsed_url.path.rstrip("/") or "/"
        query = {k: v[0] for k, v in parse_qs(parsed_url.query).items() if v}
        method_u = method.upper()
        is_admin_surface = surface == "admin"

        if method_u == "OPTIONS":
            return self._json_response(204, {}, req_headers)

        try:
            # Unauthenticated operational health & Prometheus scrapes
            if path == "/healthz" and method_u == "GET":
                return self._json_response(
                    200,
                    {
                        "status": "ok",
                        "surface": surface,
                        "engine_mode": self.config.engine_mode,
                        "gitops_mode": self.config.gitops_mode,
                        "storage_mode": self.storage.mode,
                    },
                    req_headers,
                )
            if path == "/readyz" and method_u == "GET":
                db_ok = self.ledger.health_check()
                return self._json_response(
                    200 if db_ok else 503,
                    {"ready": db_ok, "db_backend": self.ledger.backend},
                    req_headers,
                )
            if path == "/metrics" and method_u == "GET":
                hdrs = dict(DEFAULT_SECURITY_HEADERS)
                hdrs["Content-Type"] = "text/plain; version=0.0.4; charset=utf-8"
                return HTTPResponseEnvelope(
                    200, self.metrics.render_prometheus().encode("utf-8"), hdrs
                )
            if path == "/openapi.json" and method_u == "GET":
                return self._json_response(200, build_openapi_spec(surface), req_headers)

            # Offline HTML UI root
            if path == "/" and method_u == "GET":
                default_reg = (
                    self.config.allowed_registry_prefixes[0]
                    if self.config.allowed_registry_prefixes
                    else "harbor.gdc.local/blueprint-images/"
                )
                html_doc = (
                    render_admin_html(
                        self.config.engine_mode,
                        allow_simulated_oidc=self.config.allow_simulated_oidc,
                    )
                    if is_admin_surface
                    else render_portal_html(
                        self.config.engine_mode,
                        self.config.gitops_mode,
                        self.config.namespace,
                        default_registry=default_reg,
                        allow_simulated_oidc=self.config.allow_simulated_oidc,
                        default_worker_tag=self.config.worker_image_tag,
                    )
                )
                hdrs = dict(DEFAULT_SECURITY_HEADERS)
                hdrs["Content-Type"] = "text/html; charset=utf-8"
                return HTTPResponseEnvelope(200, html_doc.encode("utf-8"), hdrs)

            # OIDC PKCE Login Initiator
            if path == "/auth/oidc/login" and method_u == "GET":
                _, challenge = generate_pkce_pair()
                client_id = (
                    self.config.oidc_admin_client_id
                    if is_admin_surface
                    else self.config.oidc_client_id
                )
                params = urlencode(
                    {
                        "client_id": client_id,
                        "response_type": "code",
                        "scope": "openid profile email",
                        "code_challenge": challenge,
                        "code_challenge_method": "S256",
                    }
                )
                return self._json_response(
                    200,
                    {
                        "authorize_url": f"{self.config.oidc_issuer}/protocol/openid-connect/auth?{params}",
                        "pkce_method": "S256",
                    },
                    req_headers,
                )

            # Stateless OIDC Session Exchange: trade a verified Keycloak RS256 JWT
            # (supplied via `Authorization: Bearer <jwt>` OR JSON body `{"token": "<jwt>"}` so
            # authenticating reverse proxies like Cloud Workstations Web Preview do not intercept
            # the Authorization header) for a surface-bound HttpOnly session cookie + CSRF token.
            if path == "/auth/oidc/session" and method_u == "POST":
                norm_hdrs = {k.lower(): v for k, v in req_headers.items()}
                authz = norm_hdrs.get("authorization", "")
                raw_jwt = ""
                if authz.lower().startswith("bearer "):
                    raw_jwt = authz[7:].strip()
                elif body:
                    try:
                        parsed_body = json.loads(body.decode("utf-8") or "{}")
                        if isinstance(parsed_body, dict):
                            raw_jwt = str(
                                parsed_body.get("token") or parsed_body.get("access_token") or ""
                            )
                    except json.JSONDecodeError:
                        raw_jwt = ""
                raw_jwt = re.sub(r"\s+", "", raw_jwt)
                if not raw_jwt:
                    raise AuthenticationError(
                        "POST /auth/oidc/session requires an Authorization: Bearer <Keycloak RS256 JWT> header or JSON body {\"token\": \"<jwt>\"}"
                    )
                principal = self.auth.verify_bearer_token(
                    raw_jwt, require_admin_surface=is_admin_surface
                )
                c_name, c_val, csrf = self.auth.issue_session_cookie(
                    principal, admin_surface=is_admin_surface
                )
                set_cookie = self.auth.format_set_cookie_header(c_name, c_val)
                return self._json_response(
                    200,
                    {
                        "authenticated": True,
                        "principal": principal.subject,
                        "persona": principal.persona,
                        "roles": list(principal.roles),
                        "allowed_namespaces": list(principal.allowed_namespaces),
                        "can_mutate": principal.can_mutate,
                        "csrf_token": csrf,
                    },
                    req_headers,
                    extra_headers={"Set-Cookie": set_cookie},
                )

            # Session Introspection (`GET /auth/me`) & Surface Sign-Out (`POST /auth/logout`)
            if path == "/auth/me" and method_u == "GET":
                principal = self._authenticate(method_u, req_headers, admin_surface=is_admin_surface)
                return self._json_response(
                    200,
                    {
                        "authenticated": True,
                        "surface": surface,
                        "principal": principal.subject,
                        "email": principal.email,
                        "persona": principal.persona,
                        "roles": list(principal.roles),
                        "allowed_namespaces": list(principal.allowed_namespaces),
                        "can_mutate": principal.can_mutate,
                    },
                    req_headers,
                )

            if path == "/auth/logout" and method_u == "POST":
                c_name = (
                    OIDCAuthenticator.ADMIN_COOKIE_NAME
                    if is_admin_surface
                    else OIDCAuthenticator.USER_COOKIE_NAME
                )
                clear_cookie = self.auth.format_set_cookie_header(c_name, "", max_age=0)
                return self._json_response(
                    200,
                    {"authenticated": False, "surface": surface},
                    req_headers,
                    extra_headers={"Set-Cookie": clear_cookie},
                )

            # Stepping-Stone Simulated OIDC Login (STRICTLY gated by ALLOW_SIMULATED_OIDC)
            if path == "/auth/simulated" and method_u == "POST":
                if not self.config.allow_simulated_oidc:
                    raise AuthenticationError(
                        "Simulated OIDC login is disabled in production (ALLOW_SIMULATED_OIDC=false)"
                    )
                payload = json.loads(body.decode("utf-8") or "{}")
                role = str(payload.get("role") or "ao-job-operator")
                user = str(payload.get("username") or "stepping-stone-user").strip()
                email = user if "@" in user else f"{user}@gdc.local"
                ns = str(payload.get("namespace") or self.config.namespace)
                if role == "pa-job-admin":
                    principal = AuthPrincipal(
                        subject=user,
                        email=email,
                        persona="PA",
                        roles=("pa-job-admin",),
                        allowed_namespaces=("*",),
                        can_mutate=True,
                    )
                else:
                    principal = AuthPrincipal(
                        subject=user,
                        email=email,
                        persona="AO",
                        roles=(f"job-viewer-{ns}" if role.startswith("job-viewer") else f"ao-job-operator-{ns}",),
                        allowed_namespaces=(ns,),
                        can_mutate=(not role.startswith("job-viewer")),
                    )
                c_name, c_val, csrf = self.auth.issue_session_cookie(
                    principal, admin_surface=is_admin_surface
                )
                set_cookie = self.auth.format_set_cookie_header(c_name, c_val)
                return self._json_response(
                    200,
                    {
                        "authenticated": True,
                        "principal": principal.subject,
                        "persona": principal.persona,
                        "csrf_token": csrf,
                    },
                    req_headers,
                    extra_headers={"Set-Cookie": set_cookie},
                )

            # Enforce dual-port surface boundary before route dispatch
            if is_admin_surface:
                if not path.startswith("/admin/v1/"):
                    return self._json_response(404, {"error": "Route not found on :8081"}, req_headers)
                principal = self._authenticate(method_u, req_headers, admin_surface=True)
                return self._handle_admin_routes(method_u, path, body, principal, req_headers)

            if path.startswith("/admin/"):
                return self._json_response(
                    403,
                    {"error": "PA Admin routes are isolated strictly to Port 8081"},
                    req_headers,
                )

            principal = self._authenticate(method_u, req_headers, admin_surface=False)
            return self._handle_portal_routes(method_u, path, query, body, principal, req_headers)

        except AuthenticationError as exc:
            return self._json_response(
                401, {"error": str(exc), "correlation_id": correlation_id}, req_headers
            )
        except AuthorizationError as exc:
            return self._json_response(
                403, {"error": str(exc), "correlation_id": correlation_id}, req_headers
            )
        except TOCTOUConflictError as exc:
            return self._json_response(
                409, {"error": str(exc), "correlation_id": correlation_id}, req_headers
            )
        except (SecurityValidationError, CronValidationError, ValueError) as exc:
            return self._json_response(
                400, {"error": str(exc), "correlation_id": correlation_id}, req_headers
            )
        except KeyError as exc:
            return self._json_response(
                404, {"error": str(exc), "correlation_id": correlation_id}, req_headers
            )
        except NotificationDeliveryError as exc:
            return self._json_response(
                502, {"error": str(exc), "correlation_id": correlation_id}, req_headers
            )
        except Exception:
            # Redact internal stack traces / DB details on client responses (`REQ-SEC-008`)
            return self._json_response(
                500,
                {"error": "Internal control-plane error", "correlation_id": correlation_id},
                req_headers,
            )

    # -------------------------------------------------------------------------
    # Port `:8081` PA Platform Admin Routes
    # -------------------------------------------------------------------------
    def _handle_admin_routes(
        self,
        method: str,
        path: str,
        body: bytes,
        principal: AuthPrincipal,
        req_headers: dict[str, str],
    ) -> HTTPResponseEnvelope:
        assert principal.is_pa_admin
        payload = json.loads(body.decode("utf-8") or "{}") if body else {}

        if path == "/admin/v1/overview" and method == "GET":
            jobs = self.ledger.list_job_definitions()
            return self._json_response(
                200,
                {
                    "emergency_pause_all": self.ledger.emergency_pause_all,
                    "engine_mode": self.config.engine_mode,
                    "gitops_mode": self.config.gitops_mode,
                    "total_jobs": len(jobs),
                    "allowed_notification_hosts": list(self.config.allowed_notification_hosts),
                    "approved_templates": list(self.config.approved_templates),
                    "allowed_registry_prefixes": list(self.config.allowed_registry_prefixes),
                    "namespace_quotas": self.ledger.namespace_quotas,
                },
                req_headers,
            )

        if path == "/admin/v1/kill-switch" and method == "POST":
            paused = bool(payload.get("paused", True))
            self.ledger.emergency_pause_all = paused
            for job in self.ledger.list_job_definitions():
                job["suspended"] = paused
                self.ledger.upsert_job_definition(job)
            return self._json_response(
                200,
                {"emergency_pause_all": paused, "updated_by": principal.subject},
                req_headers,
            )

        if path == "/admin/v1/allowed-hosts" and method == "PUT":
            hosts = [str(h).strip().lower() for h in payload.get("hosts", []) if str(h).strip()]
            self.config.allowed_notification_hosts = hosts
            return self._json_response(
                200, {"allowed_notification_hosts": hosts, "updated_by": principal.subject}, req_headers
            )

        if path == "/admin/v1/quotas" and method == "PUT":
            ns = str(payload.get("namespace") or "").strip()
            if not ns:
                raise SecurityValidationError("namespace is required")
            quota = {
                "max_concurrent_jobs": int(payload.get("max_concurrent_jobs", 10)),
                "max_shards_per_run": min(
                    int(payload.get("max_shards_per_run", 25)), self.config.max_shards_per_run
                ),
            }
            self.ledger.namespace_quotas[ns] = quota
            return self._json_response(200, {"namespace": ns, "quota": quota}, req_headers)

        if path == "/admin/v1/audit-export" and method == "GET":
            return self._json_response(
                200,
                {
                    "exported_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "approvals": self.ledger.list_approvals(),
                    "findings": self.ledger.list_findings(),
                    "outbox": self.ledger.list_outbox_items(limit=200),
                },
                req_headers,
            )

        return self._json_response(404, {"error": f"Unknown admin route: {path}"}, req_headers)

    # -------------------------------------------------------------------------
    # Port `:8080` AO/PA Job Portal & OpenAPI Routes
    # -------------------------------------------------------------------------
    def _handle_portal_routes(
        self,
        method: str,
        path: str,
        query: dict[str, str],
        body: bytes,
        principal: AuthPrincipal,
        req_headers: dict[str, str],
    ) -> HTTPResponseEnvelope:
        payload = json.loads(body.decode("utf-8") or "{}") if body else {}

        if path == "/api/v1/schedules/preview" and method == "POST":
            persona = str(payload.get("persona") or principal.persona)
            preview = preview_schedule(
                cron_expr=str(payload.get("schedule_cron", "")),
                tz_name=str(payload.get("timezone", "UTC")),
                count=int(payload.get("count", 5)),
                persona=persona,
                min_ao_interval_minutes=self.config.min_ao_cron_interval_minutes,
            )
            return self._json_response(200, preview, req_headers)

        if path == "/api/v1/schedules" and method == "GET":
            items = self.ledger.list_job_definitions(
                allowed_namespaces=principal.allowed_namespaces,
                persona=query.get("persona"),
                job_class=query.get("job_class"),
            )
            return self._json_response(200, {"items": items}, req_headers)

        if path == "/api/v1/schedules" and method == "POST":
            ns = str(payload.get("namespace") or (
                self.config.namespace if principal.is_pa_admin else principal.allowed_namespaces[0]
            ))
            principal.check_namespace_access(ns, require_write=True)
            req_persona = str(payload.get("persona") or principal.persona).upper()
            if req_persona == "PA" and not principal.is_pa_admin:
                raise AuthorizationError("Only PA Admins may register PA-persona schedules")

            validate_job_security_spec(
                payload,
                approved_templates=self.config.approved_templates,
                allowed_registry_prefixes=self.config.allowed_registry_prefixes,
            )
            job_id = str(payload.get("job_id") or "").strip()
            if not re.match(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$", job_id):
                raise SecurityValidationError("job_id must be a valid DNS-1123 label")

            existing = self.ledger.get_job_definition(job_id)
            if existing:
                principal.check_namespace_access(existing["namespace"], require_write=True)

            cron_preview = preview_schedule(
                cron_expr=str(payload["schedule_cron"]),
                tz_name=str(payload.get("timezone", "UTC")),
                persona=req_persona,
                min_ao_interval_minutes=self.config.min_ao_cron_interval_minutes,
            )

            candidate = {
                **(existing or {}),
                "job_id": job_id,
                "namespace": ns,
                "persona": req_persona,
                "job_class": str(payload.get("job_class", "batch")),
                "template_name": str(payload.get("template_name", "gdc-standard-job-runner-v1")),
                "worker_image": str(payload["worker_image"]),
                "worker_mode": str(payload.get("worker_mode", "batch-watermarked-rollup")),
                "enforcement_mode": str(payload.get("enforcement_mode", "audit")),
                "schedule_cron": cron_preview["cron"],
                "timezone": cron_preview["timezone"],
                "suspended": bool(payload.get("suspended", False)),
                "concurrency_policy": str(payload.get("concurrency_policy", "Forbid")),
                "starting_deadline_secs": int(payload.get("starting_deadline_secs", 300)),
                "active_deadline_secs": int(payload.get("active_deadline_secs", 900)),
                "sla_seconds": int(payload.get("sla_seconds", 900)),
                "max_shards": int(payload.get("max_shards", 10)),
                "parallelism": int(payload.get("parallelism", 5)),
                "max_actions_per_run": int(
                    payload.get("max_actions_per_run", self.config.default_max_actions_per_run)
                ),
                "cooldown_seconds": int(
                    payload.get("cooldown_seconds", self.config.default_cooldown_seconds)
                ),
                "gitops_managed": bool(
                    payload.get("gitops_managed", (existing or {}).get("gitops_managed", False))
                ),
                "gitops_annotations": payload.get(
                    "gitops_annotations", (existing or {}).get("gitops_annotations", {})
                ),
                "parameters": payload.get("parameters", {}),
                "notification_sinks": payload.get("notification_sinks", ["portal-default"]),
                "created_by": (existing or {}).get("created_by") or principal.subject,
            }
            reconcile = self.engine.reconcile_schedule(candidate)
            if reconcile["gitops_protected"] and existing is not None:
                # Do NOT overwrite existing GitOps-managed schedule in DB or cluster!
                return self._json_response(
                    200,
                    {"schedule": existing, "reconcile": reconcile, "preview": cron_preview},
                    req_headers,
                )

            saved = self.ledger.upsert_job_definition(candidate)
            return self._json_response(
                201 if existing is None else 200,
                {"schedule": saved, "reconcile": reconcile, "preview": cron_preview},
                req_headers,
            )

        # Schedule action subroutes: /api/v1/schedules/{job_id}[/pause|/resume|/trigger|/backfill]
        m_sched = re.match(r"^/api/v1/schedules/([a-z0-9-]+)(?:/(pause|resume|trigger|backfill))?$", path)
        if m_sched:
            job_id, action = m_sched.group(1), m_sched.group(2)
            job = self.ledger.get_job_definition(job_id)
            if not job:
                raise KeyError(f"Schedule '{job_id}' not found")
            principal.check_namespace_access(job["namespace"], require_write=(method != "GET"))

            if action is None and method == "GET":
                wm = self.ledger.get_watermark(job_id, "all")
                return self._json_response(200, {"schedule": job, "watermark": wm}, req_headers)

            if action is None and method == "DELETE":
                protected, reason = is_gitops_protected(job, self.config.gitops_mode)
                if protected:
                    reconcile = self.engine.reconcile_schedule(job)
                    return self._json_response(200, {"deleted": False, "reconcile": reconcile}, req_headers)
                cluster_error = ""
                if self.k8s is not None:
                    try:
                        kind = "CronWorkflow" if self.config.engine_mode == "argo" else "CronJob"
                        self.k8s.delete_resource(kind, job["namespace"], job_id)
                    except Exception as exc:
                        cluster_error = str(exc)
                        sys.stderr.write(f"[p15-k8s] Warning: delete {job_id} failed: {exc}\n")
                self.ledger.delete_job_definition(job_id)
                del_payload: dict[str, Any] = {"deleted": True, "job_id": job_id}
                if cluster_error:
                    del_payload["cluster_error"] = cluster_error
                return self._json_response(200, del_payload, req_headers)

            if action in ("pause", "resume") and method == "POST":
                reconcile = self.engine.reconcile_schedule({**job, "suspended": (action == "pause")})
                if reconcile["gitops_protected"]:
                    return self._json_response(200, {"schedule": job, "reconcile": reconcile}, req_headers)
                job["suspended"] = action == "pause"
                saved = self.ledger.upsert_job_definition(job)
                return self._json_response(200, {"schedule": saved, "reconcile": reconcile}, req_headers)

            if action == "trigger" and method == "POST":
                if self.ledger.emergency_pause_all:
                    raise SecurityValidationError("Global Emergency Pause-All Kill-Switch is active")
                now = datetime.now(timezone.utc)
                w_start = normalize_utc_iso(payload.get("window_start") or (now - timedelta(minutes=15)))
                w_end = normalize_utc_iso(payload.get("window_end") or now)
                shards = payload.get("shards") or ["all"]
                run_id = f"{job_id}-run-{uuid.uuid4().hex[:8]}"
                manifest = self.engine.compile_run_manifest(
                    job, run_id=run_id, window_start=w_start, window_end=w_end, shard_keys=shards
                )
                submitted_to_cluster = False
                cluster_error = ""
                if self.k8s is not None and payload.get("dispatch_to_cluster", True):
                    try:
                        self.k8s.apply_manifest(manifest)
                        submitted_to_cluster = True
                    except Exception as exc:
                        cluster_error = str(exc)
                        sys.stderr.write(f"[p15-k8s] Warning: dispatch {manifest['kind']}/{run_id} failed: {exc}\n")
                run_rec = self.ledger.upsert_job_run(
                    {
                        "run_id": run_id,
                        "job_id": job_id,
                        "namespace": job["namespace"],
                        "engine_mode": self.config.engine_mode,
                        "engine_ref": f"{manifest['kind']}/{run_id}",
                        "trigger_type": "manual",
                        "window_start": w_start,
                        "window_end": w_end,
                        "shard_key": ",".join(shards),
                        "status": "Running",
                        "requested_by": principal.subject,
                    }
                )
                resp_payload: dict[str, Any] = {
                    "run": run_rec,
                    "manifest_kind": manifest["kind"],
                    "manifest": manifest,
                    "submitted_to_cluster": submitted_to_cluster,
                }
                if cluster_error:
                    resp_payload["cluster_error"] = cluster_error
                return self._json_response(201, resp_payload, req_headers)

            if action == "backfill" and method == "POST":
                if self.ledger.emergency_pause_all:
                    raise SecurityValidationError("Global Emergency Pause-All Kill-Switch is active")
                windows = generate_utc_windows(
                    start_iso=str(payload["window_start"]),
                    end_iso=str(payload["window_end"]),
                    step_seconds=int(payload.get("step_seconds", 900)),
                )
                created_runs = []
                for idx, (ws, we) in enumerate(windows, 1):
                    run_id = f"{job_id}-bf-{idx:03d}-{uuid.uuid4().hex[:6]}"
                    self.engine.compile_run_manifest(job, run_id=run_id, window_start=ws, window_end=we)
                    created_runs.append(
                        self.ledger.upsert_job_run(
                            {
                                "run_id": run_id,
                                "job_id": job_id,
                                "namespace": job["namespace"],
                                "engine_mode": self.config.engine_mode,
                                "engine_ref": run_id,
                                "trigger_type": "backfill",
                                "window_start": ws,
                                "window_end": we,
                                "shard_key": str(payload.get("shard_key", "all")),
                                "status": "Running",
                                "requested_by": principal.subject,
                            }
                        )
                    )
                return self._json_response(201, {"backfill_runs": created_runs}, req_headers)

        # Runs & Archived Log Retrieval (`Content-Disposition: attachment` + `nosniff`)
        if path == "/api/v1/runs" and method == "GET":
            runs = self.ledger.list_job_runs(
                job_id=query.get("job_id"),
                allowed_namespaces=principal.allowed_namespaces,
                status=query.get("status"),
            )
            return self._json_response(200, {"items": runs}, req_headers)

        m_run_log = re.match(r"^/api/v1/runs/([A-Za-z0-9._-]+)/logs$", path)
        if m_run_log and method == "GET":
            run_id = m_run_log.group(1)
            run = self.ledger.get_job_run(run_id)
            if not run:
                raise KeyError(f"Run '{run_id}' not found")
            principal.check_namespace_access(run["namespace"], require_write=False)
            log_key = query.get("key") or build_job_artifact_key(
                run["namespace"], run["job_id"], run_id, "stdout.log"
            )
            validate_object_key(log_key)
            content = redact_secrets(self.storage.get_text(log_key))
            hdrs = dict(DEFAULT_SECURITY_HEADERS)
            hdrs["Content-Type"] = "text/plain; charset=utf-8"
            hdrs["Content-Disposition"] = f'attachment; filename="{run_id}.log"'
            return HTTPResponseEnvelope(200, content.encode("utf-8"), hdrs)

        m_run_done = re.match(r"^/api/v1/runs/([A-Za-z0-9._-]+)/complete$", path)
        if m_run_done and method == "POST":
            run_id = m_run_done.group(1)
            run = self.ledger.get_job_run(run_id)
            if not run:
                raise KeyError(f"Run '{run_id}' not found")
            principal.check_namespace_access(run["namespace"], require_write=True)
            exit_code = int(payload.get("exit_code", 0))
            log_text = str(payload.get("logs", ""))
            artifact_uri = payload.get("artifact_uri")
            if log_text:
                log_key = build_job_artifact_key(
                    run["namespace"], run["job_id"], run_id, "stdout.log"
                )
                artifact_uri = self.storage.put_text(log_key, log_text, redact=True)
            outcome = self.healing.record_run_outcome(
                job_id=run["job_id"],
                run_id=run_id,
                exit_code=exit_code,
                summary=payload.get("summary") or {},
                artifact_uri=artifact_uri,
            )
            if exit_code == 0 and payload.get("watermark_end"):
                self.ledger.advance_watermark(
                    run["job_id"],
                    run.get("shard_key", "all"),
                    str(payload["watermark_end"]),
                    object_uri=artifact_uri,
                )
            if payload.get("violations"):
                enf_res = self.healing.evaluate_violations(
                    job_id=run["job_id"],
                    run_id=run_id,
                    violations=list(payload["violations"]),
                    requested_by=run.get("requested_by") or principal.subject,
                )
                outcome["enforcement"] = enf_res
            return self._json_response(200, outcome, req_headers)

        # Enforcement Findings, Four-Eyes Approvals & 1-Click Snapshot Rollback
        if path == "/api/v1/findings" and method == "GET":
            items = self.ledger.list_findings(
                allowed_namespaces=principal.allowed_namespaces,
                status=query.get("status"),
            )
            return self._json_response(200, {"items": items}, req_headers)

        m_decide = re.match(r"^/api/v1/approvals/([A-Za-z0-9._-]+)/decide$", path)
        if m_decide and method == "POST":
            res = self.healing.decide_approval(
                finding_id=m_decide.group(1),
                approver=principal,
                decision=str(payload.get("decision", "")),
                reason=str(payload.get("reason", "")),
                expected_patch_sha256=payload.get("planned_patch_sha256"),
            )
            return self._json_response(200, res, req_headers)

        m_rb = re.match(r"^/api/v1/approvals/([A-Za-z0-9._-]+)/rollback$", path)
        if m_rb and method == "POST":
            res = self.healing.rollback_remediation(
                finding_id=m_rb.group(1),
                actor=principal,
                reason=str(payload.get("reason", "Operator rollback")),
            )
            return self._json_response(200, res, req_headers)

        # Notification Sinks, Self-Test & Outbox Visibility
        if path == "/api/v1/notifications/sinks" and method == "POST":
            ns = str(payload.get("namespace") or (
                self.config.namespace if principal.is_pa_admin else principal.allowed_namespaces[0]
            ))
            principal.check_namespace_access(ns, require_write=True)
            sink_pub = self.notifier.register_sink({**payload, "namespace": ns})
            return self._json_response(201, {"sink": sink_pub}, req_headers)

        m_sink_test = re.match(r"^/api/v1/notifications/sinks/([A-Za-z0-9._-]+)/test$", path)
        if m_sink_test and method == "POST":
            sink_name = m_sink_test.group(1)
            sink_cfg = self.ledger.get_sink(sink_name)
            if not sink_cfg:
                raise KeyError(f"Sink '{sink_name}' not found")
            if sink_cfg["namespace"] != "*":
                principal.check_namespace_access(sink_cfg["namespace"], require_write=True)
            res = self.notifier.test_sink(sink_name, actor=principal.subject)
            return self._json_response(200, res, req_headers)

        if path == "/api/v1/notifications/outbox" and method == "GET":
            items = self.ledger.list_outbox_items(
                allowed_namespaces=principal.allowed_namespaces,
                status=query.get("status"),
            )
            return self._json_response(200, {"items": items}, req_headers)

        return self._json_response(404, {"error": f"Unknown portal route: {path}"}, req_headers)


def build_openapi_spec(surface: str = "portal") -> dict[str, Any]:
    """Generate OpenAPI 3.1 specification for `:8080` Portal or `:8081` PA Admin Console."""
    if surface == "admin":
        paths = {
            "/healthz": {"get": {"summary": "Liveness check"}},
            "/admin/v1/overview": {"get": {"summary": "Org-wide job & governance overview"}},
            "/admin/v1/kill-switch": {"post": {"summary": "Global Emergency Pause-All Kill-Switch"}},
            "/admin/v1/allowed-hosts": {"put": {"summary": "Update PA SSRF notification host allowlist"}},
            "/admin/v1/quotas": {"put": {"summary": "Set per-namespace concurrency & shard quotas"}},
            "/admin/v1/audit-export": {"get": {"summary": "Export immutable approval & outbox ledger"}},
        }
    else:
        paths = {
            "/healthz": {"get": {"summary": "Liveness check"}},
            "/readyz": {"get": {"summary": "PostgreSQL readiness check"}},
            "/metrics": {"get": {"summary": "Prometheus exposition metrics"}},
            "/api/v1/schedules": {
                "get": {"summary": "List authorised job schedules"},
                "post": {"summary": "Create or update job schedule"},
            },
            "/api/v1/schedules/preview": {"post": {"summary": "Preview next-5 UTC/local runs & DST warnings"}},
            "/api/v1/schedules/{job_id}": {
                "get": {"summary": "Inspect schedule & watermark"},
                "delete": {"summary": "Delete schedule"},
            },
            "/api/v1/schedules/{job_id}/pause": {"post": {"summary": "Pause schedule"}},
            "/api/v1/schedules/{job_id}/resume": {"post": {"summary": "Resume schedule"}},
            "/api/v1/schedules/{job_id}/trigger": {"post": {"summary": "Trigger immediate run"}},
            "/api/v1/schedules/{job_id}/backfill": {"post": {"summary": "Trigger UTC window backfill"}},
            "/api/v1/runs": {"get": {"summary": "List job runs"}},
            "/api/v1/runs/{run_id}/logs": {"get": {"summary": "Download redacted archived run logs"}},
            "/api/v1/runs/{run_id}/complete": {"post": {"summary": "Record worker completion & findings"}},
            "/api/v1/findings": {"get": {"summary": "List compliance/enforcement findings"}},
            "/api/v1/approvals/{finding_id}/decide": {"post": {"summary": "Approve/reject HITL remediation"}},
            "/api/v1/approvals/{finding_id}/rollback": {"post": {"summary": "Rollback pre-action snapshot"}},
            "/api/v1/notifications/sinks": {"post": {"summary": "Register air-gapped notification sink"}},
            "/api/v1/notifications/sinks/{name}/test": {"post": {"summary": "Send test notification"}},
            "/api/v1/notifications/outbox": {"get": {"summary": "List transactional outbox entries"}},
        }
    return {
        "openapi": "3.1.0",
        "info": {
            "title": f"GDC-ag Pattern 15 Job Orchestrator ({surface})",
            "version": "1.3.0",
        },
        "paths": paths,
    }


def create_fastapi_surface_app(hub: ControlPlaneHub, surface: str = "portal") -> Any:
    """Build production FastAPI ASGI application binding `ControlPlaneHub` (`:8080` or `:8081`)."""
    if FastAPI is None or Request is None or Response is None:  # pragma: no cover
        raise RuntimeError("fastapi must be installed to run create_fastapi_surface_app")

    app = FastAPI(
        title=f"GDC-ag Pattern 15 Job Orchestrator ({surface})",
        version="1.3.0",
        openapi_url=None,
        docs_url=None,
        redoc_url=None,
    )

    async def _dispatch(request, full_path=""):
        raw_body = await request.body()
        raw_path = "/" + full_path
        if request.url.query:
            raw_path = f"{raw_path}?{request.url.query}"
        env = hub.handle_http(
            surface=surface,
            method=request.method,
            raw_path=raw_path,
            headers=dict(request.headers),
            body=raw_body,
        )
        return Response(content=env.body, status_code=env.status_code, headers=env.headers)

    # Bind real class annotations (not deferred PEP 563 strings) before route registration
    # so FastAPI always injects `starlette.requests.Request` instead of a query parameter.
    _dispatch.__annotations__ = {"request": Request, "full_path": str, "return": Response}
    app.add_api_route(
        "/{full_path:path}",
        _dispatch,
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    )

    return app


def main() -> None:  # pragma: no cover - container entrypoint running :8080, :8081 & :9091
    import threading
    import time
    import uvicorn  # type: ignore

    hub = ControlPlaneHub()
    portal_app = create_fastapi_surface_app(hub, surface="portal")
    admin_app = create_fastapi_surface_app(hub, surface="admin")

    def _bg_loop() -> None:
        while True:
            try:
                hub.run_background_maintenance_tick()
            except Exception:
                pass
            time.sleep(5.0)

    threading.Thread(target=_bg_loop, daemon=True, name="p15-lease-loops").start()
    threading.Thread(
        target=lambda: uvicorn.run(admin_app, host="0.0.0.0", port=8081, log_level="info"),
        daemon=True,
        name="p15-admin-8081",
    ).start()
    uvicorn.run(portal_app, host="0.0.0.0", port=8080, log_level="info")


if __name__ == "__main__":
    main()
