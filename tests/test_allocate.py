"""ACs for allocate_interactive (DESIGN.md §4.7): JID parse + verbatim srun pattern,
plus the timeout-orphan cleanup path."""

from nersc_mcp.tools import allocate


def test_granted_allocation_returns_pattern(monkeypatch):
    monkeypatch.setattr(allocate.slurm, "run",
                        lambda argv, timeout=30, stdin_text=None:
                        (0, "", "salloc: Granted job allocation 55999\n"))
    res = allocate.allocate_interactive("m5020", nodes=1)
    assert res["ok"] and res["data"]["jobid"] == "55999"
    assert "SLURM_JOB_ID=55999 srun --jobid=55999" in res["data"]["usage_pattern"]


def test_timeout_with_pending_jid_cancels_it(monkeypatch):
    calls = []

    def fake(argv, timeout=30, stdin_text=None):
        calls.append(argv)
        if argv[0] == "salloc":
            return 124, "salloc: Pending job allocation 55888\n", "timeout after 180s"
        return 0, "", ""
    monkeypatch.setattr(allocate.slurm, "run", fake)
    res = allocate.allocate_interactive("m5020")
    assert not res["ok"] and res["error"]["kind"] == "salloc_timeout"
    assert ["scancel", "55888"] in calls
    assert "55888" in res["error"]["message"]


def test_timeout_without_jid_warns(monkeypatch):
    monkeypatch.setattr(allocate.slurm, "run",
                        lambda argv, timeout=30, stdin_text=None:
                        (124, "", "timeout after 180s"))
    res = allocate.allocate_interactive("m5020")
    assert not res["ok"] and "squeue --me" in res["error"]["message"]


def test_rejects_ambiguous_time():
    res = allocate.allocate_interactive("m5020", time="04:00")
    assert not res["ok"] and "MINUTES:SECONDS" in res["error"]["message"]


def test_rejects_bad_constraint_and_missing_account():
    assert not allocate.allocate_interactive("m5020", constraint="tpu")["ok"]
    assert not allocate.allocate_interactive("")["ok"]
