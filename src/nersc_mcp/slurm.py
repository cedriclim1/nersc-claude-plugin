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
    except subprocess.TimeoutExpired as exc:
        # Preserve partial output — it may contain the only evidence of side
        # effects already in flight (e.g. salloc's job allocation line).
        partial_out = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        partial_err = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return 124, partial_out, f"timeout after {timeout}s: {' '.join(argv)}\n{partial_err}"
    except FileNotFoundError:
        return 127, "", f"command not found: {argv[0]}"
    except OSError as exc:  # pragma: no cover - environment-specific
        return 126, "", f"os error running {argv[0]}: {exc}"


def parse_squeue_table(text: str) -> list:
    """Parse `squeue ... -o '%i|%j|%T|%r|%M|%l|%S|%V' --noheader` pipe-tables.

    Only the name field (%j) can itself contain '|', so the six trailing fields
    are taken from the right and the name is whatever remains in the middle.
    """
    jobs = []
    for line in text.splitlines():
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 8 or not parts[0]:
            continue
        tail = parts[-6:]
        jobs.append({
            "jobid": parts[0], "name": "|".join(parts[1:-6]), "state": tail[0],
            "reason": tail[1], "elapsed": tail[2], "time_limit": tail[3],
            "start_estimate": tail[4], "submitted": tail[5],
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
