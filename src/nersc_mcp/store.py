"""Local state store for submit-job UX.

The store lives under $HOME, never CFS, so flock-on-CFS concerns do not apply.
Concurrency is intentionally last-writer-wins; there are no locks or background
coordination threads, preserving DESIGN.md I2/I7.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCHEMA_VERSION = 1
HISTORY_LIMIT = 20


def state_path() -> Path:
    override = os.environ.get("NERSC_MCP_STATE_PATH")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".nersc-mcp" / "state.json"


def empty_state() -> dict:
    return {"schema_version": SCHEMA_VERSION, "defaults": {}, "scripts": {}}


def normalize_script_path(script_path: str) -> str:
    return str(Path(script_path).expanduser().resolve())


def load_state(path: Optional[Path] = None) -> Tuple[dict, List[str]]:
    path = path or state_path()
    if not path.exists():
        return empty_state(), []
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        warning = f"state store was corrupt/unreadable and has been backed up to {path.with_name('state.json.bad')}: {exc}"
        try:
            path.replace(path.with_name("state.json.bad"))
        except OSError as backup_exc:
            warning += f" (backup failed: {backup_exc})"
        return empty_state(), [warning]
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
        return empty_state(), [f"state store schema was not version {SCHEMA_VERSION}; treated as empty"]
    data.setdefault("defaults", {})
    data.setdefault("scripts", {})
    if not isinstance(data["defaults"], dict):
        data["defaults"] = {}
    if not isinstance(data["scripts"], dict):
        data["scripts"] = {}
    return data, []


def save_state(state: dict, path: Optional[Path] = None) -> None:
    path = path or state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    for entry in state.get("scripts", {}).values():
        hist = entry.get("history", [])
        if isinstance(hist, list) and len(hist) > HISTORY_LIMIT:
            entry["history"] = hist[-HISTORY_LIMIT:]
    fd, tmp_name = tempfile.mkstemp(prefix="state.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def get_script_entry(state: dict, script_path: str) -> dict:
    return state.get("scripts", {}).get(normalize_script_path(script_path), {})


def set_profile(script_path: str, profile: Dict[str, Any],
                set_default_account: bool = False) -> Tuple[dict, List[str]]:
    state, warnings = load_state()
    key = normalize_script_path(script_path)
    scripts = state.setdefault("scripts", {})
    entry = scripts.setdefault(key, {})
    entry["profile"] = dict(profile)
    entry.setdefault("history", [])
    if set_default_account and profile.get("account"):
        state.setdefault("defaults", {})["account"] = profile["account"]
    save_state(state)
    return entry["profile"], warnings


def append_history(script_path: str, record: Dict[str, Any]) -> List[str]:
    state, warnings = load_state()
    key = normalize_script_path(script_path)
    entry = state.setdefault("scripts", {}).setdefault(key, {})
    hist = entry.setdefault("history", [])
    hist.append(dict(record))
    entry["history"] = hist[-HISTORY_LIMIT:]
    save_state(state)
    return warnings


def all_history_for_hash(content_hash: str) -> List[dict]:
    state, _warnings = load_state()
    matches: List[dict] = []
    for script_path, entry in state.get("scripts", {}).items():
        for item in entry.get("history", []):
            if item.get("content_hash") == content_hash:
                copied = dict(item)
                copied["script_path"] = script_path
                matches.append(copied)
    return matches


def file_sha256(script_path: str) -> Tuple[Optional[str], Optional[str]]:
    import hashlib

    try:
        data = Path(script_path).expanduser().resolve().read_bytes()
    except OSError as exc:
        return None, str(exc)
    return hashlib.sha256(data).hexdigest(), None
