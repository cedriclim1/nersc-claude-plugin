"""job_postmortem — classify why a job died (DESIGN.md §4.4).

Encodes the failure-text diagnosis the tomo transcripts show being done by hand
(wiki: friction-points §6). Classifier is pure so it can be fixture-tested.
"""

from __future__ import annotations

from .. import slurm
from ..util import err, result

CATEGORIES = ("oom", "time_limit", "node_fail", "cancelled", "quota", "script_error", "unknown")

_HINTS = {
    "oom": ("reduce per-task memory, request more nodes, or lower batch size; "
            "GPU nodes have ~150 GB usable GPU / ~246 GB CPU RAM, CPU nodes ~502 GB"),
    "time_limit": "request more --time (check queue_advise for QOS ceilings) or add checkpointing",
    "node_fail": "hardware fault — resubmitting the same script is usually safe",
    "cancelled": "cancelled by user/admin; if you cancelled an aged PENDING job, note that queue age = priority",
    "quota": "a filesystem is over quota — SLURM enforces quotas at submit AND srun; run check_storage",
    "script_error": "the script itself exited nonzero — check the .out/.err files; validate with submit_job(dry_run=True)",
    "unknown": "unclassified — read data.rows raw output; consider asking NERSC support",
}


def classify(rows: list) -> str:
    """Pure classifier over parsed sacct rows (fixture-tested)."""
    states = " ".join(r.get("state", "") for r in rows).upper()
    exits = " ".join(r.get("exitcode", "") for r in rows)
    if "OUT_OF_MEMORY" in states or "0:125" in exits:
        return "oom"
    if "TIMEOUT" in states:
        return "time_limit"
    if "NODE_FAIL" in states:
        return "node_fail"
    if "CANCELLED" in states:
        return "cancelled"
    reasons = " ".join(r.get("reason", "") for r in rows).lower()
    if "quota" in reasons or "disk" in reasons:
        return "quota"
    if "FAILED" in states:
        return "script_error"
    return "unknown"


def job_postmortem(jobid: str) -> dict:
    jobid = str(jobid).strip()
    rc, out, errtxt = slurm.run([
        "sacct", "-j", jobid, "-P",
        "-o", "JobID,JobName,State,ExitCode,DerivedExitCode,Elapsed,Timelimit,ReqMem,MaxRSS,Reason,NodeList"])
    if rc != 0:
        return err("sacct_failed", errtxt.strip() or "sacct failed", errtxt)
    rows = slurm.parse_sacct_table(out)
    if not rows:
        return err("not_found", f"no accounting rows for job {jobid}")
    category = classify(rows)
    return result(True, {
        "jobid": jobid, "category": category, "fix_hint": _HINTS[category],
        "rows": rows,
    }, hints=[_HINTS[category]])
