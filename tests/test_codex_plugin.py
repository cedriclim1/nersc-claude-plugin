import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CODEX_MANIFEST = ROOT / ".codex-plugin" / "plugin.json"
CLAUDE_MANIFEST = ROOT / ".claude-plugin" / "plugin.json"
MCP_CONFIG = ROOT / ".mcp.json"
SHARED_HOOKS = ROOT / "hooks" / "hooks.json"
SERVER = ROOT / "src" / "nersc_mcp" / "server.py"


def _registered_tools():
    text = SERVER.read_text(encoding="utf-8")
    return set(re.findall(r"@app\.tool\(\)\s*\ndef\s+([a-z_]+)\(", text))


def test_codex_manifest_has_required_components_and_matching_version():
    codex = json.loads(CODEX_MANIFEST.read_text(encoding="utf-8"))
    claude = json.loads(CLAUDE_MANIFEST.read_text(encoding="utf-8"))
    assert codex["name"] == claude["name"] == "nersc"
    assert codex["version"] == claude["version"] == "0.2.2"
    assert codex["skills"] == "./skills/"
    assert codex["mcpServers"] == "./.mcp.json"
    assert "hooks" not in codex  # default hooks/hooks.json discovery


def test_shared_mcp_is_single_server_and_portable_across_clients():
    config = json.loads(MCP_CONFIG.read_text(encoding="utf-8"))
    assert set(config) == {"mcpServers"}
    config = config["mcpServers"]
    assert set(config) == {"nersc"}
    assert config["nersc"]["command"] == "sh"
    command = config["nersc"]["args"]
    assert command[0] == "-c"
    assert "PLUGIN_ROOT" in command[1]
    assert "CLAUDE_PLUGIN_ROOT" in command[1]
    assert "git rev-parse --show-toplevel" in command[1]
    assert "$PWD" not in command[1]
    assert set(config["nersc"]["env_vars"]) == {
        "NERSC_MCP_PYTHON", "NERSC_MCP_DATA"
    }


def test_claude_has_no_second_inline_mcp_registration():
    claude = json.loads(CLAUDE_MANIFEST.read_text(encoding="utf-8"))
    assert "mcpServers" not in claude
    assert MCP_CONFIG.exists()


def test_shared_hook_uses_both_client_roots_and_checkout_fallback():
    hooks = json.loads(SHARED_HOOKS.read_text(encoding="utf-8"))
    command = hooks["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    assert "${PLUGIN_ROOT" in command
    assert "${CLAUDE_PLUGIN_ROOT" in command
    assert "git rev-parse --show-toplevel" in command
    assert "$PWD" not in command


def test_closed_tool_surface_is_exactly_eleven():
    assert _registered_tools() == {
        "nersc_status", "submit_job", "job_status", "job_postmortem",
        "cancel_job", "queue_advise", "queue_wait_stats",
        "allocate_interactive", "check_storage", "get_job_context",
        "save_job_profile",
    }


def test_codex_docs_and_agents_cover_install_and_safety_contracts():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    for marker in [
        "codex plugin marketplace add", "codex plugin add",
        "codex plugin remove", "codex mcp add", "hook trust",
        "PLUGIN_ROOT", "PLUGIN_DATA", "user data",
    ]:
        assert marker in readme
    for marker in ["I1–I8", "du`, `df`, `find", "Loop", "11-tool"]:
        assert marker in agents
