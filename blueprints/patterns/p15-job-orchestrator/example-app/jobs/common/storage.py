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
"""Dual-Mode Object Storage Adapter (GCS Workload Identity on GKE <-> boto3 S3 v4 on GDC-ag)."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any

from .redaction import redact_payload, redact_secrets, validate_object_key


def _strip_bucket_scheme(raw_bucket: str) -> str:
    val = (raw_bucket or "").strip()
    for prefix in ("s3://", "gs://", "file://"):
        if val.startswith(prefix):
            val = val[len(prefix) :]
    val = val.strip("/")
    return val.split("/", 1)[0] if "/" in val else val


def build_job_artifact_key(
    namespace: str,
    job_id: str,
    run_id: str,
    filename: str,
    ts: datetime | None = None,
) -> str:
    """Build a canonical retention-locked object storage key (`jobs/{ns}/{job}/{YYYY}/{MM}/{run}/{file}`)."""
    when = (ts or datetime.now(timezone.utc)).astimezone(timezone.utc)
    key = f"jobs/{namespace}/{job_id}/{when:%Y}/{when:%m}/{run_id}/{filename}"
    return validate_object_key(key)


class DualModeStorageAdapter:
    """Switches transparently between native Google Cloud Storage and GDC-ag S3 Object Storage.

    - When `s3_endpoint` (`S3_ENDPOINT`) is empty (`""`): uses `google.cloud.storage.Client()`
      authenticated via GKE Workload Identity against `gs://<bucket>`.
    - When `s3_endpoint` is set (e.g. `https://objectstorage.gdc.goog` on GDC-ag): uses
      `boto3.client("s3")` (`signature_version="s3v4"`) verifying internal PKI via `AWS_CA_BUNDLE`.
    - Supports `local_dir` strictly for hermetic unit/offline testing when neither cloud endpoint
      is configured in local test harnesses.
    """

    def __init__(
        self,
        bucket_name: str | None = None,
        s3_endpoint: str | None = None,
        s3_region: str | None = None,
        ca_bundle: str | bool | None = None,
        local_dir: str | Path | None = None,
        s3_client: Any = None,
        gcs_client: Any = None,
    ) -> None:
        raw_bucket = bucket_name if bucket_name is not None else os.getenv("BUCKET_NAME", "p15-jobs-ledger")
        self.bucket_name = _strip_bucket_scheme(raw_bucket) or "p15-jobs-ledger"
        self.s3_endpoint = (
            s3_endpoint if s3_endpoint is not None else os.getenv("S3_ENDPOINT", "")
        ).strip()
        self.s3_region = (
            s3_region if s3_region is not None else os.getenv("S3_REGION", "zone1")
        ).strip()
        resolved_ca = (
            ca_bundle
            if ca_bundle is not None
            else (os.getenv("AWS_CA_BUNDLE") or os.getenv("REQUESTS_CA_BUNDLE") or True)
        )
        self.ca_bundle: str | bool = resolved_ca

        env_local = os.getenv("P15_LOCAL_OBJECT_STORE", "").strip()
        self.local_dir: Path | None = (
            Path(local_dir) if local_dir is not None else (Path(env_local) if env_local else None)
        )
        self._s3_client = s3_client
        self._gcs_client = gcs_client

        if self.local_dir is not None:
            self.mode = "local-fs"
            self.local_dir.mkdir(parents=True, exist_ok=True)
        elif self.s3_endpoint:
            self.mode = "gdc-s3"
            if self._s3_client is None:
                import boto3  # type: ignore
                from botocore.config import Config  # type: ignore

                self._s3_client = boto3.client(
                    "s3",
                    endpoint_url=self.s3_endpoint,
                    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID") or None,
                    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY") or None,
                    config=Config(signature_version="s3v4", connect_timeout=5, read_timeout=10),
                    region_name=self.s3_region,
                    verify=self.ca_bundle,
                )
        else:
            self.mode = "gcp-gcs"
            if self._gcs_client is None:
                from google.cloud import storage as gcs_storage  # type: ignore

                self._gcs_client = gcs_storage.Client()

    @property
    def uri_scheme(self) -> str:
        if self.mode == "gdc-s3":
            return "s3"
        if self.mode == "gcp-gcs":
            return "gs"
        return "memstore"

    def format_uri(self, object_key: str) -> str:
        safe_key = validate_object_key(object_key)
        return f"{self.uri_scheme}://{self.bucket_name}/{safe_key}"

    def put_bytes(
        self,
        object_key: str,
        content: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        safe_key = validate_object_key(object_key)
        if self.mode == "local-fs" and self.local_dir is not None:
            dest = (self.local_dir / safe_key).resolve()
            root = self.local_dir.resolve()
            if root not in dest.parents and dest != root:
                raise ValueError("Path escaped local storage root")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(content)
            return self.format_uri(safe_key)

        if self.mode == "gdc-s3":
            self._s3_client.put_object(
                Bucket=self.bucket_name,
                Key=safe_key,
                Body=content,
                ContentType=content_type,
            )
            return self.format_uri(safe_key)

        bucket = self._gcs_client.bucket(self.bucket_name)
        blob = bucket.blob(safe_key)
        blob.upload_from_string(content, content_type=content_type, timeout=10)
        return self.format_uri(safe_key)

    def put_text(
        self,
        object_key: str,
        text: str,
        content_type: str = "text/plain; charset=utf-8",
        redact: bool = True,
    ) -> str:
        payload_str = redact_secrets(text) if redact else text
        return self.put_bytes(object_key, payload_str.encode("utf-8"), content_type=content_type)

    def put_json(self, object_key: str, data: Any, redact: bool = True) -> str:
        cleaned = redact_payload(data) if redact else data
        encoded = json.dumps(cleaned, sort_keys=True, indent=2).encode("utf-8")
        return self.put_bytes(object_key, encoded, content_type="application/json")

    def get_bytes(self, object_key: str) -> bytes:
        safe_key = validate_object_key(object_key)
        if self.mode == "local-fs" and self.local_dir is not None:
            dest = (self.local_dir / safe_key).resolve()
            root = self.local_dir.resolve()
            if root not in dest.parents and dest != root:
                raise ValueError("Path escaped local storage root")
            if not dest.exists():
                raise FileNotFoundError(safe_key)
            return dest.read_bytes()

        if self.mode == "gdc-s3":
            resp = self._s3_client.get_object(Bucket=self.bucket_name, Key=safe_key)
            body = resp["Body"]
            return body.read() if hasattr(body, "read") else bytes(body)

        bucket = self._gcs_client.bucket(self.bucket_name)
        blob = bucket.blob(safe_key)
        return blob.download_as_bytes(timeout=10)

    def get_text(self, object_key: str) -> str:
        return self.get_bytes(object_key).decode("utf-8", errors="replace")

    def get_json(self, object_key: str) -> Any:
        return json.loads(self.get_text(object_key))

    def list_keys(self, prefix: str) -> list[str]:
        safe_prefix = validate_object_key(prefix.strip("/")) if prefix.strip("/") else ""
        if self.mode == "local-fs" and self.local_dir is not None:
            root = self.local_dir.resolve()
            target = (root / safe_prefix).resolve() if safe_prefix else root
            if not target.exists():
                return []
            if target.is_file():
                return [str(target.relative_to(root))]
            return sorted(
                str(p.relative_to(root)) for p in target.rglob("*") if p.is_file()
            )

        if self.mode == "gdc-s3":
            resp = self._s3_client.list_objects_v2(Bucket=self.bucket_name, Prefix=safe_prefix)
            return sorted(item["Key"] for item in resp.get("Contents", []))

        blobs = self._gcs_client.list_blobs(self.bucket_name, prefix=safe_prefix)
        return sorted(b.name for b in blobs)
