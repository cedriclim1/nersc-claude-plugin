"""get_job_context and save_job_profile (DESIGN.md §4.10-§4.11)."""

from __future__ import annotations

import os
import re
from typing import Dict, Iterable, List

from .. import slurm, store
from ..util import err, result


def _accounts() -> tuple:
    user = os.environ.get("USER") or os.environ.get("LOGNAME") or ""
    rc, out, errtxt = slurm.run(["sacctmgr", "show", "assoc", f"user={user}",
                                 "format=account", "-nP"])
    if rc != 0:
        return [], [f"could not list accounts via sacctmgr: {errtxt.strip() or out.strip()}"]
    accounts = sorted({ln.split("|")[0].strip() for ln in out.splitlines()
                       if ln.split("|")[0].strip()})
    return accounts, []


def parse_cudatoolkit_modules(text: str) -> List[str]:
    versions = set()
    for match in re.finditer(r"(?:^|\s)cudatoolkit/([0-9][A-Za-z0-9._-]*)", text):
        versions.add(match.group(1))
    return sorted(versions, key=lambda v: [int(p) if p.isdigit() else p
                                           for p in re.split(r"([0-9]+)", v)])


def _cudatoolkit_modules() -> tuple:
    rc, out, errtxt = slurm.run(["module", "avail", "cudatoolkit"])
    text = "\n".join([out, errtxt])
    versions = parse_cudatoolkit_modules(text)
    if rc != 0:
        return versions, [f"module avail cudatoolkit failed: {errtxt.strip() or out.strip()}"]
    return versions, []


def parse_sacct_job_states(text: str) -> Dict[str, dict]:
    rows: Dict[str, dict] = {}
    for line in text.splitlines():
        if not line.strip() or line.lower().startswith("jobid|"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 3:
            continue
        jobid = parts[0].split(".")[0]
        if jobid not in rows:
            rows[jobid] = {"state": parts[1], "elapsed": parts[2]}
    return rows


def _join_history(history: List[dict]) -> tuple:
    jobids = [str(h.get("jobid")) for h in history if h.get("jobid")]
    if not jobids:
        return history, []
    rc, out, errtxt = slurm.run(["sacct", "-j", ",".join(jobids), "-o",
                                 "JobID,State,Elapsed", "-nP"])
    if rc != 0:
        return history, [f"could not refresh history with sacct: {errtxt.strip() or out.strip()}"]
    states = parse_sacct_job_states(out)
    joined = []
    for item in history:
        copied = dict(item)
        live = states.get(str(item.get("jobid")))
        if live:
            copied.update(live)
        else:
            copied.setdefault("state", None)
            copied.setdefault("elapsed", None)
        joined.append(copied)
    return joined, []


def history_flags(history: Iterable[dict], current_hash: str) -> dict:
    completed = [h for h in history if h.get("state") == "COMPLETED"]
    has_current_success = any(h.get("content_hash") == current_hash for h in completed)
    has_other_success = any(h.get("content_hash") != current_hash for h in completed)
    return {
        "untested": not has_current_success,
        "changed_since_success": has_other_success and not has_current_success,
    }


def get_job_context(script_path: str) -> dict:
    """Report script submit context; account/profile choices are informational only."""
    warnings: List[str] = []
    path = store.normalize_script_path(script_path)
    state, store_warnings = store.load_state()
    warnings.extend(store_warnings)
    entry = state.get("scripts", {}).get(path, {})
    current_hash, hash_error = store.file_sha256(path)
    if hash_error:
        warnings.append(f"could not hash script_path: {hash_error}")

    accounts, account_warnings = _accounts()
    warnings.extend(account_warnings)
    modules, module_warnings = _cudatoolkit_modules()
    warnings.extend(module_warnings)
    history, history_warnings = _join_history(list(entry.get("history", [])))
    warnings.extend(history_warnings)

    flags = {"untested": True, "changed_since_success": False}
    if current_hash:
        flags = history_flags(history, current_hash)

    return result(True, {
        "script_path": path,
        "content_hash": current_hash,
        "accounts": accounts,
        "default_account": state.get("defaults", {}).get("account"),
        "profile": entry.get("profile"),
        "history": history,
        "untested": flags["untested"],
        "changed_since_success": flags["changed_since_success"],
        "cudatoolkit_modules": modules,
    }, warnings, ["Accounts and stored profiles are reported only; confirm with the user before applying them."])


def save_job_profile(script_path: str, profile: dict,
                     set_default_account: bool = False) -> dict:
    if not isinstance(profile, dict):
        return err("bad_args", "profile must be an object")
    try:
        saved, warnings = store.set_profile(script_path, profile,
                                            set_default_account=set_default_account)
    except OSError as exc:
        return err("store_write_failed", str(exc))
    return result(True, {
        "script_path": store.normalize_script_path(script_path),
        "profile": saved,
    }, warnings, [])
