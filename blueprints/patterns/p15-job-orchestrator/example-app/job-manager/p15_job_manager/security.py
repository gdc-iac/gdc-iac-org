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
"""Identity (Keycloak OIDC RS256 + PKCE), Dual-Port Cookie/CSRF, Template Allowlist & SSRF Guard."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
import hashlib
import hmac
import ipaddress
import json
import re
import secrets
import socket
import time
from typing import Any, Callable
from urllib.parse import urlparse

import jwt

from .config import ControlPlaneConfig


class AuthenticationError(Exception):
    """Raised when a caller is unauthenticated (`401`)."""


class AuthorizationError(Exception):
    """Raised when an authenticated caller lacks persona/namespace permission (`403`)."""


class SecurityValidationError(ValueError):
    """Raised when an input fails SSRF, CSRF, template, or image allowlist checks (`400`)."""


FORBIDDEN_POD_SPEC_KEYS = frozenset(
    {
        "podSpec",
        "podspec",
        "command",
        "args",
        "volumes",
        "volumeMounts",
        "hostNetwork",
        "hostPID",
        "hostIPC",
        "securityContext",
        "serviceAccountName",
        "containers",
        "initContainers",
        "ephemeralContainers",
        "privileged",
    }
)

BLOCKED_HOSTNAMES = frozenset(
    {
        "localhost",
        "metadata.google.internal",
        "metadata",
        "kubernetes",
        "kubernetes.default",
        "kubernetes.default.svc",
        "kubernetes.default.svc.cluster.local",
    }
)

_IMAGE_TAG_OR_DIGEST_RE = re.compile(
    r"^[a-z0-9._-]+(?::[0-9]+)?/[a-z0-9._/-]+(?::(?!latest$)[A-Za-z0-9._-]+|@sha256:[0-9a-f]{64})$"
)


@dataclass(frozen=True)
class AuthPrincipal:
    """Verified OIDC caller identity and authorised namespace boundaries."""

    subject: str
    email: str
    persona: str  # "PA" or "AO"
    roles: tuple[str, ...] = field(default_factory=tuple)
    allowed_namespaces: tuple[str, ...] = field(default_factory=tuple)
    can_mutate: bool = True

    @property
    def is_pa_admin(self) -> bool:
        return self.persona == "PA" and "pa-job-admin" in self.roles

    def check_namespace_access(self, namespace: str, require_write: bool = False) -> None:
        if require_write and not self.can_mutate:
            raise AuthorizationError(f"Principal '{self.subject}' has viewer-only access")
        if self.is_pa_admin:
            return
        if "*" not in self.allowed_namespaces and namespace not in self.allowed_namespaces:
            raise AuthorizationError(
                f"Principal '{self.subject}' is not authorised for namespace '{namespace}'"
            )


def generate_pkce_pair() -> tuple[str, str]:
    """Generate RFC 7636 PKCE `S256` `(code_verifier, code_challenge)`."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode("ascii")
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def derive_principal_from_claims(claims: dict[str, Any], default_namespace: str) -> AuthPrincipal:
    """Map Keycloak OIDC JWT claims (`roles`, `realm_access.roles`, `groups`) to `AuthPrincipal`."""
    subject = str(claims.get("preferred_username") or claims.get("sub") or "").strip()
    if not subject:
        raise AuthenticationError("OIDC token missing 'sub' / 'preferred_username'")
    email = str(claims.get("email") or f"{subject}@gdc.local").strip()

    raw_roles: list[str] = []
    for src in (
        claims.get("roles"),
        (claims.get("realm_access") or {}).get("roles")
        if isinstance(claims.get("realm_access"), dict)
        else None,
        claims.get("groups"),
    ):
        if isinstance(src, list):
            raw_roles.extend(str(r).lstrip("/") for r in src)

    roles = tuple(sorted(set(raw_roles)))
    if "pa-job-admin" in roles:
        return AuthPrincipal(
            subject=subject,
            email=email,
            persona="PA",
            roles=roles,
            allowed_namespaces=("*",),
            can_mutate=True,
        )

    operator_ns: list[str] = []
    viewer_ns: list[str] = []
    for r in roles:
        if r.startswith("ao-job-operator-"):
            ns = r[len("ao-job-operator-") :].strip()
            if ns:
                operator_ns.append(ns)
        elif r.startswith("job-viewer-"):
            ns = r[len("job-viewer-") :].strip()
            if ns:
                viewer_ns.append(ns)
        elif r == "ao-job-operator":
            operator_ns.append(default_namespace)
        elif r == "job-viewer":
            viewer_ns.append(default_namespace)

    allowed = tuple(sorted(set(operator_ns + viewer_ns)))
    if not allowed:
        raise AuthorizationError(f"Principal '{subject}' has no assigned GDC job roles")
    return AuthPrincipal(
        subject=subject,
        email=email,
        persona="AO",
        roles=roles,
        allowed_namespaces=allowed,
        can_mutate=bool(operator_ns),
    )


