"""allocate_interactive — salloc --no-shell + the srun --jobid pattern (DESIGN.md §4.7).

Agent shells do not persist env between tool calls, so `salloc` into a shell or
`export SLURM_JOB_ID` is useless. The working pattern (wiki: friction-points §2,
s-tomo-runbook): allocate with --no-shell, then target the allocation explicitly
on every call.
"""

from __future__ import annotations

import re

from .. import slurm
from ..util import err, result
from .submit import validate_time

_GRANTED_RE = re.compile(r"Granted job allocation (\d+)")
_PENDING_RE = re.compile(r"job allocation (\d+)")


def allocate_interactive(account: str, nodes: int = 1, time: str = "04:00:00",
                         constraint: str = "gpu") -> dict:
    if constraint not in ("gpu", "cpu"):
        return err("bad_args", "constraint must be 'gpu' or 'cpu'")
    if not account:
        return err("bad_args", "account is required (e.g. m1234)")
    time_error = validate_time(time)
    if time_error:
        return err("validation", time_error)

    rc, out, errtxt = slurm.run(
        ["salloc", "-A", account, "-C", constraint, "-q", "interactive",
         "-t", str(time), "-N", str(int(nodes)), "--no-shell"],
        timeout=180)
    text = out + "\n" + errtxt
    m = _GRANTED_RE.search(text)

    if rc == 124 and not m:
        # Timeout: salloc was killed, but a PENDING allocation request may still be
        # granted later and charge while idle. Surface any JID we saw and clean up.
        pending = _PENDING_RE.search(text)
        if pending:
            jid = pending.group(1)
            slurm.run(["scancel", jid])
            return err("salloc_timeout",
                       f"salloc timed out; pending allocation {jid} was cancelled to "
                       f"avoid an orphaned (idle, charging) allocation. Retry when the "
                       f"queue is quieter.", text)
        return err("salloc_timeout",
                   "salloc timed out before printing a job allocation line. Check "
                   "`squeue --me` for an orphaned interactive allocation and scancel "
                   "it if present.", text)

    if rc != 0 and not m:
        return err("salloc_failed", text.strip() or "salloc failed", text)
    if not m:
        return err("parse", "salloc returned but no 'Granted job allocation' line", text)
    jid = m.group(1)
    pattern = f"SLURM_JOB_ID={jid} srun --jobid={jid} <your command>"
    return result(True, {
        "jobid": jid,
        "usage_pattern": pattern,
        "release_with": f"scancel {jid}",
    }, hints=[
        f"the allocation persists across tool calls; run work with: {pattern}",
        "your shell does NOT inherit SLURM_JOB_ID — always pass --jobid explicitly",
        "release the allocation when done (cancel_job with confirm) — it charges while idle",
    ])
