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
"""Pre-archive secret redaction, safe subprocess env scrubbing, and object key validation."""

from __future__ import annotations

import os
import re
from typing import Any

_OBJECT_KEY_RE = re.compile(r"^[a-zA-Z0-9._-]+(?:/[a-zA-Z0-9._-]+)*$")

_PEM_RE = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z0-9 ]*PRIVATE KEY-----",
    re.MULTILINE,
)
_AUTH_SCHEME_RE = re.compile(r"\b(Bearer|Basic)\s+[A-Za-z0-9._~+/=-]{8,}", re.IGNORECASE)
_KV_SECRET_RE = re.compile(
    r"(?i)\b(password|passwd|secret|client_secret|api_key|apikey|access_token|refresh_token|"
    r"aws_secret_access_key|secret_access_key|smtp_password|hmac_secret)\s*([:=])\s*([^\s,\"'&]+)"
)
_JSON_SECRET_KEY_RE = re.compile(
    r"(?i)(password|passwd|secret|token|api_key|apikey|private_key|cookie_secret)"
)
_AWS_KEY_ID_RE = re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b")

_SAFE_ENV_ALLOWLIST = {
    "PATH",
    "HOME",
    "LANG",
    "LC_ALL",
    "TZ",
    "PYTHONPATH",
    "PYTHONUNBUFFERED",
    "AWS_CA_BUNDLE",
    "REQUESTS_CA_BUNDLE",
    "SSL_CERT_FILE",
    "S3_ENDPOINT",
    "S3_REGION",
    "BUCKET_NAME",
    "PROJECT_ID",
    "NAMESPACE",
}


def redact_secrets(text: str) -> str:
    """Scrub credentials, bearer tokens, and private keys prior to 400-day Bucket archival."""
    if not text:
        return text
    scrubbed = _PEM_RE.sub("[REDACTED_PRIVATE_KEY]", text)
    scrubbed = _AUTH_SCHEME_RE.sub(r"\1 [REDACTED_TOKEN]", scrubbed)
    scrubbed = _KV_SECRET_RE.sub(r"\1\2[REDACTED_SECRET]", scrubbed)
    scrubbed = _AWS_KEY_ID_RE.sub("[REDACTED_ACCESS_KEY_ID]", scrubbed)
    return scrubbed


def redact_payload(value: Any) -> Any:
    """Recursively scrub sensitive dictionary keys and string values in structured JSON payloads."""
    if isinstance(value, str):
        return redact_secrets(value)
    if isinstance(value, list):
        return [redact_payload(item) for item in value]
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            if _JSON_SECRET_KEY_RE.search(str(k)):
                out[k] = "[REDACTED_SECRET]"
            else:
                out[k] = redact_payload(v)
        return out
    return value


def validate_object_key(object_key: str) -> str:
    """Validate canonical object storage keys and reject path traversal ('..') or absolute paths."""
    if not object_key or not isinstance(object_key, str):
        raise ValueError("Object key must be a non-empty string")
    cleaned = object_key.strip()
    if "\x00" in cleaned or cleaned.startswith("/") or cleaned.endswith("/"):
        raise ValueError(f"Invalid object key boundary: {object_key!r}")
    segments = cleaned.split("/")
    for seg in segments:
        if seg in ("", ".", "..") or ".." in seg:
            raise ValueError(f"Path traversal rejected in object key: {object_key!r}")
    if not _OBJECT_KEY_RE.match(cleaned):
        raise ValueError(f"Object key contains disallowed characters: {object_key!r}")
    return cleaned


def build_safe_subprocess_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Build a minimal, secret-scrubbed environment dictionary for child worker processes."""
    safe_env = {k: v for k, v in os.environ.items() if k in _SAFE_ENV_ALLOWLIST}
    if extra:
        for k, v in extra.items():
            if not _JSON_SECRET_KEY_RE.search(k):
                safe_env[k] = str(v)
    return safe_env
