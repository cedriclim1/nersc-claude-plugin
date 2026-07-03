"""ACs for check_storage (§4.8) and nersc_status (§4.1)."""

from nersc_mcp.tools import status, storage


def _mock(monkeypatch, module, mapping):
    def fake(argv, timeout=30, stdin_text=None):
        return mapping.get(argv[0], (127, "", f"command not found: {argv[0]}"))
    monkeypatch.setattr(module.slurm, "run", fake)


def test_storage_placement_software(monkeypatch):
    _mock(monkeypatch, storage, {"showquota": (0, "HOME 12G/40G\n", "")})
    res = storage.check_storage("software")
    assert res["ok"]
    assert "/global/common/software" in res["data"]["placement"]["path"]


def test_storage_cfs_flock_warning(monkeypatch):
    _mock(monkeypatch, storage, {"showquota": (0, "", "")})
    res = storage.check_storage("shared_data")
    assert any("flock" in w for w in res["warnings"])


def test_storage_scratch_purge_warning(monkeypatch):
    _mock(monkeypatch, storage, {"showquota": (0, "", "")})
    res = storage.check_storage("job_io")
    assert any("purged" in w for w in res["warnings"])


def test_storage_unknown_need(monkeypatch):
    _mock(monkeypatch, storage, {"showquota": (0, "", "")})
    res = storage.check_storage("everything")
    assert not res["ok"] and res["error"]["kind"] == "bad_args"


SHOWQUOTA_FIXTURE = """\
Filesystem    Usage        Limit      %Used
home          12.3GiB      40.0GiB    31%
pscratch      1.2TiB       20.0TiB    6%
cfs_m5020     8.7TiB       20.0TiB    43%
"""


def test_storage_parses_showquota(monkeypatch):
    _mock(monkeypatch, storage, {"showquota": (0, SHOWQUOTA_FIXTURE, "")})
    res = storage.check_storage()
    rows = res["data"]["quotas"]
    assert {"filesystem": "home", "used": "12.3GiB", "limit": "40.0GiB"} in rows
    assert len(rows) == 3


def test_storage_unparseable_quota_warns(monkeypatch):
    _mock(monkeypatch, storage, {"showquota": (0, "something novel\n", "")})
    res = storage.check_storage()
    assert res["data"]["quotas"] == []
    assert any("did not match" in w for w in res["warnings"])


def test_status_zero_jobs(monkeypatch):
    _mock(monkeypatch, status, {"squeue": (0, "", ""), "sacct": (0, "", "")})
    res = status.nersc_status()
    assert res["ok"] and res["data"]["queued"] == []


def test_status_decodes_reason(monkeypatch):
    line = "1|j|PENDING|QOSMaxJobsPerUserLimit|0:00|1:00|N/A|2026-07-03T00:00:00\n"
    _mock(monkeypatch, status, {"squeue": (0, line, ""), "sacct": (0, "", "")})
    res = status.nersc_status()
    assert "per-user run limit" in res["data"]["queued"][0]["reason_explained"]
