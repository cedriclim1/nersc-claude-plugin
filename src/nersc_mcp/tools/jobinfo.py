"""job_status — squeue+sacct merge with decoded states (DESIGN.md §4.3)."""

from __future__ import annotations

from .. import knowledge, slurm
from ..util import err, result

_SQUEUE_FMT = "%i|%j|%T|%r|%M|%l|%S|%V"


def job_status(jobid: str) -> dict:
    jobid = str(jobid).strip()
    if not jobid.replace("_", "").replace(".", "").isdigit():
        return err("bad_args", f"jobid must be numeric, got {jobid!r}")

    rc, out, _ = slurm.run(["squeue", "-j", jobid, "--noheader", "-o", _SQUEUE_FMT])
    live = slurm.parse_squeue_table(out) if rc == 0 else []

    if live:
        job = live[0]
        state = job["state"]
        reason = job["reason"]
        explained = knowledge.REASONS.get(
            reason, f"state {state}" + (f", reason {reason}" if reason and reason != "None" else ""))
        return result(True, {
            "jobid": jobid, "phase": "queued/running", "state": state,
            "state_explained": explained, "reason": reason,
            "elapsed": job["elapsed"], "time_limit": job["time_limit"],
            "start_estimate": job["start_estimate"],
        })

    rc, out, errtxt = slurm.run([
        "sacct", "-j", jobid, "-X", "-P",
        "-o", "JobID,JobName,State,ExitCode,Elapsed,Timelimit,Reason"])
    if rc != 0:
        return err("sacct_failed", errtxt.strip() or "sacct failed", errtxt)
    rows = slurm.parse_sacct_table(out)
    if not rows:
        return err("not_found", f"no job {jobid} in squeue or recent sacct history")
    row = rows[0]
    state = row.get("state", "UNKNOWN")
    explained = {
        "COMPLETED": "finished successfully",
        "FAILED": "exited nonzero — run job_postmortem for classification",
        "TIMEOUT": "hit its time limit — request more time or checkpoint",
        "OUT_OF_MEMORY": "killed by the OOM handler — run job_postmortem",
        "CANCELLED": "cancelled (by user or admin)",
        "NODE_FAIL": "node failure — resubmit is usually safe",
    }.get(state.split()[0], f"finished in state {state}")
    return result(True, {
        "jobid": jobid, "phase": "finished", "state": state,
        "state_explained": explained, "exit_code": row.get("exitcode"),
        "elapsed": row.get("elapsed"), "time_limit": row.get("timelimit"),
    })
