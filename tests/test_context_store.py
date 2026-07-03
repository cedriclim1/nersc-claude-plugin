import json
import os
from pathlib import Path

import pytest

from nersc_mcp import store
from nersc_mcp.tools import context


SACCT_HISTORY = """\
1|COMPLETED|00:01:00
2|FAILED|00:00:03
3|TIMEOUT|00:30:00
"""


def _state_file(monkeypatch, tmp_path):
    path = tmp_path / "state.json"
    monkeypatch.setenv("NERSC_MCP_STATE_PATH", str(path))
    return path


def _write_state(path, script_path, history):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schema_version": 1,
        "defaults": {"account": "m5020"},
        "scripts": {str(script_path.resolve()): {
            "profile": {"account": "m5020", "qos": "debug"},
            "history": history,
        }},
    }))


def test_parse_cudatoolkit_modules_from_stderr_style_output():
    text = """
---------------- /opt/cray/pe/lmod/modulefiles/core ----------------
cudatoolkit/11.7  cudatoolkit/12.2  cudatoolkit/12.4
"""
    assert context.parse_cudatoolkit_modules(text) == ["11.7", "12.2", "12.4"]


@pytest.mark.parametrize("history,body,expected", [
    ([], "new", {"untested": True, "changed_since_success": False}),
    ([{"jobid": "1", "content_hash": "CURRENT"}], "same",
     {"untested": False, "changed_since_success": False}),
    ([{"jobid": "1", "content_hash": "OLD"}], "same",
     {"untested": True, "changed_since_success": True}),
    ([{"jobid": "2", "content_hash": "CURRENT"}], "same",
     {"untested": True, "changed_since_success": False}),
])
def test_get_job_context_untested_changed_matrix(monkeypatch, tmp_path, history, body, expected):
    state_path = _state_file(monkeypatch, tmp_path)
    script = tmp_path / "job.sh"
    script.write_text(body)
    current_hash, _ = store.file_sha256(str(script))
    for item in history:
        if item["content_hash"] == "CURRENT":
            item["content_hash"] = current_hash
    _write_state(state_path, script, history)

    def fake_run(argv, timeout=30, stdin_text=None):
        if argv[0] == "sacctmgr":
            return 0, "m5020\nm1000\nm5020\n", ""
        if argv[0] == "module":
            return 0, "", "cudatoolkit/12.2 cudatoolkit/12.4\n"
        if argv[0] == "sacct":
            return 0, SACCT_HISTORY, ""
        raise AssertionError(argv)

    monkeypatch.setattr(context.slurm, "run", fake_run)
    res = context.get_job_context(str(script))
    assert res["ok"]
    assert res["data"]["accounts"] == ["m1000", "m5020"]
    assert res["data"]["default_account"] == "m5020"
    assert res["data"]["cudatoolkit_modules"] == ["12.2", "12.4"]
    assert res["data"]["untested"] is expected["untested"]
    assert res["data"]["changed_since_success"] is expected["changed_since_success"]


def test_store_atomic_replace_failure_keeps_original(monkeypatch, tmp_path):
    path = _state_file(monkeypatch, tmp_path)
    original = {"schema_version": 1, "defaults": {"account": "old"}, "scripts": {}}
    path.write_text(json.dumps(original))

    def boom(src, dst):
        assert Path(src).exists()
        raise OSError("crash")

    monkeypatch.setattr(store.os, "replace", boom)
    with pytest.raises(OSError):
        store.save_state({"schema_version": 1, "defaults": {"account": "new"}, "scripts": {}})
    assert json.loads(path.read_text()) == original


def test_corrupt_store_recovery_backs_up_and_warns(monkeypatch, tmp_path):
    path = _state_file(monkeypatch, tmp_path)
    path.write_text("{garbage")
    state, warnings = store.load_state()
    assert state == store.empty_state()
    assert warnings and "backed up" in warnings[0]
    assert path.with_name("state.json.bad").exists()


def test_save_job_profile_sets_default(monkeypatch, tmp_path):
    _state_file(monkeypatch, tmp_path)
    script = tmp_path / "job.sh"
    res = context.save_job_profile(str(script), {"account": "m5020"}, True)
    assert res["ok"]
    state, warnings = store.load_state()
    assert not warnings
    assert state["defaults"]["account"] == "m5020"
    assert state["scripts"][str(script.resolve())]["profile"]["account"] == "m5020"
