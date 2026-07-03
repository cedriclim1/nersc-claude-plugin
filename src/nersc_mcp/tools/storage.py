"""check_storage — quotas + placement advice (DESIGN.md §4.8, invariant I7).

Encodes: env/software belongs in /global/common, job I/O in $SCRATCH (purged),
shared data in CFS where flock() silently fails (wiki: filesystems,
friction-points §4).
"""

from __future__ import annotations

from .. import knowledge, slurm
from ..util import result


def check_storage(need: str = "") -> dict:
    """need: one of software|job_io|shared_data|archive ('' = just quotas)."""
    warnings, hints = [], []
    data: dict = {}

    rc, out, errtxt = slurm.run(["showquota"])
    if rc == 0:
        data["quota_raw"] = out.strip()
    else:
        warnings.append(f"showquota unavailable ({errtxt.strip() or rc}); quota not checked")

    if need:
        entry = knowledge.PLACEMENT.get(need)
        if entry is None:
            valid = [k for k in knowledge.PLACEMENT if k != "never"]
            return result(False, None,
                          warnings=[f"unknown need {need!r}; valid: {valid}"])
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
