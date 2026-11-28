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
"""Runtime configuration for `p15-job-manager`."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
import secrets


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_csv(name: str, default: str = "") -> list[str]:
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass
class ControlPlaneConfig:
    """Immutable control-plane configuration resolved from Kubernetes Secrets & ConfigMaps."""

    project_id: str = field(default_factory=lambda: os.getenv("PROJECT_ID", "my-gdc-project"))
    namespace: str = field(default_factory=lambda: os.getenv("NAMESPACE", "test-project"))
    engine_mode: str = field(default_factory=lambda: os.getenv("ENGINE_MODE", "argo"))
    gitops_mode: str = field(default_factory=lambda: os.getenv("GITOPS_MODE", "direct-apply"))
    allow_simulated_oidc: bool = field(
        default_factory=lambda: _env_bool("ALLOW_SIMULATED_OIDC", False)
    )
    require_four_eyes_approval: bool = field(
        default_factory=lambda: _env_bool("REQUIRE_FOUR_EYES_APPROVAL", True)
    )
    allow_http_emulation_sinks: bool = field(
        default_factory=lambda: _env_bool("ALLOW_HTTP_EMULATION_SINKS", False)
    )
    allowed_registry_prefixes: list[str] = field(
        default_factory=lambda: _env_csv(
            "ALLOWED_REGISTRY_PREFIXES",
            "harbor.gdc.local/,harbor.infra.gdc.local/",
        )
    )
    worker_image_tag: str = field(default_factory=lambda: os.getenv("WORKER_IMAGE_TAG", "v1.0.0"))
    approved_templates: list[str] = field(
        default_factory=lambda: _env_csv(
            "APPROVED_TEMPLATES",
            "gdc-standard-job-runner-v1",
        )
    )
    allowed_notification_hosts: list[str] = field(
        default_factory=lambda: _env_csv(
            "ALLOWED_NOTIFICATION_HOSTS",
            "webhooks.gdc.local,smtp.gdc.local,chat.gdc.local,itsm.gdc.local",
        )
    )
    cors_allowed_origins: list[str] = field(
        default_factory=lambda: _env_csv(
            "CORS_ALLOWED_ORIGINS",
            "https://jobs.gdc.local,https://admin.jobs.gdc.local",
        )
    )
    oidc_issuer: str = field(
        default_factory=lambda: os.getenv(
            "OIDC_ISSUER", "https://keycloak.gdc.local/realms/gdc-jobs-realm"
        )
    )
    oidc_jwks_url: str = field(
        default_factory=lambda: os.getenv(
            "OIDC_JWKS_URL",
            "http://keycloak.p12-keycloak.svc.cluster.local:80/realms/gdc-jobs-realm/protocol/openid-connect/certs",
        )
    )
    oidc_client_id: str = field(
        default_factory=lambda: os.getenv("OIDC_CLIENT_ID", "p15-job-portal")
    )
    oidc_admin_client_id: str = field(
        default_factory=lambda: os.getenv("OIDC_ADMIN_CLIENT_ID", "p15-job-admin")
    )
    user_cookie_secret: str = field(
        default_factory=lambda: os.getenv("USER_COOKIE_SECRET") or secrets.token_hex(32)
    )
    admin_cookie_secret: str = field(
        default_factory=lambda: os.getenv("ADMIN_COOKIE_SECRET") or secrets.token_hex(32)
    )
    cookie_secure: bool = field(default_factory=lambda: _env_bool("COOKIE_SECURE", True))

    # Resource & Noisy-Neighbour Guardrails (REQ-REL-004)
    max_shards_per_run: int = field(
        default_factory=lambda: int(os.getenv("MAX_SHARDS_PER_RUN", "50"))
    )
    min_ao_cron_interval_minutes: int = field(
        default_factory=lambda: int(os.getenv("MIN_AO_CRON_INTERVAL_MINUTES", "5"))
    )
    max_batch_deadline_seconds: int = field(
        default_factory=lambda: int(os.getenv("MAX_BATCH_DEADLINE_SECONDS", "14400"))
    )
    max_monitor_deadline_seconds: int = field(
        default_factory=lambda: int(os.getenv("MAX_MONITOR_DEADLINE_SECONDS", "900"))
    )

    # Layer 1 & Layer 2 Self-Healing Defaults (REQ-HEAL-001..004)
    default_max_actions_per_run: int = field(
        default_factory=lambda: int(os.getenv("DEFAULT_MAX_ACTIONS_PER_RUN", "5"))
    )
    default_cooldown_seconds: int = field(
        default_factory=lambda: int(os.getenv("DEFAULT_COOLDOWN_SECONDS", "3600"))
    )
    consecutive_failure_threshold: int = field(
        default_factory=lambda: int(os.getenv("CONSECUTIVE_FAILURE_THRESHOLD", "5"))
    )
    approval_ttl_seconds: int = field(
        default_factory=lambda: int(os.getenv("APPROVAL_TTL_SECONDS", "86400"))
    )

    # Notification Deduplication, Rate Limiting & Quiet Hours (REQ-NOTIF-003)
    dedup_window_seconds: int = field(
        default_factory=lambda: int(os.getenv("DEDUP_WINDOW_SECONDS", "900"))
    )
    sink_rate_limit_per_minute: int = field(
        default_factory=lambda: int(os.getenv("SINK_RATE_LIMIT_PER_MINUTE", "30"))
    )
    quiet_hours_utc: str = field(default_factory=lambda: os.getenv("QUIET_HOURS_UTC", ""))

    # Database & Storage Settings
    db_dsn: str = field(default_factory=lambda: os.getenv("DB_DSN", ""))
    db_host: str = field(default_factory=lambda: os.getenv("DB_HOST", ""))
    db_port: int = field(default_factory=lambda: int(os.getenv("DB_PORT", "5432")))
    db_name: str = field(default_factory=lambda: os.getenv("DB_NAME", "postgres"))
    db_user: str = field(default_factory=lambda: os.getenv("DB_USER", "postgres"))
    db_password: str = field(default_factory=lambda: os.getenv("DB_PASSWORD", ""))
    db_sslrootcert: str = field(default_factory=lambda: os.getenv("DB_SSLROOTCERT", ""))
    sqlite_path: str = field(default_factory=lambda: os.getenv("P15_SQLITE_PATH", ":memory:"))

    bucket_name: str = field(
        default_factory=lambda: os.getenv("BUCKET_NAME", "p15-jobs-ledger")
    )
    s3_endpoint: str = field(default_factory=lambda: os.getenv("S3_ENDPOINT", ""))
    ca_bundle_path: str = field(
        default_factory=lambda: os.getenv("GDC_CA_BUNDLE", "/etc/gdc-certs/ca.crt")
    )

    def __post_init__(self) -> None:
        if self.engine_mode not in ("argo", "k8s-native"):
            raise ValueError(f"Unsupported ENGINE_MODE: {self.engine_mode!r}")
        if self.gitops_mode not in ("direct-apply", "gitops-mr"):
            raise ValueError(f"Unsupported GITOPS_MODE: {self.gitops_mode!r}")
        if self.user_cookie_secret == self.admin_cookie_secret:
            # Guarantee cryptographic isolation between :8080 and :8081 cookies (REQ-UX-002)
            self.admin_cookie_secret = f"admin-{self.admin_cookie_secret}"
