"""ACs for job_status (DESIGN.md §4.3): pending, running, and finished jobs all
return a decoded state_explained."""

from nersc_mcp.tools import jobinfo


def _mock(monkeypatch, squeue=(0, "", ""), sacct=(0, "", "")):
    def fake(argv, timeout=30, stdin_text=None):
        return {"squeue": squeue, "sacct": sacct}[argv[0]]
    monkeypatch.setattr(jobinfo.slurm, "run", fake)


def test_pending_job_decodes_reason(monkeypatch):
    line = "55123|j|PENDING|QOSMaxJobsPerUserLimit|0:00|4:00:00|2026-07-03T09:00:00|2026-07-03T05:00:00\n"
    _mock(monkeypatch, squeue=(0, line, ""))
    res = jobinfo.job_status("55123")
    assert res["ok"] and res["data"]["phase"] == "queued/running"
    assert "per-user run limit" in res["data"]["state_explained"]
    assert res["data"]["start_estimate"] == "2026-07-03T09:00:00"


def test_running_job(monkeypatch):
    line = "55123|j|RUNNING|None|1:23|4:00:00|N/A|2026-07-03T05:00:00\n"
    _mock(monkeypatch, squeue=(0, line, ""))
    res = jobinfo.job_status("55123")
    assert res["data"]["state"] == "RUNNING"
    assert res["data"]["state_explained"]


def test_finished_job_from_sacct(monkeypatch):
    sacct_out = "JobID|JobName|State|ExitCode|Elapsed|Timelimit|Reason\n55123|j|TIMEOUT|0:0|4:00:01|4:00:00|None\n"
    _mock(monkeypatch, squeue=(0, "", ""), sacct=(0, sacct_out, ""))
    res = jobinfo.job_status("55123")
    assert res["ok"] and res["data"]["phase"] == "finished"
    assert "time limit" in res["data"]["state_explained"]


def test_unknown_job(monkeypatch):
    _mock(monkeypatch, squeue=(0, "", ""), sacct=(0, "", ""))
    res = jobinfo.job_status("55123")
    assert not res["ok"] and res["error"]["kind"] == "not_found"


def test_rejects_non_numeric():
    assert not jobinfo.job_status("all; rm -rf /")["ok"]
