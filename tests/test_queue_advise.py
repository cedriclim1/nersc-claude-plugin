"""ACs for queue_advise (DESIGN.md §4.6) — table boundaries."""

from nersc_mcp.tools.queue_advise import queue_advise


def test_small_short_job_gets_debug():
    res = queue_advise(nodes=2, time_minutes=20)
    assert res["ok"] and res["data"]["qos"] == "debug"


def test_over_30min_leaves_debug():
    res = queue_advise(nodes=2, time_minutes=31)
    assert res["data"]["qos"] == "regular"


def test_nine_nodes_leaves_debug():
    res = queue_advise(nodes=9, time_minutes=10)
    assert res["data"]["qos"] == "regular"


def test_interactive_flag():
    res = queue_advise(nodes=2, time_minutes=60, gpus=4, interactive=True)
    assert res["data"]["qos"] == "interactive"


def test_interactive_over_4_nodes_refused():
    res = queue_advise(nodes=5, time_minutes=60, interactive=True)
    assert not res["ok"]


def test_over_48h_refused():
    res = queue_advise(nodes=4, time_minutes=48 * 60 + 1)
    assert not res["ok"]


def test_big_gpu_job_discount_hint():
    res = queue_advise(nodes=128, time_minutes=600, gpus=512)
    assert any("50%" in h for h in res["hints"])


def test_long_job_preempt_hint():
    res = queue_advise(nodes=4, time_minutes=180, gpus=16)
    assert any("preempt" in h for h in res["hints"])


def test_charge_math():
    res = queue_advise(nodes=10, time_minutes=120)
    assert res["data"]["estimated_charge_node_hours"] == 20.0
