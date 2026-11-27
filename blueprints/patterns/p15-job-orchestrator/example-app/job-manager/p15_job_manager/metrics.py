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
"""Prometheus text exposition (`0.0.4`) for all 7 required `REQ-NOTIF-001` metric families."""

from __future__ import annotations

import threading

_DURATION_BUCKETS = (1.0, 5.0, 15.0, 60.0, 300.0, 900.0, 3600.0)


def _fmt_labels(labels: dict[str, str]) -> str:
    if not labels:
        return ""
    parts = []
    for k, v in labels.items():
        esc = str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        parts.append(f'{k}="{esc}"')
    return "{" + ",".join(parts) + "}"


class MetricsRegistry:
    """Thread-safe Prometheus metric collector for `p15-job-manager` (`/metrics`)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last_success: dict[tuple[str, str, str, str], float] = {}
        self._runs_total: dict[tuple[str, str, str, str], int] = {}
        self._duration_buckets: dict[tuple[str, str], list[int]] = {}
        self._duration_sum: dict[tuple[str, str], float] = {}
        self._duration_count: dict[tuple[str, str], int] = {}
        self._watermark_lag: dict[tuple[str, str, str], float] = {}
        self._violations_total: dict[tuple[str, str, str, str], int] = {}
        self._self_heal_total: dict[tuple[str, str, str, str], int] = {}
        self._circuit_open: dict[tuple[str, str], int] = {}
        self._dead_letter_total: dict[tuple[str, str], int] = {}

    def record_job_run(
        self,
        namespace: str,
        job_name: str,
        job_class: str,
        persona: str,
        status: str,
        trigger: str,
        duration_seconds: float | None = None,
        finished_epoch: float | None = None,
    ) -> None:
        with self._lock:
            rkey = (namespace, job_name, status, trigger)
            self._runs_total[rkey] = self._runs_total.get(rkey, 0) + 1
            if status == "Succeeded" and finished_epoch is not None:
                self._last_success[(namespace, job_name, job_class, persona)] = finished_epoch
            if duration_seconds is not None:
                dkey = (namespace, job_name)
                if dkey not in self._duration_buckets:
                    self._duration_buckets[dkey] = [0] * len(_DURATION_BUCKETS)
                for idx, bound in enumerate(_DURATION_BUCKETS):
                    if duration_seconds <= bound:
                        self._duration_buckets[dkey][idx] += 1
                self._duration_sum[dkey] = self._duration_sum.get(dkey, 0.0) + max(0.0, duration_seconds)
                self._duration_count[dkey] = self._duration_count.get(dkey, 0) + 1

    def set_watermark_lag(self, namespace: str, job_name: str, shard_key: str, lag_seconds: float) -> None:
        with self._lock:
            self._watermark_lag[(namespace, job_name, shard_key)] = max(0.0, lag_seconds)

    def inc_violation(self, namespace: str, job_name: str, severity: str, mode: str, count: int = 1) -> None:
        with self._lock:
            key = (namespace, job_name, severity, mode)
            self._violations_total[key] = self._violations_total.get(key, 0) + count

    def inc_self_heal(self, namespace: str, job_name: str, layer: str, outcome: str, count: int = 1) -> None:
        with self._lock:
            key = (namespace, job_name, layer, outcome)
            self._self_heal_total[key] = self._self_heal_total.get(key, 0) + count

    def set_circuit_breaker(self, namespace: str, job_name: str, is_open: bool) -> None:
        with self._lock:
            self._circuit_open[(namespace, job_name)] = 1 if is_open else 0

    def inc_dead_letter(self, namespace: str, sink_name: str, count: int = 1) -> None:
        with self._lock:
            key = (namespace, sink_name)
            self._dead_letter_total[key] = self._dead_letter_total.get(key, 0) + count

    def render_prometheus(self) -> str:
        with self._lock:
            lines: list[str] = [
                "# HELP gdc_job_last_success_timestamp_seconds Unix timestamp of last successful job completion.",
                "# TYPE gdc_job_last_success_timestamp_seconds gauge",
            ]
            for (ns, jn, jc, per), val in sorted(self._last_success.items()):
                lbl = _fmt_labels({"namespace": ns, "job_name": jn, "job_class": jc, "persona": per})
                lines.append(f"gdc_job_last_success_timestamp_seconds{lbl} {val:.3f}")

            lines.extend(
                [
                    "# HELP gdc_job_runs_total Total job runs partitioned by status and trigger.",
                    "# TYPE gdc_job_runs_total counter",
                ]
            )
            for (ns, jn, st, tr), cnt in sorted(self._runs_total.items()):
                lbl = _fmt_labels({"namespace": ns, "job_name": jn, "status": st, "trigger": tr})
                lines.append(f"gdc_job_runs_total{lbl} {cnt}")

            lines.extend(
                [
                    "# HELP gdc_job_duration_seconds Histogram of job execution duration in seconds.",
                    "# TYPE gdc_job_duration_seconds histogram",
                ]
            )
            for (ns, jn), counts in sorted(self._duration_buckets.items()):
                total = self._duration_count.get((ns, jn), 0)
                dsum = self._duration_sum.get((ns, jn), 0.0)
                for idx, bound in enumerate(_DURATION_BUCKETS):
                    lbl = _fmt_labels({"namespace": ns, "job_name": jn, "le": str(bound)})
                    lines.append(f"gdc_job_duration_seconds_bucket{lbl} {counts[idx]}")
                inf_lbl = _fmt_labels({"namespace": ns, "job_name": jn, "le": "+Inf"})
                lines.append(f"gdc_job_duration_seconds_bucket{inf_lbl} {total}")
                base_lbl = _fmt_labels({"namespace": ns, "job_name": jn})
                lines.append(f"gdc_job_duration_seconds_sum{base_lbl} {dsum:.3f}")
                lines.append(f"gdc_job_duration_seconds_count{base_lbl} {total}")

            lines.extend(
                [
                    "# HELP gdc_job_watermark_lag_seconds Current watermark lag in seconds per job shard.",
                    "# TYPE gdc_job_watermark_lag_seconds gauge",
                ]
            )
            for (ns, jn, sk), lag in sorted(self._watermark_lag.items()):
                lbl = _fmt_labels({"namespace": ns, "job_name": jn, "shard_key": sk})
                lines.append(f"gdc_job_watermark_lag_seconds{lbl} {lag:.3f}")

            lines.extend(
                [
                    "# HELP gdc_job_enforcement_violations_total Detected policy/compliance violations.",
                    "# TYPE gdc_job_enforcement_violations_total counter",
                ]
            )
            for (ns, jn, sev, md), cnt in sorted(self._violations_total.items()):
                lbl = _fmt_labels({"namespace": ns, "job_name": jn, "severity": sev, "mode": md})
                lines.append(f"gdc_job_enforcement_violations_total{lbl} {cnt}")

            lines.extend(
                [
                    "# HELP gdc_job_self_heal_actions_total Self-healing actions across Layer 1 and Layer 2.",
                    "# TYPE gdc_job_self_heal_actions_total counter",
                ]
            )
            for (ns, jn, lyr, out), cnt in sorted(self._self_heal_total.items()):
                lbl = _fmt_labels({"namespace": ns, "job_name": jn, "layer": lyr, "outcome": out})
                lines.append(f"gdc_job_self_heal_actions_total{lbl} {cnt}")

            lines.extend(
                [
                    "# HELP gdc_job_circuit_breaker_open Whether the job circuit breaker is open (1) or closed (0).",
                    "# TYPE gdc_job_circuit_breaker_open gauge",
                ]
            )
            for (ns, jn), flag in sorted(self._circuit_open.items()):
                lbl = _fmt_labels({"namespace": ns, "job_name": jn})
                lines.append(f"gdc_job_circuit_breaker_open{lbl} {flag}")

            lines.extend(
                [
                    "# HELP gdc_job_notification_dead_letter_total Exhausted notification outbox events moved to dead_letter.",
                    "# TYPE gdc_job_notification_dead_letter_total counter",
                ]
            )
            for (ns, sn), cnt in sorted(self._dead_letter_total.items()):
                lbl = _fmt_labels({"namespace": ns, "sink_name": sn})
                lines.append(f"gdc_job_notification_dead_letter_total{lbl} {cnt}")

            lines.append("")
            return "\n".join(lines)
