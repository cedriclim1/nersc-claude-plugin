"""submit_job — build/validate/submit sbatch scripts (DESIGN.md §4.2, invariant I3).

Encodes: constraint/qos/time/nodes/account are ALWAYS explicit (constraint has no
SLURM default and debug-QOS is the silent fallback — wiki: slurm-jobs, qos-policy);
GPU jobs always carry an explicit GPU request (the `no CUDA-capable device` trap).
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, ValidationError

from .. import knowledge, slurm, store
from ..util import err, result
from .context import history_flags, parse_sacct_job_states

REQUIRED = ("nodes", "time", "constraint", "qos", "account")

# Pydantic is declared directly because SubmitSpec is the single source of
# field truth for submit specs and is also part of the MCP validation stack.
class SubmitSpec(BaseModel):
    nodes: int
    time: str
    constraint: str
    qos: str
    account: str
    command: Optional[str] = None
    gpus: Optional[int] = None
    ntasks_per_node: Optional[int] = None
    cpus_per_task: Optional[int] = None
    gpu_bind: Optional[str] = None
    env_lines: Optional[List[str]] = None
    script_path: Optional[str] = None
    job_name: Optional[str] = None


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
    if spec.get("cpus_per_task"):
        lines.append(f"#SBATCH --cpus-per-task={int(spec['cpus_per_task'])}")
    lines.append("")
    if constraint == "gpu":
        for key, val in knowledge.GPU_ENV_EXPORTS.items():
            lines.append(f"export {key}={val}")
        for env_line in spec.get("env_lines") or []:
            lines.append(str(env_line))
        lines.append("")
    command = spec.get("command") or 'echo "no command given"'
    srun = ["srun", "--cpu-bind=cores"]
    if gpus:
        srun.append(f"-G {gpus}")
    if spec.get("ntasks_per_node"):
        srun.append(f"--ntasks-per-node={int(spec['ntasks_per_node'])}")
    if spec.get("cpus_per_task"):
        srun.append(f"--cpus-per-task={int(spec['cpus_per_task'])}")
    if spec.get("gpu_bind"):
        srun.append(f"--gpu-bind={spec['gpu_bind']}")
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


def _spec_dict(spec) -> dict:
    # FastMCP pre-validation of Optional[SubmitSpec] rejects malformed nested
    # fields before submit_job can return the hard-rule-6 / DESIGN I6 envelope.
    # Keep server.py's boundary as Optional[dict], document the schema there,
    # and validate here so failures stay {ok:false, error:{...}}.
    if hasattr(spec, "model_dump"):
        data = spec.model_dump(exclude_none=True)
    elif hasattr(spec, "dict"):
        data = spec.dict(exclude_none=True)
    else:
        data = dict(spec)
    model = SubmitSpec(**data)
    if hasattr(model, "model_dump"):
        return model.model_dump(exclude_none=True)
    return model.dict(exclude_none=True)


def _script_hash_for_body(script: str) -> str:
    import hashlib

    return hashlib.sha256(script.encode("utf-8")).hexdigest()


def _current_hash(script_path: Optional[str], script: str) -> tuple:
    if script_path:
        return store.file_sha256(script_path)
    return _script_hash_for_body(script), None


def _completed_history_for_hash(content_hash: str) -> bool:
    records = store.all_history_for_hash(content_hash)
    if not records:
        return False
    jobids = [str(r["jobid"]) for r in records if r.get("jobid")]
    if not jobids:
        return False
    rc, out, _errtxt = slurm.run(["sacct", "-j", ",".join(jobids), "-o",
                                  "JobID,State,Elapsed", "-nP"])
    if rc != 0:
        return False
    states = parse_sacct_job_states(out)
    return any(states.get(str(r.get("jobid")), {}).get("state") == "COMPLETED"
               for r in records)


def _script_path_flags(script_path: str, content_hash: str) -> tuple:
    state, warnings = store.load_state()
    entry = state.get("scripts", {}).get(store.normalize_script_path(script_path), {})
    hist = list(entry.get("history", []))
    jobids = [str(h.get("jobid")) for h in hist if h.get("jobid")]
    if jobids:
        rc, out, errtxt = slurm.run(["sacct", "-j", ",".join(jobids), "-o",
                                     "JobID,State,Elapsed", "-nP"])
        if rc == 0:
            live = parse_sacct_job_states(out)
            for item in hist:
                if str(item.get("jobid")) in live:
                    item.update(live[str(item.get("jobid"))])
        else:
            warnings.append(f"could not refresh script history: {errtxt.strip() or out.strip()}")
    return history_flags(hist, content_hash), warnings


def _path_under(path: str, root: str) -> bool:
    try:
        p = Path(path).expanduser().resolve()
        r = Path(root).expanduser().resolve()
        return p == r or r in p.parents
    except OSError:
        return str(path).startswith(str(root))


def _output_paths(script: str) -> List[str]:
    paths: List[str] = []
    for line in script.splitlines():
        stripped = line.strip()
        if not stripped.startswith("#SBATCH"):
            continue
        m = re.search(r"(?:--output(?:=|\s+)|-o\s+)(\S+)", stripped)
        if m:
            paths.append(m.group(1))
    return paths


def _storage_warnings(script: str, submit_dir: str) -> List[str]:
    warnings: List[str] = []
    home = str(Path.home())
    risky = []
    for label, path in [("submit directory", submit_dir)]:
        if _path_under(path, home) or _path_under(path, knowledge.CFS_ROOT):
            risky.append(f"{label} {path}")
    for out_path in _output_paths(script):
        expanded = out_path
        if not os.path.isabs(expanded):
            expanded = os.path.join(submit_dir, expanded)
        if _path_under(expanded, home) or _path_under(expanded, knowledge.CFS_ROOT):
            risky.append(f"output path {out_path}")
    if risky:
        warnings.append("Job I/O under $HOME or /global/cfs is a common performance/quota problem; "
                        f"use $SCRATCH for submit/output paths instead ({'; '.join(risky)})")
    return warnings


def _start_estimate(jobid: Optional[str], hints: List[str]) -> Optional[str]:
    if not jobid:
        hints.append("start_estimate unavailable because no jobid was parsed")
        return None
    rc, out, errtxt = slurm.run(["squeue", "--start", "-j", jobid, "-o", "%i|%S", "-h"])
    if rc != 0:
        hints.append(f"squeue --start failed; start estimate unavailable: {errtxt.strip() or out.strip()}")
        return None
    for line in out.splitlines():
        parts = [part.strip() for part in line.split("|", 1)]
        if len(parts) != 2 or parts[0] != jobid:
            continue
        if parts[1] and parts[1].upper() != "N/A":
            return parts[1]
        break
    hints.append("squeue --start returned no estimate for this job")
    return None


def submit_job(spec: Optional[dict] = None, script_body: Optional[str] = None,
               dry_run: bool = False) -> dict:
    if (spec is None) == (script_body is None):
        return err("bad_args", "provide exactly one of spec or script_body")

    warnings: list = []
    hints: list = []
    script_path = None
    spec_data = None
    if spec is not None:
        try:
            spec_data = _spec_dict(spec)
        except ValidationError as exc:
            first = exc.errors()[0] if exc.errors() else {}
            loc = ".".join(str(item) for item in first.get("loc", ())) or "spec"
            msg = first.get("msg", str(exc))
            return err("validation", f"{loc}: {msg}", str(exc))
        script_path = spec_data.get("script_path")
        try:
            script, warnings, hints = build_script(spec_data)
        except ValueError as exc:
            return err("validation", str(exc))
    else:
        script = script_body
        problem = validate_script_body(script)
        if problem:
            return err("validation", problem)

    content_hash, hash_error = _current_hash(script_path, script)
    if hash_error:
        warnings.append(f"could not hash script_path for history checks: {hash_error}")
    if content_hash:
        qos = (spec_data or {}).get("qos") or _extract_sbatch_value(script, "qos", "q")
        if script_path:
            flags, flag_warnings = _script_path_flags(script_path, content_hash)
            warnings.extend(flag_warnings)
            untested = flags["untested"]
        else:
            untested = not _completed_history_for_hash(content_hash)
        if untested and "debug" not in str(qos).lower():
            warning = "This script/content has no COMPLETED history; submit with qos=debug first when feasible before using a longer or larger QOS."
            if spec_data is None and not script_path:
                warning += " (pass spec.script_path instead to enable history tracking so this warning clears after a COMPLETED run)"
            warnings.append(warning)
    submit_dir = str(Path(script_path).expanduser().resolve().parent) if script_path else os.getcwd()
    warnings.extend(_storage_warnings(script, submit_dir))

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
    start_estimate = _start_estimate(jobid, hints)
    if script_path and jobid and content_hash:
        try:
            warnings.extend(store.append_history(script_path, {
                "jobid": jobid,
                "content_hash": content_hash,
                "submitted_at": datetime.now(timezone.utc).isoformat(),
                "qos": (spec_data or {}).get("qos") or _extract_sbatch_value(script, "qos", "q"),
                "constraint": (spec_data or {}).get("constraint") or _extract_sbatch_value(script, "constraint", "C"),
                "nodes": (spec_data or {}).get("nodes") or _extract_sbatch_value(script, "nodes", "N"),
            }))
        except OSError as exc:
            warnings.append(f"job submitted but history could not be saved: {exc}")
    return result(True, {"jobid": jobid, "script": script, "submitted": True,
                         "start_estimate": start_estimate, "raw": out.strip()},
                  warnings, hints)


def _extract_sbatch_value(script: str, long_name: str, short_name: str) -> Optional[str]:
    long_re = re.compile(rf"#SBATCH\s+--{re.escape(long_name)}(?:=|\s+)(\S+)")
    short_re = re.compile(rf"#SBATCH\s+-{re.escape(short_name)}\s+(\S+)")
    for line in script.splitlines():
        m = long_re.search(line) or short_re.search(line)
        if m:
            return m.group(1)
    return None


def _translate_sbatch_error(text: str) -> str:
    t = text.lower()
    if "invalid qos" in t:
        return "QOS rejected — check the qos name and whether your account may use it"
    if "quota" in t or "disk" in t:
        return "quota failure — SLURM validates quotas at submission (check_storage can show usage)"
    if "invalid account" in t:
        return "account rejected — pass your project account (e.g. m1234)"
    return text.strip() or "sbatch failed"
