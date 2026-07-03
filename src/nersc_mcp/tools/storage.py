"""check_storage — quotas + placement advice (DESIGN.md §4.8, invariant I7).

Encodes: env/software belongs in /global/common, job I/O in $SCRATCH (purged),
shared data in CFS where flock() silently fails (wiki: filesystems,
friction-points §4).
"""

from __future__ import annotations

import re

from .. import knowledge, slurm
from ..util import err, result

# showquota rows look like:  "home        12.3GiB   40.0GiB   31%   ..." with a
# header line; formats drift, so parse defensively and keep the raw text too.
_QUOTA_ROW_RE = re.compile(
    r"^(?P<fs>\S+)\s+(?P<used>[\d.]+\s*[KMGTP]?i?B?)\s+(?P<limit>[\d.]+\s*[KMGTP]?i?B?)",
    re.IGNORECASE)


def parse_showquota(text: str) -> list:
    """Best-effort structured rows from showquota output (fixture-tested)."""
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.lower().startswith(("filesystem", "----", "usage")):
            continue
        m = _QUOTA_ROW_RE.match(line)
        if m:
            rows.append({"filesystem": m.group("fs"),
                         "used": m.group("used").replace(" ", ""),
                         "limit": m.group("limit").replace(" ", "")})
    return rows


def check_storage(need: str = "") -> dict:
    """need: one of software|job_io|shared_data|archive ('' = just quotas)."""
    warnings, hints = [], []
    data: dict = {}

    rc, out, errtxt = slurm.run(["showquota"])
    if rc == 0:
        data["quotas"] = parse_showquota(out)
        data["raw"] = out.strip()
        if not data["quotas"]:
            warnings.append("showquota output did not match the expected table format — "
                            "see data.raw")
    else:
        warnings.append(f"showquota unavailable ({errtxt.strip() or rc}); quota not checked")

    if need:
        entry = knowledge.PLACEMENT.get(need)
        if entry is None:
            valid = [k for k in knowledge.PLACEMENT if k != "never"]
            return err("bad_args", f"unknown need {need!r}; valid: {valid}")
        path, why = entry
        data["placement"] = {"need": need, "path": path, "why": why}
        if need == "shared_data":
            warnings.append("flock() silently fails on CFS — it returns an error but "
                            "code under set +e proceeds UNLOCKED; use atomic mkdir "
                            "spin-locks for cross-node mutual exclusion")
        if need == "job_io":
            warnings.append("$SCRATCH is purged — copy results to CFS/HPSS promptly")

    hints.append("never point parallel job I/O at $HOME (per-user, not built for it)")
    hints.append("quota is enforced at job submission AND at srun execution — an "
                 "over-quota filesystem rejects your jobs")
    return result(True, data, warnings, hints)
