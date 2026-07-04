import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
HOOKS_JSON = ROOT / "hooks" / "hooks.json"
HOOK_SCRIPT = ROOT / "hooks" / "session-context.sh"


def test_session_start_hook_json_registers_context_command():
    data = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))

    session_entries = data["hooks"]["SessionStart"]
    assert isinstance(session_entries, list)
    assert session_entries

    commands = [
        hook["command"]
        for entry in session_entries
        for hook in entry.get("hooks", [])
        if hook.get("type") == "command"
    ]
    assert commands
    assert any(
        "${CLAUDE_PLUGIN_ROOT}" in command and "session-context.sh" in command
        for command in commands
    )


def test_session_context_script_is_static_and_fast():
    assert HOOK_SCRIPT.exists()
    text = HOOK_SCRIPT.read_text(encoding="utf-8")
    assert text.splitlines()[0] == "#!/bin/sh"

    tokens = set(re.findall(r"[A-Za-z_]+", text.lower()))
    assert not {"curl", "ssh", "python"} & tokens


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not available")
def test_session_context_script_is_tracked_executable():
    result = subprocess.run(
        ["git", "ls-tree", "HEAD", "--", "hooks/session-context.sh"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=5,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("100755"), result.stdout


@pytest.mark.skipif(shutil.which("sh") is None, reason="sh is not available")
def test_session_context_script_outputs_compact_context():
    result = subprocess.run(
        ["sh", str(HOOK_SCRIPT)],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0, result.stderr
    assert len(result.stdout) <= 1200
    assert "check_storage" in result.stdout
    assert "login node" in result.stdout.lower()
