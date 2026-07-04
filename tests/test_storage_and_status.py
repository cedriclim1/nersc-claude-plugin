"""ACs for check_storage (§4.8) and nersc_status (§4.1)."""

import json

from nersc_mcp.tools import status, storage


def _mock(monkeypatch, module, mapping, projects=()):
    def fake(argv, timeout=30, stdin_text=None):
        return mapping.get(argv[0], (127, "", f"command not found: {argv[0]}"))
    monkeypatch.setattr(module.slurm, "run", fake)
    if module is storage:
        monkeypatch.setattr(storage, "user_projects", lambda: list(projects))


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
    # Table output flows through the -J path and normalizes to the JSON keys.
    _mock(monkeypatch, storage, {"showquota": (0, SHOWQUOTA_FIXTURE, "")})
    res = storage.check_storage()
    rows = res["data"]["quotas"]
    assert {"fs": "home", "space_used": "12.3GiB", "space_quota": "40.0GiB"} in rows
    assert len(rows) == 3
    assert res["data"]["raw"]["user"].startswith("Filesystem")


def test_storage_retries_without_J_flag(monkeypatch):
    calls = []
    def fake(argv, timeout=30, stdin_text=None):
        calls.append(list(argv))
        if "-J" in argv:
            return 2, "", "unknown option -J"
        return 0, SHOWQUOTA_FIXTURE, ""
    monkeypatch.setattr(storage.slurm, "run", fake)
    monkeypatch.setattr(storage, "user_projects", lambda: [])
    res = storage.check_storage()
    assert calls[0] == ["showquota", "-J"] and calls[1] == ["showquota"]
    assert res["data"]["quotas"][0]["fs"] == "home"


def test_storage_unparseable_quota_warns(monkeypatch):
    _mock(monkeypatch, storage, {"showquota": (0, "something novel\n", "")})
    res = storage.check_storage()
    assert res["data"]["quotas"] == []
    assert any("did not match" in w for w in res["warnings"])


def _q(fs, sp="10.00GiB", sq="100.00GiB", spp="10.0%", iu="1.00K", iq="1.00M", ipp="0.1%"):
    return {"fs": fs, "space_used": sp, "space_quota": sq, "space_perc": spp,
            "inode_used": iu, "inode_quota": iq, "inode_perc": ipp}


JSON_USER = json.dumps([_q("home"), _q("pscratch")])
JSON_CFS = json.dumps([_q("m5020", sp="2.97TiB", sq="20.00TiB", spp="14.9%")])
JSON_CMN = json.dumps([_q("m5020", sp="88.24GiB", sq="100.00GiB", spp="88.2%",
                          iu="727.37K", ipp="72.7%")])


def test_storage_parses_showquota_json(monkeypatch):
    _mock(monkeypatch, storage, {"showquota": (0, JSON_USER, "")})
    res = storage.check_storage()
    assert [r["fs"] for r in res["data"]["quotas"]] == ["home", "pscratch"]
    assert res["data"]["quotas"][0]["space_quota"] == "100.00GiB"


def test_storage_project_and_common_quotas(monkeypatch):
    def fake(argv, timeout=30, stdin_text=None):
        if "--cmn" in argv:
            return 0, JSON_CMN, ""
        if "m5020" in argv:
            return 0, JSON_CFS, ""
        return 0, JSON_USER, ""
    monkeypatch.setattr(storage.slurm, "run", fake)
    monkeypatch.setattr(storage, "user_projects", lambda: ["m5020"])
    monkeypatch.setattr(storage.os.path, "isdir", lambda p: True)
    res = storage.check_storage()
    assert res["data"]["projects"] == ["m5020"]
    assert res["data"]["project_quotas"][0]["fs"] == "m5020"
    gc = res["data"]["global_common"]
    assert gc["root"].startswith("/global/common/software")
    assert gc["quotas"][0]["space_perc"] == "88.2%"
    # 88.2% space is over the 85% threshold -> a near-quota warning fires
    assert any("global common" in w and "88%" in w for w in res["warnings"])


def test_storage_no_cmn_dir_skips_common(monkeypatch):
    def fake(argv, timeout=30, stdin_text=None):
        return (0, JSON_CFS, "") if "m5020" in argv else (0, JSON_USER, "")
    monkeypatch.setattr(storage.slurm, "run", fake)
    monkeypatch.setattr(storage, "user_projects", lambda: ["m5020"])
    monkeypatch.setattr(storage.os.path, "isdir", lambda p: False)
    res = storage.check_storage()
    assert "global_common" not in res["data"]
    assert res["data"]["project_quotas"][0]["fs"] == "m5020"


def test_storage_software_hint_mentions_inodes(monkeypatch):
    _mock(monkeypatch, storage, {"showquota": (0, JSON_USER, "")})
    res = storage.check_storage("software")
    assert any("inode" in h for h in res["hints"])


def test_status_zero_jobs(monkeypatch):
    _mock(monkeypatch, status, {"squeue": (0, "", ""), "sacct": (0, "", "")})
    res = status.nersc_status()
    assert res["ok"] and res["data"]["queued"] == []


def test_status_decodes_reason(monkeypatch):
    line = "1|j|PENDING|QOSMaxJobsPerUserLimit|0:00|1:00|N/A|2026-07-03T00:00:00\n"
    _mock(monkeypatch, status, {"squeue": (0, line, ""), "sacct": (0, "", "")})
    res = status.nersc_status()
    assert "per-user run limit" in res["data"]["queued"][0]["reason_explained"]