class OIDCAuthenticator:
    """Verifies RS256 Keycloak JWTs via JWKS and issues dual-port HMAC-SHA256 session cookies."""

    USER_COOKIE_NAME = "jobs_user_session"
    ADMIN_COOKIE_NAME = "jobs_admin_session"

    def __init__(
        self,
        config: ControlPlaneConfig,
        jwks_provider: Callable[[], dict[str, Any]] | None = None,
        public_key_pem: str | bytes | None = None,
    ) -> None:
        self.config = config
        self._jwks_provider = jwks_provider
        self._public_key_pem = public_key_pem
        self._cached_jwks: tuple[float, jwt.PyJWKSet] | None = None

    def _resolve_signing_key(self, token: str) -> Any:
        if self._public_key_pem is not None:
            return self._public_key_pem
        now = time.time()
        if self._cached_jwks is None or (now - self._cached_jwks[0]) > 300:
            if self._jwks_provider is not None:
                jwks_dict = self._jwks_provider()
            else:
                import httpx

                ca: str | bool = (
                    self.config.ca_bundle_path
                    if self.config.ca_bundle_path and __import__("os").path.exists(self.config.ca_bundle_path)
                    else True
                )
                with httpx.Client(timeout=5.0, follow_redirects=False, trust_env=False, verify=ca) as client:
                    resp = client.get(self.config.oidc_jwks_url)
                    resp.raise_for_status()
                    jwks_dict = resp.json()
            self._cached_jwks = (now, jwt.PyJWKSet.from_dict(jwks_dict))

        header = jwt.get_unverified_header(token)
        if header.get("alg") != "RS256":
            raise AuthenticationError(f"Disallowed JWT signing algorithm: {header.get('alg')!r}")
        kid = header.get("kid")
        jwk_set = self._cached_jwks[1]
        for jwk_key in jwk_set.keys:
            if kid is None or jwk_key.key_id == kid:
                return jwk_key.key
        raise AuthenticationError(f"Unknown JWKS key ID: {kid!r}")

    def verify_bearer_token(self, token: str, require_admin_surface: bool = False) -> AuthPrincipal:
        try:
            key = self._resolve_signing_key(token)
            claims = jwt.decode(
                token,
                key=key,
                algorithms=["RS256"],
                issuer=self.config.oidc_issuer,
                options={"verify_aud": False},
                leeway=60,
            )
        except AuthenticationError:
            raise
        except Exception as exc:
            raise AuthenticationError("Invalid or expired OIDC JWT") from exc

        principal = derive_principal_from_claims(claims, self.config.namespace)
        if require_admin_surface and not principal.is_pa_admin:
            raise AuthorizationError("Port 8081 PA Admin Console requires role 'pa-job-admin'")
        return principal

    def issue_session_cookie(
        self, principal: AuthPrincipal, admin_surface: bool = False, ttl_seconds: int = 28800
    ) -> tuple[str, str, str]:
        """Return `(cookie_name, signed_cookie_value, csrf_token)`."""
        if admin_surface and not principal.is_pa_admin:
            raise AuthorizationError("Cannot mint Port 8081 admin session for non-PA principal")
        secret = (
            self.config.admin_cookie_secret if admin_surface else self.config.user_cookie_secret
        )
        cookie_name = self.ADMIN_COOKIE_NAME if admin_surface else self.USER_COOKIE_NAME
        csrf_nonce = secrets.token_hex(16)
        payload = {
            "sub": principal.subject,
            "email": principal.email,
            "persona": principal.persona,
            "roles": list(principal.roles),
            "ns": list(principal.allowed_namespaces),
            "mut": principal.can_mutate,
            "surface": "admin" if admin_surface else "portal",
            "csrf": csrf_nonce,
            "exp": int(time.time()) + ttl_seconds,
        }
        raw_b64 = (
            base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
            .rstrip(b"=")
            .decode("ascii")
        )
        sig = hmac.new(secret.encode("utf-8"), raw_b64.encode("ascii"), hashlib.sha256).hexdigest()
        csrf_token = hmac.new(
            secret.encode("utf-8"), f"csrf:{csrf_nonce}:{principal.subject}".encode("utf-8"), hashlib.sha256
        ).hexdigest()
        return cookie_name, f"{raw_b64}.{sig}", csrf_token

    def verify_session_cookie(
        self,
        cookie_value: str,
        admin_surface: bool = False,
        csrf_header: str | None = None,
        require_csrf: bool = False,
    ) -> AuthPrincipal:
        if not cookie_value or "." not in cookie_value:
            raise AuthenticationError("Missing or malformed session cookie")
        raw_b64, got_sig = cookie_value.rsplit(".", 1)
        secret = (
            self.config.admin_cookie_secret if admin_surface else self.config.user_cookie_secret
        )
        exp_sig = hmac.new(
            secret.encode("utf-8"), raw_b64.encode("ascii"), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(got_sig, exp_sig):
            raise AuthenticationError("Session cookie HMAC verification failed")

        pad = "=" * (-len(raw_b64) % 4)
        try:
            payload = json.loads(base64.urlsafe_b64decode(raw_b64 + pad).decode("utf-8"))
        except Exception as exc:
            raise AuthenticationError("Corrupted session payload") from exc

        if int(payload.get("exp", 0)) < int(time.time()):
            raise AuthenticationError("Session cookie expired")
        expected_surface = "admin" if admin_surface else "portal"
        if payload.get("surface") != expected_surface:
            raise AuthenticationError("Cross-port session surface mismatch")

        principal = AuthPrincipal(
            subject=payload["sub"],
            email=payload["email"],
            persona=payload["persona"],
            roles=tuple(payload.get("roles", [])),
            allowed_namespaces=tuple(payload.get("ns", [])),
            can_mutate=bool(payload.get("mut", True)),
        )
        if admin_surface and not principal.is_pa_admin:
            raise AuthorizationError("Port 8081 PA Admin Console requires role 'pa-job-admin'")

        if require_csrf:
            expected_csrf = hmac.new(
                secret.encode("utf-8"),
                f"csrf:{payload.get('csrf', '')}:{principal.subject}".encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            if not csrf_header or not hmac.compare_digest(csrf_header, expected_csrf):
                raise SecurityValidationError("CSRF token missing or invalid")

        return principal

    def format_set_cookie_header(self, cookie_name: str, cookie_value: str, max_age: int = 28800) -> str:
        attrs = [
            f"{cookie_name}={cookie_value}",
            "Path=/",
            f"Max-Age={max_age}",
            "HttpOnly",
            "SameSite=Lax",
        ]
        if self.config.cookie_secure:
            attrs.append("Secure")
        return "; ".join(attrs)


def validate_job_security_spec(
    payload: dict[str, Any],
    approved_templates: Iterable[str],
    allowed_registry_prefixes: Iterable[str],
) -> None:
    """Enforce `REQ-SEC-005`: ban raw PodSpec overrides & enforce Harbor registry + pinned tags."""

    def _scan_forbidden_keys(node: Any) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                if str(k) in FORBIDDEN_POD_SPEC_KEYS:
                    raise SecurityValidationError(
                        f"Raw Kubernetes PodSpec field '{k}' is forbidden on the API; "
                        "jobs must bind to an approved template and typed parameters."
                    )
                _scan_forbidden_keys(v)
        elif isinstance(node, list):
            for item in node:
                _scan_forbidden_keys(item)

    _scan_forbidden_keys(payload)

    template_name = str(payload.get("template_name") or "gdc-standard-job-runner-v1").strip()
    if template_name not in set(approved_templates):
        raise SecurityValidationError(
            f"Unapproved job template {template_name!r}; allowed templates: {sorted(approved_templates)}"
        )

    worker_image = str(payload.get("worker_image") or "").strip()
    if not worker_image:
        raise SecurityValidationError("worker_image is required")
    if worker_image.endswith(":latest") or (":" not in worker_image.split("/")[-1] and "@sha256:" not in worker_image):
        raise SecurityValidationError(
            f"worker_image {worker_image!r} must specify an immutable pinned tag or @sha256 digest (':latest' is prohibited)"
        )
    if not _IMAGE_TAG_OR_DIGEST_RE.match(worker_image):
        raise SecurityValidationError(f"Invalid container image reference syntax: {worker_image!r}")

    prefixes = [p for p in allowed_registry_prefixes if p]
    if not any(worker_image.startswith(prefix) for prefix in prefixes):
        raise SecurityValidationError(
            f"worker_image {worker_image!r} is not from an allowlisted GDC Harbor registry ({prefixes})"
        )


def validate_notification_target(
    target_url: str,
    allowed_hosts: Iterable[str],
    sink_type: str = "generic-webhook",
    allow_http_emulation: bool = False,
    resolver: Callable[..., Any] | None = None,
) -> str:
    """Enforce `REQ-SEC-006`: SSRF validation, DNS rebinding protection & PA host allowlist."""
    if sink_type == "portal-feed":
        return "internal://portal-feed"
    if not target_url or not isinstance(target_url, str):
        raise SecurityValidationError("Notification target URL is required")

    parsed = urlparse(target_url.strip())
    if parsed.username or parsed.password:
        raise SecurityValidationError("Credentials embedded in notification URLs are forbidden; use Secret refs")

    if sink_type == "smtp-relay":
        allowed_schemes = {"smtps", "smtp"} if allow_http_emulation else {"smtps", "smtp"}
    else:
        allowed_schemes = {"https", "http"} if allow_http_emulation else {"https"}

    if parsed.scheme.lower() not in allowed_schemes:
        raise SecurityValidationError(
            f"Disallowed URL scheme {parsed.scheme!r} for sink type {sink_type!r} (expected {sorted(allowed_schemes)})"
        )

    hostname = (parsed.hostname or "").strip().lower().rstrip(".")
    if not hostname:
        raise SecurityValidationError("Notification URL missing hostname")
    if hostname in BLOCKED_HOSTNAMES or hostname.endswith(".internal"):
        raise SecurityValidationError(f"Blocked internal/metadata hostname: {hostname!r}")

    # Check literal IP before DNS resolution
    try:
        literal_ip = ipaddress.ip_address(hostname)
        _reject_unsafe_ip(literal_ip, hostname)
    except ValueError:
        pass

    normalized_allowlist = {h.strip().lower().rstrip(".") for h in allowed_hosts if h.strip()}
    if not _host_matches_allowlist(hostname, normalized_allowlist):
        raise SecurityValidationError(
            f"Destination host {hostname!r} is not in PA-governed ALLOWED_NOTIFICATION_HOSTS"
        )

    # Pre-connect DNS resolution check to prevent DNS rebinding to loopback / 169.254.169.254
    res_fn = resolver or socket.getaddrinfo
    port = parsed.port or (587 if sink_type == "smtp-relay" else (443 if parsed.scheme == "https" else 80))
    try:
        infos = res_fn(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise SecurityValidationError(f"DNS resolution failed for {hostname!r}: {exc}") from exc

    for info in infos:
        sockaddr = info[4]
        ip_obj = ipaddress.ip_address(sockaddr[0])
        _reject_unsafe_ip(ip_obj, hostname)

    return target_url.strip()


def _host_matches_allowlist(hostname: str, allowlist: set[str]) -> bool:
    if hostname in allowlist:
        return True
    for pattern in allowlist:
        if pattern.startswith("*.") and hostname.endswith(pattern[1:]):
            return True
    return False


def _reject_unsafe_ip(ip_obj: ipaddress.IPv4Address | ipaddress.IPv6Address, host: str) -> None:
    if (
        ip_obj.is_loopback
        or ip_obj.is_link_local
        or ip_obj.is_multicast
        or ip_obj.is_unspecified
        or str(ip_obj).startswith("169.254.")
    ):
        raise SecurityValidationError(
            f"SSRF blocked: {host!r} resolved to restricted loopback/link-local/metadata address {ip_obj}"
        )
