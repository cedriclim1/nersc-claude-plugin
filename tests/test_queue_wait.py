"""ACs for queue_wait_stats (DESIGN.md §4.9) — Iris parser and policy."""

import json
from datetime import datetime
from pathlib import Path

import pytest

from nersc_mcp import knowledge
from nersc_mcp.tools import queue_wait


FIXTURE = Path(__file__).parent / "fixtures" / "iris_queuewait.json"


def _fixture_payload():
    return json.loads(FIXTURE.read_text())


def test_qos_mapping_table_includes_cpu_gpu_and_live_probe_names():
    assert knowledge.IRIS_QOS[("cpu", "regular")] == "regular_1"
    assert knowledge.IRIS_QOS[("gpu", "regular")] == "gpu_regular"
    assert knowledge.IRIS_QOS[("gpu", "debug")] == "gpu_debug"
    assert knowledge.IRIS_QOS[("gpu", "interactive")] == "gpu_interactive"
    assert knowledge.IRIS_QOS[("gpu", "preempt")] == "gpu_preempt"
    assert knowledge.IRIS_QOS[("gpu", "premium")] == "gpu_premium"
    assert knowledge.IRIS_QOS[("cpu", "shared")] == "shared"
    assert knowledge.IRIS_QOS[("cpu", "overrun")] == "overrun"
    assert knowledge.IRIS_QOS[("cpu", "regular_1")] == "regular_1"
    assert knowledge.IRIS_QOS[("cpu", "realtime_lcls")] == "realtime_lcls"


def test_parser_fixture_covers_observed_qos_and_null_waits():
    rows = queue_wait.parse_response(_fixture_payload())
    observed = {row["qos"] for row in rows}
    expected = {
        "RESERVE", "badger", "cron", "debug", "debug_preempt",
        "express_amsc", "interactive", "jupyter", "overrun", "preempt",
        "premium", "realtime_als", "realtime_desi", "realtime_lcls",
        "realtime_m3795", "realtime_m4616", "realtime_m5070",
        "realtime_m5149", "realtime_nstaff", "regular_1",
    }
    assert expected <= observed

    reserve = queue_wait.summarize_bucket(rows, "RESERVE", 1, None)
    assert reserve["matched"]
    assert reserve["job_count"] == 71
    assert reserve["mean_wait_hours"] is None
    assert reserve["null_wait_job_count"] == 71

    regular = queue_wait.summarize_bucket(rows, "regular_1", 1, 1)
    assert regular["job_count"] == 15
    assert regular["mean_wait_hours"] == 2.0
    assert regular["max_wait_hours"] == 8.0
    assert regular["null_wait_job_count"] == 5


def test_queue_wait_stats_uses_two_windows_and_returns_recommendation(monkeypatch):
    calls = []

    def fake_post(iris_qos, start, end):
        calls.append((iris_qos, start, end))
        return _fixture_payload()

    monkeypatch.setattr(queue_wait, "_post_graphql", fake_post)
    now = datetime(2026, 7, 3, 12, 30, 0)
    res = queue_wait.queue_wait_stats("cpu", "regular", hours=1, nodes=1,
                                      window_days=30, _now=now)
    assert res["ok"]
    assert res["data"]["iris_qos"] == "regular_1"
    assert res["data"]["long_term"]["mean_wait_hours"] == 2.0
    assert "moderate queue wait" in res["data"]["recommendation"]
    assert len(calls) == 2
    assert calls[0][1] == datetime(2026, 6, 3, 12, 30, 0)
    assert calls[1][1] == datetime(2026, 7, 2, 0, 0, 0)


def test_empty_bucket_is_ok_with_no_data_hint(monkeypatch):
    def fake_post(iris_qos, start, end):
        return {"data": {"queueWaitTime": {"queueWaitTime": []}}}

    monkeypatch.setattr(queue_wait, "_post_graphql", fake_post)
    res = queue_wait.queue_wait_stats("cpu", "regular", hours=1, nodes=1,
                                      _now=datetime(2026, 7, 3, 12, 0, 0))
    assert res["ok"]
    assert res["data"]["long_term"]["matched"] is False
    assert any("no jobs matched this shape" in hint for hint in res["hints"])
    assert "No Iris jobs matched" in res["data"]["recommendation"]


@pytest.mark.parametrize("mean,rule_name", [
    (None, "no_data"),
    (0.5, "short"),
    (2.0, "moderate"),
    (12.0, "long"),
    (30.0, "very_long"),
])
def test_recommendation_threshold_table(mean, rule_name):
    rule = queue_wait.recommendation_rule_for(mean)
    assert rule["name"] == rule_name
    assert rule["text"]
    assert rule in queue_wait.RECOMMENDATION_RULES


def test_network_failure_returns_structured_error(monkeypatch):
    def fake_post(iris_qos, start, end):
        raise OSError("network down")

    monkeypatch.setattr(queue_wait, "_post_graphql", fake_post)
    res = queue_wait.queue_wait_stats("cpu", "regular", hours=1, nodes=1,
                                      _now=datetime(2026, 7, 3, 12, 0, 0))
    assert not res["ok"]
    assert res["error"]["kind"] == "iris_unavailable"
    assert "do not block" in res["error"]["message"]
    assert "network down" in res["error"]["raw"]
