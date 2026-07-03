"""ACs for submit_job (DESIGN.md §4.2)."""

import pytest

from nersc_mcp.tools import submit


GPU_SPEC = {"nodes": 2, "time": "01:00:00", "constraint": "gpu", "qos": "regular",
            "account": "m5020", "gpus": 8, "command": "python train.py"}


def test_dry_run_gpu_spec_contains_mandatory_flags():
    res = submit.submit_job(spec=GPU_SPEC, dry_run=True)
    assert res["ok"]
    script = res["data"]["script"]
    for needle in ("--constraint=gpu", "--qos=regular", "--time=01:00:00",
                   "--nodes=2", "--account=m5020", "--gpus=8",
                   "--cpu-bind=cores", "-G 8",
                   "PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True"):
        assert needle in script, f"missing {needle}\n{script}"
    assert res["data"]["submitted"] is False


@pytest.mark.parametrize("missing", ["account", "time", "constraint", "qos", "nodes"])
def test_missing_required_field_names_it(missing):
    spec = {k: v for k, v in GPU_SPEC.items() if k != missing}
    res = submit.submit_job(spec=spec, dry_run=True)
    assert not res["ok"]
    assert missing in res["error"]["message"]


def test_gpu_without_gpus_warns_and_defaults():
    spec = {k: v for k, v in GPU_SPEC.items() if k != "gpus"}
    res = submit.submit_job(spec=spec, dry_run=True)
    assert res["ok"]
    assert "--gpus=8" in res["data"]["script"]  # 4 per node * 2 nodes
    assert any("no CUDA-capable device" in w for w in res["warnings"])


def test_unknown_qos_rejected():
    res = submit.submit_job(spec={**GPU_SPEC, "qos": "turbo"}, dry_run=True)
    assert not res["ok"] and "turbo" in res["error"]["message"]


def test_script_body_missing_constraint_rejected():
    res = submit.submit_job(script_body="#!/bin/bash\n#SBATCH --qos=debug\n#SBATCH --time=5\n#SBATCH --nodes=1\n#SBATCH --account=m1\nsrun hostname\n", dry_run=True)
    assert not res["ok"] and "--constraint" in res["error"]["message"]


def test_script_body_short_flags_accepted():
    script = ("#!/bin/bash\n#SBATCH -C cpu\n#SBATCH -q regular\n#SBATCH -t 04:00:00\n"
              "#SBATCH -A m5020\n#SBATCH -N 2\nsrun hostname\n")
    res = submit.submit_job(script_body=script, dry_run=True)
    assert res["ok"], res


def test_script_body_quiet_flag_does_not_satisfy_qos():
    script = ("#!/bin/bash\n#SBATCH -C cpu\n#SBATCH -Q\n#SBATCH -t 04:00:00\n"
              "#SBATCH -A m5020\n#SBATCH -N 2\nsrun hostname\n")
    res = submit.submit_job(script_body=script, dry_run=True)
    assert not res["ok"] and "--qos" in res["error"]["message"]


def test_script_body_time_min_does_not_satisfy_time():
    script = ("#!/bin/bash\n#SBATCH -C cpu\n#SBATCH -q regular\n#SBATCH --time-min=5\n"
              "#SBATCH -A m5020\n#SBATCH -N 2\nsrun hostname\n")
    res = submit.submit_job(script_body=script, dry_run=True)
    assert not res["ok"] and "--time" in res["error"]["message"]


def test_script_body_gpu_without_gpus_rejected():
    script = ("#!/bin/bash\n#SBATCH -C gpu\n#SBATCH -q regular\n#SBATCH -t 04:00:00\n"
              "#SBATCH -A m5020\n#SBATCH -N 1\nsrun hostname\n")
    res = submit.submit_job(script_body=script, dry_run=True)
    assert not res["ok"] and "no CUDA-capable device" in res["error"]["message"]


def test_script_body_missing_nodes_rejected():
    script = ("#!/bin/bash\n#SBATCH -C cpu\n#SBATCH -q regular\n#SBATCH -t 04:00:00\n"
              "#SBATCH -A m5020\nsrun hostname\n")
    res = submit.submit_job(script_body=script, dry_run=True)
    assert not res["ok"] and "--nodes" in res["error"]["message"]


def test_ambiguous_two_field_time_rejected():
    res = submit.submit_job(spec={**GPU_SPEC, "time": "04:00"}, dry_run=True)
    assert not res["ok"] and "MINUTES:SECONDS" in res["error"]["message"]


def test_day_syntax_time_accepted():
    res = submit.submit_job(spec={**GPU_SPEC, "time": "1-12:00:00"}, dry_run=True)
    assert res["ok"], res


