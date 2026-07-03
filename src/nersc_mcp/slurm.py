"""Subprocess discipline (DESIGN.md §3): list argv, timeout, never shell=True,
never a traceback across the MCP boundary. All SLURM interaction goes through run().
"""

from __future__ import annotations

import subprocess
from typing import Optional, Sequence, Tuple

DEFAULT_TIMEOUT = 30


def run(argv: Sequence[str], timeout: int = DEFAULT_TIMEOUT,
        stdin_text: Optional[str] = None) -> Tuple[int, str, str]:
    """Run a short-lived command. Returns (rc, stdout, stderr); rc=124 on timeout,
    rc=127 if the binary is missing. Never raises."""
    try:
        proc = subprocess.run(
            list(argv), capture_output=True, text=True, timeout=timeout,
            input=stdin_text,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return 124, "", f"timeout after {timeout}s: {' '.join(argv)}"
    except FileNotFoundError:
        return 127, "", f"command not found: {argv[0]}"
    except OSError as exc:  # pragma: no cover - environment-specific
        return 126, "", f"os error running {argv[0]}: {exc}"


def parse_squeue_table(text: str) -> list:
    """Parse `squeue ... -o '%i|%j|%T|%r|%M|%l|%S|%V' --noheader` pipe-tables."""
    jobs = []
    for line in text.splitlines():
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 8 or not parts[0]:
            continue
        jobs.append({
            "jobid": parts[0], "name": parts[1], "state": parts[2],
            "reason": parts[3], "elapsed": parts[4], "time_limit": parts[5],
            "start_estimate": parts[6], "submitted": parts[7],
        })
    return jobs


def parse_sacct_table(text: str) -> list:
    """Parse `sacct -P -o JobID,JobName,State,ExitCode,Elapsed,ReqMem,MaxRSS,Reason` output."""
    rows = []
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return rows
    header = [h.strip() for h in lines[0].split("|")]
    for line in lines[1:]:
        parts = [p.strip() for p in line.split("|")]
        if len(parts) != len(header):
            continue
        rows.append(dict(zip([h.lower() for h in header], parts)))
    return rows
