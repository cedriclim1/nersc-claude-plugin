"""queue_wait_stats — Iris queue-wait forecasts (DESIGN.md §4.9).

Uses stdlib urllib only. No subprocesses, no background work.
"""

from __future__ import annotations

import json
import math
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional

from .. import knowledge
from ..util import err, result

IRIS_URL = "https://iris.nersc.gov/graphql_web"
IRIS_TIMEOUT_SECONDS = 10
DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"

RECOMMENDATION_RULES = [
    {
        "name": "no_data",
        "max_mean_wait_hours": None,
        "text": "No Iris jobs matched this shape in the requested windows; treat this as advisory only and do not block submission.",
    },
    {
        "name": "short",
        "max_mean_wait_hours": 1.0,
        "text": "Queue waits for this shape have usually been short; submit normally.",
    },
    {
        "name": "moderate",
        "max_mean_wait_hours": 6.0,
        "text": "Expect a moderate queue wait; keep the request as small as the workflow allows.",
    },
    {
        "name": "long",
        "max_mean_wait_hours": 24.0,
        "text": "Expect a long queue wait; consider preempt, premium, or fewer nodes if the workflow allows.",
    },
    {
        "name": "very_long",
        "max_mean_wait_hours": math.inf,
        "text": "Expect a very long queue wait; strongly consider preempt, premium, or reducing nodes/runtime.",
    },
]


def queue_wait_stats(constraint: str, qos: str, hours: float, nodes: int = 1,
                     window_days: int = 30, _now: Optional[datetime] = None) -> dict:
    """Return Iris queue-wait stats for a job shape.

    ``_now`` is for unit tests; server.py does not expose it as a tool argument.
    """
    try:
        nodes_i = int(nodes)
        hours_f = float(hours)
        window_days_i = int(window_days)
    except (TypeError, ValueError):
        return err("bad_args", "nodes, hours, and window_days must be numeric")
    if nodes_i < 1 or hours_f <= 0 or window_days_i < 1:
        return err("bad_args", "nodes >= 1, hours > 0, and window_days >= 1 are required")

    constraint_key = str(constraint).strip().lower()
    qos_key = str(qos).strip()
    iris_qos = knowledge.IRIS_QOS.get((constraint_key, qos_key))
    if iris_qos is None:
        valid = sorted({f"{c}/{q}" for c, q in knowledge.IRIS_QOS})
        return err("bad_args", f"unknown Iris QOS mapping for constraint={constraint!r}, qos={qos!r}",
                   ", ".join(valid))

    # Assumption: these times are the server host's local time. The server runs
    # on Perlmutter login nodes, whose local time matches Iris's data timezone;
    # do not convert to UTC without verifying Iris semantics.
    now = _now or datetime.now()
    long_start = now - timedelta(days=window_days_i)
    short_start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0,
                                                    microsecond=0)
    hour_bucket = int(math.ceil(hours_f))

    try:
        long_rows = parse_response(_post_graphql(iris_qos, long_start, now))
        short_rows = parse_response(_post_graphql(iris_qos, short_start, now))
    except (urllib.error.URLError, OSError) as exc:
        return err("iris_unavailable", "Iris queue-wait request failed; do not block submission decisions",
                   str(exc))
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        return err("iris_parse_failed", "Iris queue-wait response could not be parsed; do not block submission decisions",
                   str(exc))

    long_stats = summarize_bucket(long_rows, iris_qos, nodes_i, hour_bucket)
    short_stats = summarize_bucket(short_rows, iris_qos, nodes_i, hour_bucket)
    hints = []
    if not long_stats["matched"] and not short_stats["matched"]:
        hints.append("no jobs matched this shape in Iris queue-wait history; no wait estimate was fabricated")
    elif not long_stats["matched"]:
        hints.append("no long-term jobs matched this shape; recommendation leans on short-term data only")
    elif not short_stats["matched"]:
        hints.append("no jobs matched this shape since previous-day midnight; current-window contrast is unavailable")

    return result(True, {
        "constraint": constraint_key,
        "qos": qos_key,
        "iris_qos": iris_qos,
        "nodes": nodes_i,
        "hours": hours_f,
        "hour_bucket": hour_bucket,
        "window_days": window_days_i,
        "long_term": long_stats,
        "short_term": short_stats,
        "recommendation": recommendation(long_stats, short_stats),
    }, hints=hints)


