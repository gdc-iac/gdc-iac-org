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
"""Starter Worker 1: `batch-watermarked-rollup` (Idempotent WAL-First Windowed Aggregation)."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys
from typing import Any, Callable

_COMMON_PARENT = str(Path(__file__).resolve().parents[2])
if _COMMON_PARENT not in sys.path:
    sys.path.insert(0, _COMMON_PARENT)

from common.storage import DualModeStorageAdapter  # noqa: E402


def _window_slug(window_start: str, window_end: str) -> str:
    digest = hashlib.sha256(f"{window_start}..{window_end}".encode("utf-8")).hexdigest()[:16]
    safe_end = window_end.replace(":", "").replace("-", "")
    return f"{safe_end}-{digest}"


def execute_batch_watermarked_rollup(
    job_id: str,
    run_id: str,
    window_start: str,
    window_end: str,
    shard_key: str,
    storage: DualModeStorageAdapter,
    records: list[dict[str, Any]] | None = None,
    db_sink: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Aggregate resource metadata/usage over `[window_start, window_end)` with WAL failover safety.

    1. Writes immutable WAL bundle to Object Storage (`s3://` on GDC-ag, `gs://` on GKE) FIRST.
    2. Attempts to replay all unindexed WAL bundles for `(job_id, shard_key)` into PostgreSQL;
       if PostgreSQL is undergoing failover/maintenance, logs a non-fatal drain deferral so zero
       collection windows are lost (`REQ-HEAL-002`).
    """
    sample_records = records if records is not None else [
        {"resource_id": f"{shard_key}-pod-01", "labels": {"env": "prod", "tier": "core"}, "units": 12.5},
        {"resource_id": f"{shard_key}-pod-02", "labels": {"env": "prod", "tier": "batch"}, "units": 7.5},
    ]

    total_units = round(sum(float(r.get("units", 0.0)) for r in sample_records), 4)
    slug = _window_slug(window_start, window_end)
    wal_key = f"wal/rollups/{job_id}/{shard_key}/{slug}.json"
    wal_doc = {
        "idempotency_key": f"{job_id}:{shard_key}:{window_start}:{window_end}",
        "job_id": job_id,
        "run_id": run_id,
        "shard_key": shard_key,
        "window_start": window_start,
        "window_end": window_end,
        "record_count": len(sample_records),
        "total_units": total_units,
    }
    wal_uri = storage.put_json(wal_key, wal_doc, redact=True)

    # Replay all WALs not yet marked indexed when db_sink is available
    replayed_count = 0
    db_drain_deferred = False
    if db_sink is not None:
        try:
            all_wal_keys = storage.list_keys(f"wal/rollups/{job_id}/{shard_key}")
            done_keys = set(storage.list_keys(f"wal/indexed/{job_id}/{shard_key}"))
            for wk in all_wal_keys:
                marker_key = wk.replace("wal/rollups/", "wal/indexed/", 1)
                if marker_key in done_keys and wk != wal_key:
                    continue
                doc = storage.get_json(wk)
                db_sink(doc)
                storage.put_json(marker_key, {"indexed_by_run": run_id}, redact=False)
                replayed_count += 1
        except Exception as exc:
            # Non-blocking DB drain (`REQ-HEAL-002`): WAL remains safe in Object Storage for next tick
            db_drain_deferred = True
            err_note = str(exc)[:160]
        else:
            err_note = ""
    else:
        err_note = ""

    return {
        "job_id": job_id,
        "run_id": run_id,
        "mode": "batch-watermarked-rollup",
        "status": "Succeeded",
        "shard_key": shard_key,
        "window_start": window_start,
        "window_end": window_end,
        "items_processed": len(sample_records),
        "violations": [],
        "actions_taken": [],
        "watermark_end": window_end,
        "wal_uri": wal_uri,
        "metrics": {
            "total_units": total_units,
            "wal_replayed_count": replayed_count,
            "db_drain_deferred": int(db_drain_deferred),
        },
        "notes": err_note,
    }
