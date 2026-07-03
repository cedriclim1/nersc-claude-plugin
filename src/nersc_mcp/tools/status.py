"""nersc_status — read-only snapshot of the user's queue (DESIGN.md §4.1)."""

from __future__ import annotations

from .. import knowledge, slurm
from ..util import err, result

_SQUEUE_FMT = "%i|%j|%T|%r|%M|%l|%S|%V"


def nersc_status() -> dict:
    rc, out, errtxt = slurm.run(["squeue", "--me", "--noheader", "-o", _SQUEUE_FMT])
    if rc != 0:
        return err("squeue_failed", errtxt.strip() or "squeue failed", errtxt)
    jobs = slurm.parse_squeue_table(out)

    warnings, hints = [], []
    for job in jobs:
        decoded = knowledge.REASONS.get(job["reason"])
        if decoded:
            job["reason_explained"] = decoded
        if job["state"] == "PENDING" and job["reason"] == "Priority":
            hints.append(f"job {job['jobid']} is aging in queue — age accrues priority; do not cancel/resubmit")

    rc2, out2, _ = slurm.run([
        "sacct", "--starttime", "now-1days", "-X", "-P",
        "-o", "JobID,JobName,State,ExitCode,Elapsed,Reason"])
    recent = slurm.parse_sacct_table(out2) if rc2 == 0 else []

    return result(True, {"queued": jobs, "recent_24h": recent}, warnings, hints)