def _post_graphql(iris_qos: str, start: datetime, end: datetime) -> dict:
    query = (
        "{ queueWaitTime { queueWaitTime("
        f"qos: {json.dumps(iris_qos)}, "
        f"startMin: {json.dumps(start.strftime(DATE_FORMAT))}, "
        f"startMax: {json.dumps(end.strftime(DATE_FORMAT))}"
        ") { qos nodes hours waitHours jobCount maxWaitHours } } }"
    )
    body = json.dumps({"query": query}).encode("utf-8")
    request = urllib.request.Request(
        IRIS_URL,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=IRIS_TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8"))


def parse_response(payload: dict) -> List[dict]:
    rows = payload["data"]["queueWaitTime"]["queueWaitTime"]
    if not isinstance(rows, list):
        raise ValueError("queueWaitTime payload is not a list")
    parsed = []
    for row in rows:
        parsed.append({
            "qos": str(row["qos"]),
            "nodes": _maybe_int(row.get("nodes")),
            "hours": _maybe_int(row.get("hours")),
            "waitHours": _maybe_float(row.get("waitHours")),
            "jobCount": _maybe_float(row.get("jobCount")) or 0.0,
            "maxWaitHours": _maybe_float(row.get("maxWaitHours")),
        })
    return parsed


def summarize_bucket(rows: Iterable[dict], iris_qos: str, nodes: int,
                     hours: Optional[int]) -> dict:
    job_count = 0.0
    wait_weighted = 0.0
    wait_job_count = 0.0
    null_wait_job_count = 0.0
    max_wait = None
    matched = False

    for row in rows:
        if row.get("qos") != iris_qos:
            continue
        if row.get("nodes") != nodes:
            continue
        if row.get("hours") != hours:
            continue
        matched = True
        count = float(row.get("jobCount") or 0.0)
        job_count += count
        wait = row.get("waitHours")
        if wait is None:
            null_wait_job_count += count
        else:
            wait_weighted += float(wait) * count
            wait_job_count += count
        row_max = row.get("maxWaitHours")
        if row_max is not None:
            max_wait = float(row_max) if max_wait is None else max(max_wait, float(row_max))

    mean_wait = None if wait_job_count == 0 else wait_weighted / wait_job_count
    return {
        "matched": matched,
        "job_count": _round_count(job_count),
        "mean_wait_hours": _round_hours(mean_wait),
        "max_wait_hours": _round_hours(max_wait),
        "null_wait_job_count": _round_count(null_wait_job_count),
    }


def recommendation(long_stats: dict, short_stats: dict) -> str:
    mean = long_stats.get("mean_wait_hours")
    if mean is None:
        mean = short_stats.get("mean_wait_hours")
    rule = recommendation_rule_for(mean)
    detail = []
    if long_stats.get("mean_wait_hours") is not None:
        detail.append(f"long-term mean {_fmt_hours(long_stats['mean_wait_hours'])}")
    if short_stats.get("max_wait_hours") is not None:
        detail.append(f"previous-day max {_fmt_hours(short_stats['max_wait_hours'])}")
    suffix = "" if not detail else " " + "; ".join(detail) + "."
    return rule["text"] + suffix


def recommendation_rule_for(mean_wait_hours: Optional[float]) -> dict:
    if mean_wait_hours is None:
        return RECOMMENDATION_RULES[0]
    for rule in RECOMMENDATION_RULES[1:]:
        if mean_wait_hours <= rule["max_mean_wait_hours"]:
            return rule
    return RECOMMENDATION_RULES[-1]


def _maybe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    return float(value)


def _maybe_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    return int(value)


def _round_hours(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return round(float(value), 3)


def _round_count(value: float) -> int:
    return int(value) if float(value).is_integer() else round(float(value), 3)


def _fmt_hours(value: float) -> str:
    if value < 1:
        return f"{round(value * 60):g} min"
    return f"{value:.1f} h"
