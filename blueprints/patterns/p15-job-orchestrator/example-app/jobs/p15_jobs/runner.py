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
"""Orchestrator-Agnostic Container Contract Entrypoint (`gdc-standard-job-runner-v1`, `REQ-ENG-003`)."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
import time
from typing import Any

_COMMON_PARENT = str(Path(__file__).resolve().parents[2])
if _COMMON_PARENT not in sys.path:
    sys.path.insert(0, _COMMON_PARENT)

from common.redaction import redact_payload  # noqa: E402
from common.storage import DualModeStorageAdapter, build_job_artifact_key  # noqa: E402
from .batch_rollup import execute_batch_watermarked_rollup
from .enforce_policy import execute_enforce_resource_policy
from .monitor_hygiene import execute_monitor_platform_hygiene

DEFAULT_RESULT_PATH = Path("/tmp/job-out/result.json")


def run_worker_contract(
    mode: str,
    job_id: str,
    run_id: str,
    window_start: str = "",
    window_end: str = "",
    shard_key: str = "all",
    sink_uri: str = "",
    enforcement_mode: str = "audit",
    namespace: str | None = None,
    result_path: Path = DEFAULT_RESULT_PATH,
    storage: DualModeStorageAdapter | None = None,
) -> dict[str, Any]:
    """Execute one of the standardised job modes under `gdc-standard-job-runner-v1`."""
    t0 = time.monotonic()
    now = datetime.now(timezone.utc)
    w_end = window_end.strip() or now.strftime("%Y-%m-%dT%H:%M:%SZ")
    w_start = window_start.strip() or (now - timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M:%SZ")
    ns = namespace or os.getenv("NAMESPACE", "test-project")

    store = storage or DualModeStorageAdapter(bucket_name=sink_uri or os.getenv("BUCKET_NAME", "p15-jobs-ledger"))

    if mode == "batch-watermarked-rollup":
        result = execute_batch_watermarked_rollup(
            job_id=job_id,
            run_id=run_id,
            window_start=w_start,
            window_end=w_end,
            shard_key=shard_key,
            storage=store,
        )
    elif mode == "monitor-platform-hygiene":
        result = execute_monitor_platform_hygiene(
            job_id=job_id,
            run_id=run_id,
            window_start=w_start,
            window_end=w_end,
        )
    elif mode == "enforce-resource-policy":
        result = execute_enforce_resource_policy(
            job_id=job_id,
            run_id=run_id,
            window_start=w_start,
            window_end=w_end,
            enforcement_mode=enforcement_mode,
            storage=store,
        )
    else:
        raise ValueError(f"Unsupported worker --mode {mode!r}")

    result.setdefault("metrics", {})["duration_ms"] = round((time.monotonic() - t0) * 1000.0, 2)
    sanitized = redact_payload(result)

    # 1. Persist canonical local output file `/tmp/job-out/result.json`
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(sanitized, sort_keys=True, indent=2), encoding="utf-8")

    # 2. Archive redacted result bundle to Object Storage (`s3://` on GDC-ag, `gs://` on GKE)
    obj_key = build_job_artifact_key(ns, job_id, run_id, "result.json", ts=now)
    sanitized["artifact_uri"] = store.put_json(obj_key, sanitized, redact=True)
    result_path.write_text(json.dumps(sanitized, sort_keys=True, indent=2), encoding="utf-8")
    return sanitized


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="GDC-ag Pattern 15 Standard Job Runner v1")
    parser.add_argument(
        "--mode",
        required=True,
        choices=["batch-watermarked-rollup", "monitor-platform-hygiene", "enforce-resource-policy"],
    )
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--window-start", default="")
    parser.add_argument("--window-end", default="")
    parser.add_argument("--shard-key", default="all")
    parser.add_argument("--sink-uri", default="")
    parser.add_argument(
        "--enforcement-mode",
        default="audit",
        choices=["audit", "dry-run", "hitl-approval", "enforce"],
    )
    parser.add_argument("--output-file", default=str(DEFAULT_RESULT_PATH))

    try:
        args = parser.parse_args(argv)
        res = run_worker_contract(
            mode=args.mode,
            job_id=args.job_id,
            run_id=args.run_id,
            window_start=args.window_start,
            window_end=args.window_end,
            shard_key=args.shard_key,
            sink_uri=args.sink_uri,
            enforcement_mode=args.enforcement_mode,
            result_path=Path(args.output_file),
        )
        print(json.dumps({"status": res["status"], "artifact_uri": res["artifact_uri"]}))
        return 0
    except ValueError as exc:
        # Exit code 2 signals non-retryable configuration/parameter error (`REQ-HEAL-001`)
        sys.stderr.write(f"Configuration error (non-retryable): {exc}\n")
        return 2


if __name__ == "__main__":
    sys.exit(main())
