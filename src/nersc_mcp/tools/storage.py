"""check_storage — quotas + placement advice (DESIGN.md §4.8, invariant I7).

Encodes: env/software belongs in /global/common, job I/O in $SCRATCH (purged),
shared data in CFS where flock() silently fails (wiki: filesystems,
friction-points §4).

Quota source is `showquota -J` (JSON), with a plain-showquota retry and the
legacy table parse as fallbacks. Projects are positional args (multiple OK),
`-N` suppresses the implicit home/scratch rows, `--cmn` switches to
/global/common/software quotas — all verified by live capture on Perlmutter
2026-07-04 (wiki: filesystems). NM-36 adds the project + global-common context
because conda envs and shared software live in project space, not under the
user's home/scratch.
"""

from __future__ import annotations

import json
import os
import re

from .. import knowledge, slurm
from ..util import err, result

try:  # POSIX-only; absent on dev boxes — tests monkeypatch user_projects()
    import grp
except ImportError:  # pragma: no cover - non-POSIX dev machine
    grp = None

# showquota rows look like:  "home        12.3GiB   40.0GiB   31%   ..." with a
# header line; formats drift, so parse defensively and keep the raw text too.
_QUOTA_ROW_RE = re.compile(
    r"^(?P<fs>\S+)\s+(?P<used>[\d.]+\s*[KMGTP]?i?B?)\s+(?P<limit>[\d.]+\s*[KMGTP]?i?B?)",
    re.IGNORECASE)


def parse_showquota(text: str) -> list:
    """Best-effort structured rows from showquota table output (fixture-tested)."""
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


def parse_showquota_json(text: str) -> list:
    """Rows from `showquota -J`: [{fs, space_used, space_quota, space_perc,
    inode_used, inode_quota, inode_perc}] (live capture 2026-07-04)."""
    try:
        rows = json.loads(text)
    except ValueError:
        return []
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict) and r.get("fs")]


def _percent(value) -> float:
    """'88.2%' -> 88.2; unparseable -> -1 (never warns)."""
    try:
        return float(str(value).rstrip("%"))
    except ValueError:
        return -1.0


def user_projects() -> list:
    """Project names = the user's unix groups that own a CFS project dir.
    Includes the primary gid — os.getgroups() may omit it on some systems.
    Runs on the login node, so the dir check is a direct stat (no compute,
    no subprocess). Empty on non-POSIX dev machines."""
    if grp is None:
        return []
    names = []
    for gid in set(os.getgroups()) | {os.getgid()}:
        try:
            name = grp.getgrgid(gid).gr_name
        except KeyError:
            continue
        if os.path.isdir(os.path.join(knowledge.CFS_CDIRS, name)):
            names.append(name)
    return sorted(set(names))


def _parse_any(out: str) -> list:
    rows = parse_showquota_json(out)
    if not rows:
        rows = [{"fs": r["filesystem"], "space_used": r["used"],
                 "space_quota": r["limit"]} for r in parse_showquota(out)]
    return rows


def _quota_rows(argv: list, warnings: list, label: str, raw: dict) -> list:
    """Run one showquota variant. Prefers JSON; retries without -J if the
    installed showquota rejects the flag; falls back to the table parse,
    normalized to the JSON keys. Raw text is kept under data.raw[label].

    showquota's exit code is the COUNT of filesystems over quota, not an
    error status (live capture 2026-07-04: rc=1 with valid JSON when one
    project's common space sat at 105%) — so judge by parseable output,
    never by rc alone."""
    rc, out, errtxt = slurm.run(argv)
    rows = _parse_any(out)
    if not rows and rc != 0 and "-J" in argv:
        rc, out, errtxt = slurm.run([a for a in argv if a != "-J"])
        rows = _parse_any(out)
    if not rows:
        if out.strip():
            raw[label] = out.strip()
            warnings.append(f"{label} output did not match the JSON or table "
                            f"format — see data.raw['{label}']")
        else:
            warnings.append(f"{label} unavailable ({errtxt.strip() or rc}); "
                            "not checked")
        return []
    raw[label] = out.strip()
    return rows


def _warn_near_quota(rows: list, warnings: list, where: str = "") -> None:
    for r in rows:
        for kind, perc in (("space", r.get("space_perc")),
                           ("inodes", r.get("inode_perc"))):
            pct = _percent(perc)
            if pct >= knowledge.QUOTA_WARN_PERCENT:
                warnings.append(f"{where}{r['fs']} is at {pct:.0f}% of its "
                                f"{kind} quota — {knowledge.QUOTA_ENFORCEMENT}")


def check_storage(need: str = "") -> dict:
    """need: one of software|job_io|shared_data|archive ('' = just quotas)."""
    warnings, hints = [], []
    raw: dict = {}
    data: dict = {"raw": raw}

    data["quotas"] = _quota_rows(["showquota", "-J"], warnings, "user", raw)
    _warn_near_quota(data["quotas"], warnings)

    # Project-level context (NM-36): CFS project quotas + /global/common
    # software dirs — where conda envs / shared stacks actually live.
    # HPSS quotas (--hpss) deferred; see DESIGN.md §4.8.
    projects = user_projects()
    if projects:
        data["projects"] = projects
        cfs_rows = _quota_rows(["showquota", "-J", "-N"] + projects,
                               warnings, "cfs", raw)
        if cfs_rows:
            data["project_quotas"] = cfs_rows
            _warn_near_quota(cfs_rows, warnings, "CFS ")

        common = [p for p in projects
                  if os.path.isdir(os.path.join(knowledge.GLOBAL_COMMON_ROOT, p))]
        if common:
            cmn_rows = _quota_rows(["showquota", "-J", "-N", "--cmn"] + common,
                                   warnings, "cmn", raw)
            if cmn_rows:
                data["global_common"] = {
                    "root": knowledge.GLOBAL_COMMON_ROOT,
                    "projects": common,
                    "quotas": cmn_rows,
                    "facts": knowledge.GLOBAL_COMMON_FACTS,
                }
                _warn_near_quota(cmn_rows, warnings, "global common ")

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
        if need == "software":
            hints.append("/global/common is writable from login nodes only and its "
                         "quota is small in BOTH space and inodes — conda envs are "
                         "inode-heavy; check data.global_common before installing")

    hints.append("never point parallel job I/O at $HOME (per-user, not built for it)")
    hints.append(knowledge.QUOTA_ENFORCEMENT)
    return result(True, data, warnings, hints)
