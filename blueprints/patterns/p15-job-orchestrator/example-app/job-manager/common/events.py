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
"""Phase 2 Event-Driven Extension Seam (`REQ-ENG-004`: ObjectStorageWALSink & KafkaSink)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
import json
from typing import Any, Callable

from .redaction import redact_payload, validate_object_key
from .storage import DualModeStorageAdapter


class EventSink(ABC):
    """Pluggable event publication seam decoupling job producers from downstream buses."""

    @abstractmethod
    def publish(self, topic: str, event_key: str, payload: dict[str, Any]) -> str:
        """Publish a canonical event and return its durable receipt URI."""

    @abstractmethod
    def health_check(self) -> dict[str, Any]:
        """Return sink health metadata."""


class TriggerAdapter(ABC):
    """Pluggable inbound trigger adapter seam (cron/webhook in Phase 1; Argo Events/Kafka in Phase 2)."""

    @abstractmethod
    def poll_events(self, limit: int = 50) -> list[dict[str, Any]]:
        """Poll pending trigger events."""


class ObjectStorageWALSink(EventSink):
    """Phase 1 default sink persisting redacted WAL event bundles to GDC S3 / GKE GCS."""

    def __init__(self, storage: DualModeStorageAdapter, prefix: str = "wal/events") -> None:
        self.storage = storage
        self.prefix = validate_object_key(prefix)

    def publish(self, topic: str, event_key: str, payload: dict[str, Any]) -> str:
        now = datetime.now(timezone.utc)
        safe_topic = validate_object_key(topic)
        safe_key = validate_object_key(event_key)
        obj_key = f"{self.prefix}/{safe_topic}/{now:%Y/%m/%d}/{safe_key}.json"
        envelope = {
            "topic": safe_topic,
            "event_key": safe_key,
            "published_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "payload": redact_payload(payload),
        }
        return self.storage.put_json(obj_key, envelope, redact=True)

    def health_check(self) -> dict[str, Any]:
        return {"sink": "ObjectStorageWALSink", "mode": self.storage.mode, "healthy": True}


class KafkaSink(EventSink):
    """Phase 2 `p4-event-driven-kafka` (KRaft HA) sink adapter (disabled by default in Phase 1)."""

    def __init__(
        self,
        bootstrap_servers: str = "kafka-headless.platform-events.svc.cluster.local:9092",
        enabled: bool = False,
        producer_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.bootstrap_servers = bootstrap_servers
        self.enabled = enabled
        self._producer_factory = producer_factory
        self._producer: Any = None

    def _ensure_producer(self) -> Any:
        if not self.enabled:
            raise RuntimeError("KafkaSink is disabled (set events.kafka.enabled=true to activate)")
        if self._producer is None:
            if self._producer_factory is not None:
                self._producer = self._producer_factory()
            else:
                from kafka import KafkaProducer  # type: ignore

                self._producer = KafkaProducer(
                    bootstrap_servers=self.bootstrap_servers.split(","),
                    value_serializer=lambda v: json.dumps(v, sort_keys=True).encode("utf-8"),
                    key_serializer=lambda k: k.encode("utf-8"),
                )
        return self._producer

    def publish(self, topic: str, event_key: str, payload: dict[str, Any]) -> str:
        safe_topic = validate_object_key(topic)
        safe_key = validate_object_key(event_key)
        producer = self._ensure_producer()
        sanitized = redact_payload(payload)
        future = producer.send(safe_topic, key=safe_key, value=sanitized)
        if hasattr(future, "get"):
            future.get(timeout=5)
        return f"kafka://{self.bootstrap_servers}/{safe_topic}/{safe_key}"

    def health_check(self) -> dict[str, Any]:
        return {
            "sink": "KafkaSink",
            "enabled": self.enabled,
            "bootstrap_servers": self.bootstrap_servers,
            "healthy": bool(self.enabled),
        }
