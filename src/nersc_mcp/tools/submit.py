"""submit_job — build/validate/submit sbatch scripts (DESIGN.md §4.2, invariant I3).

Encodes: constraint/qos/time/nodes/account are ALWAYS explicit (constraint has no
SLURM default and debug-QOS is the silent fallback — wiki: slurm-jobs, qos-policy);
GPU jobs always carry an explicit GPU request (the `no CUDA-capable device` trap).
"""

from __future__ import annotations

import re
from typing import Optional

from .. import knowledge, slurm
from ..util import err, result

REQUIRED = ("nodes", "time", "constraint", "qos", "account")
_TIME_RE = re.compile(r"^(\d+:)?\d{1,2}:\d{2}(:\d{2})?$|^\d+$")


def build_script(spec: dict) -> tuple:
    """Returns (script_text, warnings, hints) or raises ValueError with the missing field."""
    missing = [k for k in REQUIRED if not spec.get(k)]
    if missing:
        raise ValueError(f"missing required field(s): {', '.join(missing)}")
    constraint = str(spec["constraint"])
    if constraint not in knowledge.NODES:
        raise ValueError(f"constraint must be one of {sorted(knowledge.NODES)}, got {constraint!r}")
    qos = str(spec["qos"])
    if qos not in knowledge.QOS:
        raise ValueError(f"unknown qos {qos!r}; known: {sorted(knowledge.QOS)}")
    if not _TIME_RE.match(str(spec["time"])):
        raise ValueError("time must look like MM, HH:MM or HH:MM:SS")

    warnings, hints = [], []
    gpus = int(spec.get("gpus") or 0)
    if constraint == "gpu" and gpus <= 0:
        gpus = 4 * int(spec["nodes"])
        warnings.append(
            "constraint=gpu with no gpus requested — defaulted to 4/node; "
            "srun on GPU nodes without an explicit GPU request fails with "
            "'no CUDA-capable device is detected'")

    lines = ["#!/bin/bash"]
    if spec.get("job_name"):
        lines.append(f"#SBATCH --job-name={spec['job_name']}")
    lines += [
        f"#SBATCH --nodes={int(spec['nodes'])}",
        f"#SBATCH --time={spec['time']}",
        f"#SBATCH --constraint={constraint}",
        f"#SBATCH --qos={qos}",
        f"#SBATCH --account={spec['account']}",
    ]
    if gpus:
        lines.append(f"#SBATCH --gpus={gpus}")
    if spec.get("ntasks_per_node"):
        lines.append(f"#SBATCH --ntasks-per-node={int(spec['ntasks_per_node'])}")
    lines.append("")
    if constraint == "gpu":
        for key, val in knowledge.GPU_ENV_EXPORTS.items():
            lines.append(f"export {key}={val}")
        lines.append("")
    command = spec.get("command") or 'echo "no command given"'
    srun = ["srun", "--cpu-bind=cores"]
    if gpus:
        srun.append(f"-G {gpus}")
    lines.append(f"{' '.join(srun)} {command}")
    lines.append("")
    return "\n".join(lines), warnings, hints


def submit_job(spec: Optional[dict] = None, script_body: Optional[str] = None,
               dry_run: bool = False) -> dict:
    if (spec is None) == (script_body is None):
        return err("bad_args", "provide exactly one of spec or script_body")

    warnings: list = []
    hints: list = []
    if spec is not None:
        try:
            script, warnings, hints = build_script(spec)
        except ValueError as exc:
            return err("validation", str(exc))
    else:
        script = script_body
        for flag, name in (("--constraint", "constraint"), ("--qos", "qos"),
                           ("--time", "time"), ("--account", "account")):
            if flag not in script and f"-{name[0].upper()} " not in script:
                return err("validation",
                           f"script is missing {flag} — SLURM has no safe default "
                           f"(constraint omission rejects the job; qos omission silently lands in debug)")

    if dry_run:
        return result(True, {"script": script, "submitted": False},
                      warnings, hints + ["dry_run: nothing was submitted"])

    rc, out, errtxt = slurm.run(["sbatch"], stdin_text=script)
    if rc != 0:
        return err("sbatch_failed", _translate_sbatch_error(errtxt), errtxt)
    m = re.search(r"Submitted batch job (\d+)", out)
    jobid = m.group(1) if m else None
    return result(True, {"jobid": jobid, "script": script, "submitted": True},
                  warnings, hints)


def _translate_sbatch_error(text: str) -> str:
    t = text.lower()
    if "invalid qos" in t:
        return "QOS rejected — check the qos name and whether your account may use it"
    if "quota" in t or "disk" in t:
        return "quota failure — SLURM validates quotas at submission (check_storage can show usage)"
    if "invalid account" in t:
        return "account rejected — pass your project account (e.g. m1234)"
    return text.strip() or "sbatch failed"
