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

# SLURM time: minutes | HH:MM:SS | D-HH | D-HH:MM | D-HH:MM:SS.
# Bare M:S / two-field times are DELIBERATELY rejected: SLURM reads "04:00" as
# 4 minutes (minutes:seconds), the classic silent-TIMEOUT trap.
_TIME_RE = re.compile(r"^(\d+|\d+:\d{2}:\d{2}|\d+-\d{1,2}(:\d{2}(:\d{2})?)?)$")
TIME_FORMAT_MSG = ("time must be minutes (e.g. 30), HH:MM:SS (e.g. 04:00:00), or "
                   "D-HH:MM:SS — bare HH:MM is rejected because SLURM reads it as "
                   "MINUTES:SECONDS ('04:00' = 4 minutes, not 4 hours)")

# script_body validation: (regex, human name). Word-bounded so --time-min does not
# satisfy --time and SLURM's -Q (--quiet) does not satisfy -q (qos).
_SCRIPT_CHECKS = (
    (re.compile(r"(--constraint[=\s]|-C\s)"), "--constraint (no SLURM default; omission rejects the job)"),
    (re.compile(r"(--qos[=\s]|-q\s)"), "--qos (omission silently lands in debug QOS)"),
    (re.compile(r"(--time[=\s]|-t\s)"), "--time"),
    (re.compile(r"(--account[=\s]|-A\s)"), "--account"),
    (re.compile(r"(--nodes[=\s]|-N\s)"), "--nodes (never rely on the default of 1)"),
)
_GPU_CONSTRAINT_RE = re.compile(r"(--constraint[=\s]+\S*gpu|-C\s+\S*gpu)")
_GPU_REQUEST_RE = re.compile(r"(--gpus[=\s-]|-G\s|--gres[=\s]\S*gpu)")


def validate_time(value: str) -> Optional[str]:
    """Returns an error message or None."""
    if not _TIME_RE.match(str(value)):
        return TIME_FORMAT_MSG
    return None


def build_script(spec: dict) -> tuple:
    """Returns (script_text, warnings, hints) or raises ValueError with the problem."""
    missing = [k for k in REQUIRED if not spec.get(k)]
    if missing:
        raise ValueError(f"missing required field(s): {', '.join(missing)}")
    constraint = str(spec["constraint"])
    if constraint not in knowledge.NODES:
        raise ValueError(f"constraint must be one of {sorted(knowledge.NODES)}, got {constraint!r}")
    qos = str(spec["qos"])
    if qos not in knowledge.QOS:
        raise ValueError(f"unknown qos {qos!r}; known: {sorted(knowledge.QOS)}")
    time_error = validate_time(spec["time"])
    if time_error:
        raise ValueError(time_error)

    warnings, hints = [], []
    gpus = int(spec.get("gpus") or 0)
    gpus_per_node = knowledge.NODES["gpu"]["gpus"]
    if constraint == "gpu" and gpus <= 0:
        gpus = gpus_per_node * int(spec["nodes"])
        warnings.append(
            f"constraint=gpu with no gpus requested — defaulted to {gpus_per_node}/node; "
            "srun on GPU nodes without an explicit GPU request fails with "
            "'no CUDA-capable device is detected'")
    if constraint == "cpu" and gpus > 0:
        raise ValueError("gpus requested with constraint=cpu — CPU nodes have no GPUs; "
                         "use constraint='gpu'")

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


def validate_script_body(script: str) -> Optional[str]:
    """Returns an error message or None (I3 for user-supplied scripts)."""
    for pattern, name in _SCRIPT_CHECKS:
        if not pattern.search(script):
            return f"script is missing {name}"
    if _GPU_CONSTRAINT_RE.search(script) and not _GPU_REQUEST_RE.search(script):
        return ("script requests GPU nodes but no GPUs — add --gpus/-G or srun fails "
                "with 'no CUDA-capable device is detected'")
    return None


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
        problem = validate_script_body(script)
        if problem:
            return err("validation", problem)

    if dry_run:
        return result(True, {"script": script, "submitted": False},
                      warnings, hints + ["dry_run: nothing was submitted"])

    rc, out, errtxt = slurm.run(["sbatch"], stdin_text=script)
    if rc != 0:
        return err("sbatch_failed", _translate_sbatch_error(errtxt), errtxt)
    m = re.search(r"Submitted batch job (\d+)", out)
    jobid = m.group(1) if m else None
    if jobid is None:
        warnings.append("sbatch exited 0 but no 'Submitted batch job' line was found — "
                        "check data.raw and squeue")
    return result(True, {"jobid": jobid, "script": script, "submitted": True,
                         "raw": out.strip()}, warnings, hints)


def _translate_sbatch_error(text: str) -> str:
    t = text.lower()
    if "invalid qos" in t:
        return "QOS rejected — check the qos name and whether your account may use it"
    if "quota" in t or "disk" in t:
        return "quota failure — SLURM validates quotas at submission (check_storage can show usage)"
    if "invalid account" in t:
        return "account rejected — pass your project account (e.g. m1234)"
    return text.strip() or "sbatch failed"