def test_cpu_constraint_with_gpus_rejected():
    res = submit.submit_job(spec={**GPU_SPEC, "constraint": "cpu"}, dry_run=True)
    assert not res["ok"] and "no GPUs" in res["error"]["message"]


def test_spec_and_script_mutually_exclusive():
    assert not submit.submit_job(spec=GPU_SPEC, script_body="x")["ok"]
    assert not submit.submit_job()["ok"]


def test_real_submit_parses_jobid(monkeypatch):
    monkeypatch.setattr(submit.slurm, "run",
                        lambda argv, timeout=30, stdin_text=None:
                        (0, "Submitted batch job 55123\n", "") if argv[0] == "sbatch"
                        else (0, "JOBID PARTITION NAME USER ST START_TIME NODES SCHEDNODES NODELIST(REASON)\n55123 regular j u PD 2026-07-03T12:00:00 1 n/a (Priority)\n", ""))
    res = submit.submit_job(spec=GPU_SPEC)
    assert res["ok"] and res["data"]["jobid"] == "55123"
    assert res["data"]["start_estimate"] == "2026-07-03T12:00:00"


def test_spec_env_and_geometry_fields_emit_in_script():
    res = submit.submit_job(spec={**GPU_SPEC, "env_lines": ["export OMP_NUM_THREADS=8"],
                                  "ntasks_per_node": 4, "cpus_per_task": 8,
                                  "gpu_bind": "closest"}, dry_run=True)
    script = res["data"]["script"]
    assert "export OMP_NUM_THREADS=8" in script
    assert "#SBATCH --cpus-per-task=8" in script
    assert "--ntasks-per-node=4" in script
    assert "--cpus-per-task=8" in script
    assert "--gpu-bind=closest" in script


def test_debug_first_warning_triggers_for_script_path(monkeypatch, tmp_path):
    state_path = tmp_path / "state.json"
    monkeypatch.setenv("NERSC_MCP_STATE_PATH", str(state_path))
    monkeypatch.chdir(tmp_path)
    script = tmp_path / "job.sh"
    script.write_text("#!/bin/bash\n")
    res = submit.submit_job(spec={**GPU_SPEC, "script_path": str(script)}, dry_run=True)
    assert any("qos=debug first" in w for w in res["warnings"])


def test_debug_first_warning_not_for_debug(monkeypatch, tmp_path):
    monkeypatch.setenv("NERSC_MCP_STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.chdir(tmp_path)
    script = tmp_path / "job.sh"
    script.write_text("#!/bin/bash\n")
    res = submit.submit_job(spec={**GPU_SPEC, "qos": "debug", "script_path": str(script)}, dry_run=True)
    assert not any("qos=debug first" in w for w in res["warnings"])


def test_storage_warning_for_output_under_home(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    script = ("#!/bin/bash\n#SBATCH -C cpu\n#SBATCH -q debug\n#SBATCH -t 00:05:00\n"
              "#SBATCH -A m5020\n#SBATCH -N 1\n#SBATCH -o ~/out.txt\nsrun hostname\n")
    res = submit.submit_job(script_body=script, dry_run=True)
    assert any("$SCRATCH" in w for w in res["warnings"])


def test_storage_warning_not_for_scratch_output(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.chdir(tmp_path)
    script = ("#!/bin/bash\n#SBATCH -C cpu\n#SBATCH -q debug\n#SBATCH -t 00:05:00\n"
              "#SBATCH -A m5020\n#SBATCH -N 1\n#SBATCH -o /pscratch/sd/u/user/out.txt\nsrun hostname\n")
    res = submit.submit_job(script_body=script, dry_run=True)
    assert not any("$SCRATCH" in w for w in res["warnings"])


def test_history_written_on_success(monkeypatch, tmp_path):
    monkeypatch.setenv("NERSC_MCP_STATE_PATH", str(tmp_path / "state.json"))
    script = tmp_path / "job.sh"
    script.write_text("#!/bin/bash\n")

    def fake_run(argv, timeout=30, stdin_text=None):
        if argv[0] == "sbatch":
            return 0, "Submitted batch job 777\n", ""
        if argv[0] == "sacct":
            return 0, "", ""
        if argv[0] == "squeue":
            return 0, "", ""
        raise AssertionError(argv)

    monkeypatch.setattr(submit.slurm, "run", fake_run)
    res = submit.submit_job(spec={**GPU_SPEC, "qos": "debug", "script_path": str(script)})
    assert res["ok"]
    state, warnings = submit.store.load_state()
    assert not warnings
    hist = state["scripts"][str(script.resolve())]["history"]
    assert hist[-1]["jobid"] == "777"
    assert hist[-1]["qos"] == "debug"
