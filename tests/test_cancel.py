"""ACs for cancel_job (DESIGN.md §4.5) — confirm + age guards."""

from datetime import datetime, timedelta

from nersc_mcp.tools import cancel


def _squeue_line(state, submitted):
    return f"55123|myjob|{state}|Priority|0:00|4:00:00|N/A|{submitted}\n"


def _mock_run(squeue_out):
    def fake(argv, timeout=30, stdin_text=None):
        if argv[0] == "squeue":
            return 0, squeue_out, ""
        if argv[0] == "scancel":
            return 0, "", ""
        raise AssertionError(argv)
    return fake


def test_refuses_without_confirm():
    res = cancel.cancel_job("55123")
    assert not res["ok"] and res["error"]["kind"] == "needs_confirm"


def test_age_guard_blocks_old_pending(monkeypatch):
    old = (datetime.now() - timedelta(hours=3)).isoformat(timespec="seconds")
    monkeypatch.setattr(cancel.slurm, "run", _mock_run(_squeue_line("PENDING", old)))
    res = cancel.cancel_job("55123", confirm=True)
    assert not res["ok"] and res["error"]["kind"] == "age_guard"
    assert "YOUNGEST" in res["error"]["message"]


def test_force_overrides_age_guard(monkeypatch):
    old = (datetime.now() - timedelta(hours=3)).isoformat(timespec="seconds")
    monkeypatch.setattr(cancel.slurm, "run", _mock_run(_squeue_line("PENDING", old)))
    res = cancel.cancel_job("55123", confirm=True, force=True)
    assert res["ok"] and res["data"]["cancelled"]


def test_young_pending_cancels(monkeypatch):
    young = (datetime.now() - timedelta(minutes=5)).isoformat(timespec="seconds")
    monkeypatch.setattr(cancel.slurm, "run", _mock_run(_squeue_line("PENDING", young)))
    res = cancel.cancel_job("55123", confirm=True)
    assert res["ok"]


def test_running_job_cancels_without_age_guard(monkeypatch):
    old = (datetime.now() - timedelta(hours=9)).isoformat(timespec="seconds")
    monkeypatch.setattr(cancel.slurm, "run", _mock_run(_squeue_line("RUNNING", old)))
    res = cancel.cancel_job("55123", confirm=True)
    assert res["ok"]


def test_unparseable_submit_time_fails_closed(monkeypatch):
    monkeypatch.setattr(cancel.slurm, "run", _mock_run(_squeue_line("PENDING", "N/A")))
    res = cancel.cancel_job("55123", confirm=True)
    assert not res["ok"] and res["error"]["kind"] == "age_guard"
    assert "could not be parsed" in res["error"]["message"]
