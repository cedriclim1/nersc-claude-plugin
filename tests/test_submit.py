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
    res = submit.submit_job(script_body="#!/bin/bash\n#SBATCH --qos=debug\n#SBATCH --time=5\n#SBATCH --account=m1\nsrun hostname\n", dry_run=True)
    assert not res["ok"] and "--constraint" in res["error"]["message"]


def test_spec_and_script_mutually_exclusive():
    assert not submit.submit_job(spec=GPU_SPEC, script_body="x")["ok"]
    assert not submit.submit_job()["ok"]


def test_real_submit_parses_jobid(monkeypatch):
    monkeypatch.setattr(submit.slurm, "run",
                        lambda argv, timeout=30, stdin_text=None: (0, "Submitted batch job 55123\n", ""))
    res = submit.submit_job(spec=GPU_SPEC)
    assert res["ok"] and res["data"]["jobid"] == "55123"
