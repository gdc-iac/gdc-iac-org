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
"""5-field Cron expression validator, next-5 run preview, DST skip/dup detector & UTC windowing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class CronValidationError(ValueError):
    """Raised when a cron expression, timezone, or cadence constraint is invalid."""


def _parse_field(expr: str, min_val: int, max_val: int, is_dow: bool = False) -> tuple[set[int], bool]:
    """Parse a single 5-field cron token into a sorted integer set and wildcard flag."""
    token = expr.strip()
    if not token:
        raise CronValidationError("Empty cron field")
    is_wildcard = token == "*"
    values: set[int] = set()
    for part in token.split(","):
        part = part.strip()
        if not part:
            raise CronValidationError(f"Invalid empty list element in {expr!r}")
        step = 1
        if "/" in part:
            base, step_str = part.split("/", 1)
            if not step_str.isdigit() or int(step_str) <= 0:
                raise CronValidationError(f"Invalid cron step in {expr!r}")
            step = int(step_str)
        else:
            base = part

        if base == "*":
            start, end = min_val, max_val
        elif "-" in base:
            s_str, e_str = base.split("-", 1)
            if not (s_str.isdigit() and e_str.isdigit()):
                raise CronValidationError(f"Invalid cron range in {expr!r}")
            start, end = int(s_str), int(e_str)
        else:
            if not base.isdigit():
                raise CronValidationError(f"Invalid cron literal in {expr!r}")
            start = end = int(base)

        if is_dow:
            if start == 7:
                start = 0
            if end == 7 and start == 0 and "-" not in base:
                end = 0
        if start < min_val or end > (7 if is_dow else max_val) or start > end:
            raise CronValidationError(
                f"Cron value out of range [{min_val}..{max_val}] in {expr!r}"
            )
        for v in range(start, end + 1, step):
            values.add(0 if (is_dow and v == 7) else v)

    return values, is_wildcard


@dataclass(frozen=True)
class ParsedCron:
    raw: str
    minutes: frozenset[int]
    hours: frozenset[int]
    days_of_month: frozenset[int]
    months: frozenset[int]
    days_of_week: frozenset[int]
    dom_wildcard: bool
    dow_wildcard: bool

    def matches(self, dt: datetime) -> bool:
        if dt.minute not in self.minutes or dt.hour not in self.hours or dt.month not in self.months:
            return False
        # Standard Vixie cron: Python weekday() has Monday=0..Sunday=6; cron has Sunday=0..Saturday=6
        cron_dow = (dt.weekday() + 1) % 7
        dom_match = dt.day in self.days_of_month
        dow_match = cron_dow in self.days_of_week
        if self.dom_wildcard and self.dow_wildcard:
            return True
        if self.dom_wildcard:
            return dow_match
        if self.dow_wildcard:
            return dom_match
        return dom_match or dow_match


def parse_cron_expression(cron_expr: str) -> ParsedCron:
    """Validate and parse a standard 5-field cron expression (`min hour dom month dow`)."""
    if not cron_expr or not isinstance(cron_expr, str):
        raise CronValidationError("Cron expression must be a non-empty string")
    fields = cron_expr.strip().split()
    if len(fields) != 5:
        raise CronValidationError(
            f"Expected standard 5-field cron expression, got {len(fields)} fields: {cron_expr!r}"
        )
    minutes, _ = _parse_field(fields[0], 0, 59)
    hours, _ = _parse_field(fields[1], 0, 23)
    dom, dom_wc = _parse_field(fields[2], 1, 31)
    months, _ = _parse_field(fields[3], 1, 12)
    dow, dow_wc = _parse_field(fields[4], 0, 6, is_dow=True)
    return ParsedCron(
        raw=" ".join(fields),
        minutes=frozenset(minutes),
        hours=frozenset(hours),
        days_of_month=frozenset(dom),
        months=frozenset(months),
        days_of_week=frozenset(dow),
        dom_wildcard=dom_wc,
        dow_wildcard=dow_wc,
    )


def validate_timezone(tz_name: str) -> ZoneInfo:
    """Resolve an IANA timezone name (defaulting to UTC)."""
    cleaned = (tz_name or "UTC").strip()
    try:
        return ZoneInfo(cleaned)
    except (ZoneInfoNotFoundError, KeyError, ValueError) as exc:
        raise CronValidationError(f"Invalid IANA timezone: {tz_name!r}") from exc


def _timezone_has_dst(tz: ZoneInfo, reference_year: int) -> bool:
    jan = datetime(reference_year, 1, 15, 12, 0, tzinfo=tz)
    jul = datetime(reference_year, 7, 15, 12, 0, tzinfo=tz)
    return jan.utcoffset() != jul.utcoffset()


def preview_schedule(
    cron_expr: str,
    tz_name: str = "UTC",
    count: int = 5,
    now_utc: datetime | None = None,
    persona: str = "AO",
    min_ao_interval_minutes: int = 5,
) -> dict[str, object]:
    """Compute the next N firing timestamps in UTC + local timezone, DST warnings, and cadence check."""
    parsed = parse_cron_expression(cron_expr)
    tz = validate_timezone(tz_name)
    base_utc = (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
    cursor_utc = base_utc.replace(second=0, microsecond=0) + timedelta(minutes=1)

    runs_utc: list[datetime] = []
    runs_local_iso: list[str] = []
    dst_warnings: list[str] = []

    if tz_name.strip().upper() not in ("UTC", "ETC/UTC", "GMT"):
        if _timezone_has_dst(tz, cursor_utc.year):
            dst_warnings.append(
                f"Timezone '{tz_name}' observes Daylight Saving Time (DST). Spring-forward hours "
                "may skip scheduled runs and fall-back hours may shift local wall-clock intervals. "
                "Prefer 'UTC' for mission-critical GDC-ag schedules; all internal watermarks and "
                "execution windows remain strictly UTC."
            )

    # Step minute-by-minute in UTC up to 400 days max to find next `count` matches
    max_iters = 60 * 24 * 400
    steps = 0
    prev_offset = cursor_utc.astimezone(tz).utcoffset()
    while len(runs_utc) < count and steps < max_iters:
        local_dt = cursor_utc.astimezone(tz)
        cur_offset = local_dt.utcoffset()
        if cur_offset != prev_offset and not any("transition detected" in w for w in dst_warnings):
            dst_warnings.append(
                f"Upcoming DST UTC-offset transition detected around {cursor_utc.strftime('%Y-%m-%dT%H:%M:%SZ')}."
            )
        prev_offset = cur_offset
        if parsed.matches(local_dt):
            runs_utc.append(cursor_utc)
            runs_local_iso.append(local_dt.isoformat())
        cursor_utc += timedelta(minutes=1)
        steps += 1

    if len(runs_utc) < count:
        raise CronValidationError(
            f"Cron expression {cron_expr!r} did not produce {count} runs within 400 days"
        )

    # Enforce AO minimum cron cadence floor (REQ-REL-004)
    min_delta_minutes = min(
        int((runs_utc[i + 1] - runs_utc[i]).total_seconds() // 60)
        for i in range(len(runs_utc) - 1)
    )
    if persona.upper() == "AO" and min_delta_minutes < min_ao_interval_minutes:
        raise CronValidationError(
            f"AO schedule cadence ({min_delta_minutes}m) violates minimum floor "
            f"(>= {min_ao_interval_minutes}m); use PA persona or widen interval."
        )

    return {
        "cron": parsed.raw,
        "timezone": tz_name.strip() or "UTC",
        "next_runs_utc": [dt.strftime("%Y-%m-%dT%H:%M:%SZ") for dt in runs_utc],
        "next_runs_local": runs_local_iso,
        "min_interval_minutes": min_delta_minutes,
        "dst_warnings": dst_warnings,
    }


def normalize_utc_iso(ts: str | datetime) -> str:
    """Parse an ISO-8601 timestamp or datetime and normalize strictly to UTC `YYYY-MM-DDTHH:MM:SSZ`."""
    if isinstance(ts, datetime):
        dt = ts if ts.tzinfo is not None else ts.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    raw = ts.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def generate_utc_windows(
    start_iso: str, end_iso: str, step_seconds: int = 900, max_windows: int = 100
) -> list[tuple[str, str]]:
    """Slice a historical backfill `[start, end)` interval into bounded UTC windows."""
    if step_seconds <= 0:
        raise CronValidationError("step_seconds must be positive")
    start_str = normalize_utc_iso(start_iso)
    end_str = normalize_utc_iso(end_iso)
    start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
    end_dt = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
    if end_dt <= start_dt:
        raise CronValidationError("window_end must be strictly after window_start")
    windows: list[tuple[str, str]] = []
    cur = start_dt
    step = timedelta(seconds=step_seconds)
    while cur < end_dt:
        nxt = min(cur + step, end_dt)
        windows.append(
            (
                cur.strftime("%Y-%m-%dT%H:%M:%SZ"),
                nxt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            )
        )
        if len(windows) > max_windows:
            raise CronValidationError(
                f"Backfill range exceeds maximum {max_windows} slices; narrow range or increase step"
            )
        cur = nxt
    return windows
