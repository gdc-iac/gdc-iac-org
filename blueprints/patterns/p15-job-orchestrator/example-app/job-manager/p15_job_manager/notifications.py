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
"""Vendor-Neutral Pluggable Notification Sink SDK & Transactional Outbox Dispatcher (`REQ-NOTIF-002`–`005`, `REQ-REL-002`)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
import hashlib
import hmac
import json
import os
import smtplib
import threading
import time
from typing import Any, Callable
from urllib.parse import urlparse
import uuid

import httpx

from .config import ControlPlaneConfig
from .cron_utils import normalize_utc_iso
from .ledger import LedgerStore
from .metrics import MetricsRegistry
from .security import SecurityValidationError, validate_notification_target

BACKOFF_SCHEDULE_SECONDS = (30, 120, 600, 1800)
MAX_OUTBOX_ATTEMPTS = len(BACKOFF_SCHEDULE_SECONDS)

SUPPORTED_EVENT_TYPES = frozenset(
    {
        "OnFailure",
        "OnRecovery",
        "OnSLAExceeded",
        "OnViolationDetected",
        "OnApprovalRequired",
        "OnAutoHealExecuted",
        "OnCircuitBreakerOpen",
        "OnSuccess",
        "OnSinkTest",
    }
)


class NotificationDeliveryError(RuntimeError):
    """Raised when an external air-gapped notification sink rejects or fails delivery."""


def _http_error_detail(resp: httpx.Response) -> str:
    try:
        data = resp.json()
        if isinstance(data, dict) and data.get("error"):
            err = str(data["error"]).strip()[:80]
            if err:
                return f" ({err})"
    except Exception:
        pass
    return ""


@dataclass(frozen=True)
class JobNotificationEvent:
    """Canonical signed notification payload delivered across all air-gapped sink adapters."""

    event_id: str
    timestamp_utc: str
    event_type: str
    severity: str  # "info" | "warning" | "high" | "critical"
    persona: str
    namespace: str
    job_name: str
    run_id: str
    summary: str
    details: dict[str, Any]
    artifact_uri: str = ""
    runbook_url: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "timestamp_utc": self.timestamp_utc,
            "event_type": self.event_type,
            "severity": self.severity,
            "persona": self.persona,
            "namespace": self.namespace,
            "job_name": self.job_name,
            "run_id": self.run_id,
            "summary": self.summary,
            "details": self.details,
            "artifact_uri": self.artifact_uri,
            "runbook_url": self.runbook_url,
        }


def compute_hmac_signature(shared_secret: str, raw_body: bytes) -> str:
    """Compute `X-P15-Signature-256` (`sha256=<hex>`) over canonical request bytes."""
    digest = hmac.new(shared_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def verify_hmac_signature(shared_secret: str, raw_body: bytes, signature_header: str) -> bool:
    """Constant-time verification helper for downstream air-gapped webhook receivers."""
    expected = compute_hmac_signature(shared_secret, raw_body)
    return hmac.compare_digest(expected, (signature_header or "").strip())


class NotificationSinkAdapter(ABC):
    """Public plugin interface (`REQ-NOTIF-005`) for custom air-gapped notification sinks."""

    def __init__(self, sink_config: dict[str, Any], cp_config: ControlPlaneConfig) -> None:
        self.sink_config = sink_config
        self.cp_config = cp_config

    @abstractmethod
    def validate_config(self) -> None:
        """Validate sink parameters before registration (raises `SecurityValidationError` on error)."""

    @abstractmethod
    def send(self, event: JobNotificationEvent) -> tuple[int, str]:
        """Deliver `event`; return `(status_code, diagnostic_message)` or raise on transient error."""

    def health_check(self) -> dict[str, Any]:
        """Execute a lightweight configuration & connectivity self-test."""
        self.validate_config()
        return {"sink": self.sink_config.get("name"), "type": self.sink_config.get("type"), "ok": True}

    def _ca_verify(self) -> str | bool:
        ca = self.sink_config.get("ca_bundle") or self.cp_config.ca_bundle_path
        if isinstance(ca, str) and ca and os.path.exists(ca):
            return ca
        return True

    def _resolve_secret(self, key: str, default: str = "") -> str:
        env_ref = self.sink_config.get(f"{key}_env")
        if env_ref and os.getenv(str(env_ref)):
            return str(os.getenv(str(env_ref)))
        return str(self.sink_config.get(key, default))


class GenericWebhookAdapter(NotificationSinkAdapter):
    """Primary vendor-neutral HTTPS webhook adapter with `X-P15-Signature-256` HMAC-SHA256."""

    def __init__(
        self,
        sink_config: dict[str, Any],
        cp_config: ControlPlaneConfig,
        http_transport: httpx.BaseTransport | None = None,
    ) -> None:
        super().__init__(sink_config, cp_config)
        self._transport = http_transport

    def validate_config(self) -> None:
        validate_notification_target(
            str(self.sink_config.get("url", "")),
            allowed_hosts=self.cp_config.allowed_notification_hosts,
            sink_type="generic-webhook",
            allow_http_emulation=self.cp_config.allow_http_emulation_sinks,
        )

    def send(self, event: JobNotificationEvent) -> tuple[int, str]:
        self.validate_config()
        body = json.dumps(event.to_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "X-P15-Event-Id": event.event_id,
            "X-P15-Event-Type": event.event_type,
        }
        secret = self._resolve_secret("hmac_secret")
        if secret:
            headers["X-P15-Signature-256"] = compute_hmac_signature(secret, body)

        try:
            with httpx.Client(
                timeout=5.0,
                follow_redirects=False,
                trust_env=False,
                verify=self._ca_verify(),
                transport=self._transport,
            ) as client:
                resp = client.post(str(self.sink_config["url"]), content=body, headers=headers)
        except httpx.HTTPError as exc:
            raise NotificationDeliveryError(f"Webhook delivery error: {type(exc).__name__}: {exc}") from exc
        if resp.status_code >= 400:
            raise NotificationDeliveryError(
                f"Webhook returned HTTP {resp.status_code}{_http_error_detail(resp)}"
            )
        return resp.status_code, "delivered"


class ChatWebhookAdapter(GenericWebhookAdapter):
    """Templated webhook adapter for self-hosted air-gapped chat tools (Mattermost, Rocket.Chat, Matrix)."""

    def send(self, event: JobNotificationEvent) -> tuple[int, str]:
        self.validate_config()
        message_text = (
            f"[{event.severity.upper()}] {event.event_type} | {event.namespace}/{event.job_name} "
            f"(run={event.run_id}): {event.summary}"
        )
        text_field = str(self.sink_config.get("text_field") or "text")
        payload = {
            text_field: message_text,
            "username": str(self.sink_config.get("bot_name") or "p15-job-orchestrator"),
            "event": event.to_dict(),
        }
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        headers = {"Content-Type": "application/json", "X-P15-Event-Id": event.event_id}
        secret = self._resolve_secret("hmac_secret")
        if secret:
            headers["X-P15-Signature-256"] = compute_hmac_signature(secret, body)

        try:
            with httpx.Client(
                timeout=5.0,
                follow_redirects=False,
                trust_env=False,
                verify=self._ca_verify(),
                transport=self._transport,
            ) as client:
                resp = client.post(str(self.sink_config["url"]), content=body, headers=headers)
        except httpx.HTTPError as exc:
            raise NotificationDeliveryError(f"Chat webhook delivery error: {type(exc).__name__}: {exc}") from exc
        if resp.status_code >= 400:
            raise NotificationDeliveryError(
                f"Chat webhook returned HTTP {resp.status_code}{_http_error_detail(resp)}"
            )
        return resp.status_code, "delivered"


# Illustrative ITSM field mappings (ServiceNow is strictly one optional example alongside Jira SM / custom APIs)
ITSM_PRESET_MAPPINGS: dict[str, dict[str, str]] = {
    "generic-itsm": {
        "title": "summary",
        "priority": "severity",
        "source_system": "persona",
        "external_id": "event_id",
        "artifact_link": "artifact_uri",
    },
    "servicenow-example": {
        "short_description": "summary",
        "severity": "severity",
        "u_namespace": "namespace",
        "u_job_name": "job_name",
        "u_correlation_id": "event_id",
        "work_notes": "runbook_url",
    },
    "jira-sm-example": {
        "summary": "summary",
        "priority_label": "severity",
        "service_namespace": "namespace",
        "job_key": "job_name",
        "event_uid": "event_id",
    },
}


class ItsmWebhookAdapter(GenericWebhookAdapter):
    """Vendor-neutral ITSM ticket/event webhook adapter with configurable field mapping."""

    def send(self, event: JobNotificationEvent) -> tuple[int, str]:
        self.validate_config()
        ev_dict = event.to_dict()
        preset_name = str(self.sink_config.get("preset") or "generic-itsm")
        field_map = dict(ITSM_PRESET_MAPPINGS.get(preset_name, ITSM_PRESET_MAPPINGS["generic-itsm"]))
        if isinstance(self.sink_config.get("field_mapping"), dict):
            field_map.update(self.sink_config["field_mapping"])

        mapped_payload: dict[str, Any] = {
            dest_key: ev_dict.get(src_key, "") for dest_key, src_key in field_map.items()
        }
        mapped_payload["raw_event"] = ev_dict

        body = json.dumps(mapped_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        headers = {"Content-Type": "application/json", "X-P15-Event-Id": event.event_id}
        secret = self._resolve_secret("hmac_secret")
        if secret:
            headers["X-P15-Signature-256"] = compute_hmac_signature(secret, body)

        try:
            with httpx.Client(
                timeout=5.0,
                follow_redirects=False,
                trust_env=False,
                verify=self._ca_verify(),
                transport=self._transport,
            ) as client:
                resp = client.post(str(self.sink_config["url"]), content=body, headers=headers)
        except httpx.HTTPError as exc:
            raise NotificationDeliveryError(f"ITSM webhook delivery error: {type(exc).__name__}: {exc}") from exc
        if resp.status_code >= 400:
            raise NotificationDeliveryError(
                f"ITSM webhook returned HTTP {resp.status_code}{_http_error_detail(resp)}"
            )
        return resp.status_code, "delivered"


class SmtpRelayAdapter(NotificationSinkAdapter):
    """Internal air-gapped SMTP relay adapter (`STARTTLS` + Secret-backed authentication)."""

    def __init__(
        self,
        sink_config: dict[str, Any],
        cp_config: ControlPlaneConfig,
        mail_sender: Callable[[EmailMessage, str, int], None] | None = None,
    ) -> None:
        super().__init__(sink_config, cp_config)
        self._mail_sender = mail_sender

    def validate_config(self) -> None:
        validate_notification_target(
            str(self.sink_config.get("url", "")),
            allowed_hosts=self.cp_config.allowed_notification_hosts,
            sink_type="smtp-relay",
            allow_http_emulation=self.cp_config.allow_http_emulation_sinks,
        )
        if not self.sink_config.get("recipients"):
            raise SecurityValidationError("smtp-relay sink requires non-empty 'recipients' list")

    def send(self, event: JobNotificationEvent) -> tuple[int, str]:
        self.validate_config()
        parsed = urlparse(str(self.sink_config["url"]))
        host = parsed.hostname or ""
        port = parsed.port or (465 if parsed.scheme == "smtps" else 587)
        sender = str(self.sink_config.get("sender") or "p15-jobs-noreply@gdc.local")
        recipients = self.sink_config["recipients"]
        if isinstance(recipients, str):
            recipients = [r.strip() for r in recipients.split(",") if r.strip()]

        msg = EmailMessage()
        msg["Subject"] = f"[GDC Jobs {event.severity.upper()}] {event.event_type}: {event.namespace}/{event.job_name}"
        msg["From"] = sender
        msg["To"] = ", ".join(recipients)
        msg.set_content(
            f"Event ID   : {event.event_id}\n"
            f"Timestamp  : {event.timestamp_utc}\n"
            f"Event Type : {event.event_type}\n"
            f"Severity   : {event.severity}\n"
            f"Namespace  : {event.namespace}\n"
            f"Job / Run  : {event.job_name} / {event.run_id}\n"
            f"Summary    : {event.summary}\n"
            f"Artifact   : {event.artifact_uri}\n"
            f"Runbook    : {event.runbook_url}\n"
        )

        if self._mail_sender is not None:
            self._mail_sender(msg, host, port)
            return 250, "smtp_delivered"

        try:
            with smtplib.SMTP(host=host, port=port, timeout=5) as smtp:
                if self.sink_config.get("starttls", True):
                    smtp.starttls()
                user = self._resolve_secret("smtp_username")
                pwd = self._resolve_secret("smtp_password")
                if user and pwd:
                    smtp.login(user, pwd)
                smtp.send_message(msg)
        except (smtplib.SMTPException, OSError) as exc:
            raise NotificationDeliveryError(f"SMTP relay delivery error: {type(exc).__name__}: {exc}") from exc
        return 250, "smtp_delivered"


class PortalFeedAdapter(NotificationSinkAdapter):
    """Built-in zero-external-dependency in-portal audit feed."""

    def validate_config(self) -> None:
        return None

    def send(self, event: JobNotificationEvent) -> tuple[int, str]:
        return 200, f"portal-feed:{event.event_id}"


SINK_ADAPTER_REGISTRY: dict[str, type[NotificationSinkAdapter]] = {
    "generic-webhook": GenericWebhookAdapter,
    "chat-webhook": ChatWebhookAdapter,
    "itsm-webhook": ItsmWebhookAdapter,
    "smtp-relay": SmtpRelayAdapter,
    "portal-feed": PortalFeedAdapter,
}


def register_sink_adapter(sink_type: str, adapter_cls: type[NotificationSinkAdapter]) -> None:
    """Register a custom `NotificationSinkAdapter` implementation (`REQ-NOTIF-005`)."""
    if not issubclass(adapter_cls, NotificationSinkAdapter):
        raise TypeError("adapter_cls must subclass NotificationSinkAdapter")
    SINK_ADAPTER_REGISTRY[sink_type.strip().lower()] = adapter_cls


def _in_quiet_hours(quiet_spec: str, now_utc: datetime) -> bool:
    """Evaluate `HH:MM-HH:MM` UTC quiet-hours window (supports overnight wrap e.g. `22:00-06:00`)."""
    spec = (quiet_spec or "").strip()
    if not spec or "-" not in spec:
        return False
    start_s, end_s = spec.split("-", 1)
    sh, sm = (int(x) for x in start_s.strip().split(":", 1))
    eh, em = (int(x) for x in end_s.strip().split(":", 1))
    cur_min = now_utc.hour * 60 + now_utc.minute
    start_min = sh * 60 + sm
    end_min = eh * 60 + em
    if start_min <= end_min:
        return start_min <= cur_min < end_min
    return cur_min >= start_min or cur_min < end_min


class NotificationRouter:
    """Transactional-outbox router enforcing deduplication, token-bucket rate limits & quiet hours."""

    def __init__(
        self,
        config: ControlPlaneConfig,
        ledger: LedgerStore,
        metrics: MetricsRegistry,
        adapter_kwargs: dict[str, Any] | None = None,
    ) -> None:
        self.config = config
        self.ledger = ledger
        self.metrics = metrics
        self._adapter_kwargs = adapter_kwargs or {}
        self._rate_lock = threading.Lock()
        self._sink_tokens: dict[str, tuple[float, float]] = {}

    def build_adapter(self, sink_cfg: dict[str, Any]) -> NotificationSinkAdapter:
        sink_type = str(sink_cfg.get("type") or "").strip().lower()
        adapter_cls = SINK_ADAPTER_REGISTRY.get(sink_type)
        if adapter_cls is None:
            raise SecurityValidationError(
                f"Unknown notification sink type {sink_type!r}; registered: {sorted(SINK_ADAPTER_REGISTRY)}"
            )
        extra = self._adapter_kwargs.get(sink_type, {})
        return adapter_cls(sink_cfg, self.config, **extra)

    def register_sink(self, sink_cfg: dict[str, Any]) -> dict[str, Any]:
        name = str(sink_cfg.get("name") or "").strip()
        if not name:
            raise SecurityValidationError("Sink 'name' is required")
        events = sink_cfg.get("events") or ["OnFailure", "OnSLAExceeded", "OnCircuitBreakerOpen"]
        unknown_ev = [e for e in events if e not in SUPPORTED_EVENT_TYPES]
        if unknown_ev:
            raise SecurityValidationError(f"Unsupported event subscription(s): {unknown_ev}")
        adapter = self.build_adapter(sink_cfg)
        adapter.validate_config()
        sink_type = str(sink_cfg["type"]).strip().lower()
        hmac_secret = str(sink_cfg.get("hmac_secret") or "")
        hmac_secret_env = str(sink_cfg.get("hmac_secret_env") or "")
        if (
            sink_type in ("generic-webhook", "chat-webhook", "itsm-webhook")
            and not hmac_secret
            and not hmac_secret_env
            and os.getenv("WEBHOOK_HMAC_SECRET")
        ):
            hmac_secret_env = "WEBHOOK_HMAC_SECRET"
        stored = {
            **sink_cfg,
            "name": name,
            "namespace": str(sink_cfg.get("namespace") or self.config.namespace),
            "type": sink_type,
            "url": str(sink_cfg.get("url") or "internal://portal-feed"),
            "events": list(events),
            "dedup_window_seconds": int(
                sink_cfg.get("dedup_window_seconds", self.config.dedup_window_seconds)
            ),
            "preset": sink_cfg.get("preset"),
            "field_mapping": sink_cfg.get("field_mapping"),
            "recipients": sink_cfg.get("recipients"),
            "hmac_secret": hmac_secret,
            "hmac_secret_env": hmac_secret_env,
            "enabled": bool(sink_cfg.get("enabled", True)),
        }
        self.ledger.upsert_sink(stored)
        # Return sanitized public representation (never echo raw hmac_secret!)
        pub = dict(stored)
        pub.pop("hmac_secret", None)
        pub["has_hmac_secret"] = bool(stored.get("hmac_secret") or stored.get("hmac_secret_env"))
        return pub

    def test_sink(self, sink_name: str, actor: str = "operator") -> dict[str, Any]:
        """Execute `[Send Test Notification]` (`REQ-NOTIF-004`) returning status and latency."""
        sink_cfg = self.ledger.get_sink(sink_name)
        if not sink_cfg:
            raise KeyError(f"Notification sink '{sink_name}' not found")
        adapter = self.build_adapter(sink_cfg)
        now = datetime.now(timezone.utc)
        now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        test_event = JobNotificationEvent(
            event_id=f"evt-test-{uuid.uuid4().hex[:10]}",
            timestamp_utc=now_iso,
            event_type="OnSinkTest",
            severity="info",
            persona="PA",
            namespace=sink_cfg["namespace"],
            job_name="sink-connectivity-self-test",
            run_id="self-test",
            summary=f"Connectivity test triggered by {actor} for sink '{sink_name}'",
            details={"tested_by": actor, "sink_type": sink_cfg["type"]},
        )
        t0 = time.monotonic()
        code, msg = adapter.send(test_event)
        latency_ms = round((time.monotonic() - t0) * 1000.0, 2)
        delivered_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        dedup_key = hashlib.sha256(
            f"{sink_cfg['namespace']}:sink-connectivity-self-test:OnSinkTest:{test_event.event_id}".encode("utf-8")
        ).hexdigest()[:24]
        outbox_row = self.ledger.enqueue_outbox_item(
            {
                "event_id": test_event.event_id,
                "dedup_key": dedup_key,
                "sink_name": sink_name,
                "sink_type": sink_cfg["type"],
                "namespace": sink_cfg["namespace"],
                "job_id": test_event.job_name,
                "event_type": "OnSinkTest",
                "severity": "info",
                "payload_json": test_event.to_dict(),
                "status": "delivered",
                "attempts": 1,
                "created_at": now_iso,
                "next_retry_at": now_iso,
                "last_status_code": code,
                "delivered_at": delivered_iso,
            }
        )
        return {
            "sink": sink_name,
            "status_code": code,
            "message": msg,
            "latency_ms": latency_ms,
            "outbox_id": outbox_row["outbox_id"],
            "hmac_signed": bool(sink_cfg.get("hmac_secret") or sink_cfg.get("hmac_secret_env")),
        }

    def _consume_rate_token(self, sink_name: str) -> bool:
        capacity = float(max(1, self.config.sink_rate_limit_per_minute))
        refill_per_sec = capacity / 60.0
        now = time.monotonic()
        with self._rate_lock:
            tokens, last_ts = self._sink_tokens.get(sink_name, (capacity, now))
            tokens = min(capacity, tokens + (now - last_ts) * refill_per_sec)
            if tokens < 1.0:
                self._sink_tokens[sink_name] = (tokens, now)
                return False
            self._sink_tokens[sink_name] = (tokens - 1.0, now)
            return True

    def enqueue_event(
        self,
        event: JobNotificationEvent,
        sink_names: list[str] | None = None,
        error_signature: str = "default",
        now_utc: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Persist event atomically into `notification_outbox` with dedup & quiet-hours checks."""
        when = (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
        targets = sink_names or ["portal-default"]
        if "portal-default" not in targets:
            targets = list(targets) + ["portal-default"]

        dedup_raw = f"{event.namespace}:{event.job_name}:{event.event_type}:{error_signature}"
        dedup_key = hashlib.sha256(dedup_raw.encode("utf-8")).hexdigest()[:24]

        queued: list[dict[str, Any]] = []
        for s_name in targets:
            sink_cfg = self.ledger.get_sink(s_name)
            if not sink_cfg or not sink_cfg.get("enabled", True):
                continue
            subscribed = sink_cfg.get("events") or []
            if subscribed and event.event_type not in subscribed and event.event_type != "OnSinkTest":
                continue

            dedup_window = int(sink_cfg.get("dedup_window_seconds", self.config.dedup_window_seconds))
            if dedup_window > 0 and self.ledger.has_recent_delivered_dedup(
                dedup_key, s_name, dedup_window, now_utc=when
            ):
                queued.append(
                    self.ledger.enqueue_outbox_item(
                        {
                            "event_id": event.event_id,
                            "dedup_key": dedup_key,
                            "sink_name": s_name,
                            "sink_type": sink_cfg["type"],
                            "namespace": event.namespace,
                            "job_id": event.job_name,
                            "event_type": event.event_type,
                            "severity": event.severity,
                            "payload_json": event.to_dict(),
                            "status": "deduplicated",
                            "created_at": normalize_utc_iso(when),
                        }
                    )
                )
                continue

            # Quiet-hours suppression for low-urgency alerts (`info`/`warning`); `critical`/`high` always deliver!
            if (
                s_name != "portal-default"
                and event.severity in ("info", "warning")
                and _in_quiet_hours(self.config.quiet_hours_utc, when)
            ):
                queued.append(
                    self.ledger.enqueue_outbox_item(
                        {
                            "event_id": event.event_id,
                            "dedup_key": dedup_key,
                            "sink_name": s_name,
                            "sink_type": sink_cfg["type"],
                            "namespace": event.namespace,
                            "job_id": event.job_name,
                            "event_type": event.event_type,
                            "severity": event.severity,
                            "payload_json": event.to_dict(),
                            "status": "suppressed_quiet_hours",
                            "created_at": normalize_utc_iso(when),
                        }
                    )
                )
                continue

            queued.append(
                self.ledger.enqueue_outbox_item(
                    {
                        "event_id": event.event_id,
                        "dedup_key": dedup_key,
                        "sink_name": s_name,
                        "sink_type": sink_cfg["type"],
                        "namespace": event.namespace,
                        "job_id": event.job_name,
                        "event_type": event.event_type,
                        "severity": event.severity,
                        "payload_json": event.to_dict(),
                        "status": "pending",
                        "created_at": normalize_utc_iso(when),
                        "next_retry_at": normalize_utc_iso(when),
                    }
                )
            )
        return queued

    def process_pending_outbox(self, batch_size: int = 25, now_utc: datetime | None = None) -> dict[str, int]:
        """Dispatch pending outbox items (invoked under K8s `Lease` leadership)."""
        when = (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
        pending = self.ledger.claim_pending_outbox_batch(limit=batch_size, now_utc=when)
        stats = {"delivered": 0, "deduplicated": 0, "retried": 0, "dead_letter": 0}

        for row in pending:
            sink_name = row["sink_name"]
            sink_cfg = self.ledger.get_sink(sink_name)
            if not sink_cfg:
                self.ledger.update_outbox_item(
                    row["outbox_id"],
                    status="dead_letter",
                    attempts=row["attempts"] + 1,
                    last_error="Sink configuration removed",
                )
                self.metrics.inc_dead_letter(row["namespace"], sink_name)
                stats["dead_letter"] += 1
                continue

            dedup_window = int(sink_cfg.get("dedup_window_seconds", self.config.dedup_window_seconds))
            if dedup_window > 0 and self.ledger.has_recent_delivered_dedup(
                row["dedup_key"], sink_name, dedup_window, now_utc=when
            ):
                self.ledger.update_outbox_item(
                    row["outbox_id"],
                    status="deduplicated",
                    attempts=row["attempts"],
                    last_error="Suppressed duplicate within deduplication window",
                )
                stats["deduplicated"] += 1
                continue

            if sink_name != "portal-default" and not self._consume_rate_token(sink_name):
                retry_at = normalize_utc_iso(when + timedelta(seconds=30))
                self.ledger.update_outbox_item(
                    row["outbox_id"],
                    status="pending",
                    attempts=row["attempts"],
                    next_retry_at=retry_at,
                    last_error="Deferred by per-sink token-bucket rate limiter",
                )
                stats["retried"] += 1
                continue

            ev = JobNotificationEvent(**row["payload_json"])
            attempts = int(row["attempts"]) + 1
            try:
                adapter = self.build_adapter(sink_cfg)
                code, _ = adapter.send(ev)
                self.ledger.update_outbox_item(
                    row["outbox_id"],
                    status="delivered",
                    attempts=attempts,
                    last_status_code=code,
                    last_error=None,
                    delivered_at=normalize_utc_iso(when),
                )
                stats["delivered"] += 1
            except Exception as exc:
                err_msg = str(exc)[:300]
                if attempts >= MAX_OUTBOX_ATTEMPTS:
                    self.ledger.update_outbox_item(
                        row["outbox_id"],
                        status="dead_letter",
                        attempts=attempts,
                        last_error=err_msg,
                    )
                    self.metrics.inc_dead_letter(row["namespace"], sink_name)
                    stats["dead_letter"] += 1
                else:
                    delay = BACKOFF_SCHEDULE_SECONDS[min(attempts - 1, len(BACKOFF_SCHEDULE_SECONDS) - 1)]
                    retry_at = normalize_utc_iso(when + timedelta(seconds=delay))
                    self.ledger.update_outbox_item(
                        row["outbox_id"],
                        status="pending",
                        attempts=attempts,
                        next_retry_at=retry_at,
                        last_error=err_msg,
                    )
                    stats["retried"] += 1

        return stats
