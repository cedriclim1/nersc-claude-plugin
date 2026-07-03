"""FastMCP app — tool registrations ONLY, no logic (DESIGN.md §3).

Run on a Perlmutter login node:  nersc-mcp   (or: python -m nersc_mcp.server)
Transport: stdio.
"""

from __future__ import annotations

import json
from typing import Optional

from mcp.server.fastmcp import FastMCP

from .tools.allocate import allocate_interactive as _allocate
from .tools.cancel import cancel_job as _cancel
from .tools.context import get_job_context as _context, save_job_profile as _save_profile
from .tools.jobinfo import job_status as _job_status
from .tools.postmortem import job_postmortem as _postmortem
from .tools.queue_advise import queue_advise as _queue_advise
from .tools.queue_wait import queue_wait_stats as _queue_wait_stats
from .tools.status import nersc_status as _status
from .tools.storage import check_storage as _storage
from .tools.submit import SubmitSpec, submit_job as _submit

app = FastMCP("nersc")


def _j(payload: dict) -> str:
    return json.dumps(payload, indent=2)


@app.tool()
def nersc_status() -> str:
    """Your SLURM queue on Perlmutter: queued/running jobs with decoded reason codes, plus the last 24 h of completions. Read-only."""
    return _j(_status())


@app.tool()
def submit_job(spec: Optional[SubmitSpec] = None, script_body: Optional[str] = None,
               dry_run: bool = False) -> str:
    """Build and submit a validated sbatch job. Pass spec={nodes,time,constraint:'cpu'|'gpu',qos,account,command,gpus?,ntasks_per_node?,cpus_per_task?,gpu_bind?,env_lines?,script_path?,job_name?} to have the script generated with all mandatory flags and known-good GPU env exports, or script_body to validate+submit your own. dry_run=true returns the exact script without submitting — use it to review first."""
    return _j(_submit(spec=spec, script_body=script_body, dry_run=dry_run))


@app.tool()
def job_status(jobid: str) -> str:
    """State of one job (queued, running, or finished) with the reason code decoded into plain English and a start estimate when pending."""
    return _j(_job_status(jobid))


@app.tool()
def job_postmortem(jobid: str) -> str:
    """Classify why a finished job died: oom | time_limit | node_fail | cancelled | quota | script_error | unknown, each with a concrete fix hint."""
    return _j(_postmortem(jobid))


@app.tool()
def cancel_job(jobid: str, confirm: bool = False, force: bool = False) -> str:
    """Cancel a job. Requires confirm=true. Refuses PENDING jobs older than 60 min unless force=true — queue age accrues scheduler priority and cancelling discards it."""
    return _j(_cancel(jobid, confirm=confirm, force=force))


@app.tool()
def queue_advise(nodes: int, time_minutes: int, gpus: int = 0,
                 interactive: bool = False) -> str:
    """Recommend the right QOS for a job shape and estimate its node-hour charge, with warnings about QOS limits, discounts, and cheaper alternatives."""
    return _j(_queue_advise(nodes, time_minutes, gpus=gpus, interactive=interactive))


@app.tool()
def queue_wait_stats(constraint: str, qos: str, hours: float, nodes: int = 1,
                     window_days: int = 30) -> str:
    """Forecast queue wait for a Perlmutter job shape using Iris queue-wait history: returns long-term and previous-day stats plus a plain recommendation. Advice only; failures are structured and should not block submission."""
    return _j(_queue_wait_stats(constraint, qos, hours, nodes=nodes, window_days=window_days))


@app.tool()
def allocate_interactive(account: str, nodes: int = 1, time: str = "04:00:00",
                         constraint: str = "gpu") -> str:
    """Create a persistent interactive allocation (salloc --no-shell) and return the exact `SLURM_JOB_ID=<JID> srun --jobid=<JID>` pattern to use it from stateless agent shells."""
    return _j(_allocate(account, nodes=nodes, time=time, constraint=constraint))


@app.tool()
def check_storage(need: str = "") -> str:
    """Show filesystem quotas and, given need = software | job_io | shared_data | archive, say exactly where that data belongs and which gotchas apply (scratch purge, flock-on-CFS, quota-rejects-jobs)."""
    return _j(_storage(need))


@app.tool()
def get_job_context(script_path: str) -> str:
    """Report accounts, remembered profile/defaults, recent history joined to live sacct state, current hash safety flags, and available cudatoolkit module versions for a script. This tool never auto-applies an account; the agent must confirm account/profile choices with the user."""
    return _j(_context(script_path))


@app.tool()
def save_job_profile(script_path: str, profile: dict,
                     set_default_account: bool = False) -> str:
    """Save the user-confirmed submit profile for a script path, optionally remembering profile.account as the session/user default account."""
    return _j(_save_profile(script_path, profile, set_default_account=set_default_account))


def main() -> None:
    app.run()


if __name__ == "__main__":
    main()
