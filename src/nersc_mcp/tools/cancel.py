"""cancel_job — guarded scancel (DESIGN.md §4.5, invariants I4+I5).

Queue age accrues SLURM priority: cancelling a long-pending job and resubmitting
sends the work to the back of the line (wiki: friction-points §3, tomo lesson
queue-age-is-priority-never-cancel-aged-jobs). Hence the age guard.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from .. import slurm
from ..util import err, result

AGE_GUARD_MINUTES = 60
_SQUEUE_FMT = "%i|%j|%T|%r|%M|%l|%S|%V"


def _submit_age_minutes(submitted: str, now: datetime):
    """Returns age in minutes, or None when the timestamp is unparseable.

    None makes the guard FAIL CLOSED (refuse to cancel) — a safety guard that
    silently disables itself on a format change is worse than an inconvenience.
    """
    try:
        dt = datetime.fromisoformat(submitted)
    except ValueError:
        return None
    return (now - dt) / timedelta(minutes=1)


def cancel_job(jobid: str, confirm: bool = False, force: bool = False) -> dict:
    jobid = str(jobid).strip()
    if not confirm:
        return err("needs_confirm",
                   f"cancelling job {jobid} is destructive — call again with confirm=true")

    rc, out, errtxt = slurm.run(["squeue", "-j", jobid, "--noheader", "-o", _SQUEUE_FMT])
    if rc != 0:
        return err("squeue_failed", errtxt.strip() or "squeue failed", errtxt)
    jobs = slurm.parse_squeue_table(out)
    if not jobs:
        return err("not_found", f"job {jobid} is not in the queue (already finished?)")
    job = jobs[0]

    if job["state"] == "PENDING" and not force:
        age = _submit_age_minutes(job["submitted"], datetime.now())
        if age is None:
            return err(
                "age_guard",
                f"job {jobid} is PENDING but its submit time {job['submitted']!r} "
                f"could not be parsed, so its queue age is unknown. Queue age accrues "
                f"priority — refusing to cancel blind. Pass force=true to override.")
        if age > AGE_GUARD_MINUTES:
            return err(
                "age_guard",
                f"job {jobid} has been PENDING for ~{age:.0f} min. Queue age accrues "
                f"priority — cancelling discards that and a resubmission starts at the "
                f"back. If you must trim the queue, cancel your YOUNGEST pending jobs "
                f"instead. Pass force=true to override.")

    rc, out, errtxt = slurm.run(["scancel", jobid])
    if rc != 0:
        return err("scancel_failed", errtxt.strip() or "scancel failed", errtxt)
    return result(True, {"jobid": jobid, "cancelled": True, "was_state": job["state"]})
