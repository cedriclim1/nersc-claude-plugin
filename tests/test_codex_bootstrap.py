import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = ROOT / "bin" / "plugin-bootstrap.sh"


def _write_executable(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)


def _healthy_data(
    path: Path, marker: str = "BOOTSTRAP_OK", root: Path = ROOT
) -> Path:
    bindir = path / "venv" / "bin"
    bindir.mkdir(parents=True)
    _write_executable(bindir / "python3", "#!/bin/sh\nexit 0\n")
    _write_executable(bindir / "pip", "#!/bin/sh\nexit 0\n")
    _write_executable(bindir / "nersc-mcp", f"#!/bin/sh\necho {marker}\n")
    (path / "build-stamp").write_text(
        f"root={root}\npython=/bin/true\n", encoding="utf-8"
    )
    return path


def _run(data_env: dict, home: Path, *args: str) -> subprocess.CompletedProcess:
    env = {
        "PATH": os.environ["PATH"],
        "HOME": str(home),
        "NERSC_MCP_PYTHON": "/bin/true",
        **data_env,
    }
    return subprocess.run(
        ["bash", str(BOOTSTRAP), *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )


def test_codex_root_precedes_claude_root(tmp_path):
    data = _healthy_data(tmp_path / "with spaces" / "data")
    result = _run({
        "PLUGIN_ROOT": str(ROOT),
        "CLAUDE_PLUGIN_ROOT": "/wrong/claude/root",
        "NERSC_MCP_DATA": str(data),
    }, tmp_path)
    assert result.returncode == 0, result.stderr
    assert "BOOTSTRAP_OK" in result.stdout

def test_shared_mcp_checkout_fallback_resolves_git_root_from_subdir(tmp_path):
    data = _healthy_data(tmp_path / "checkout-data", "CHECKOUT_ROOT_OK")
    config = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))
    server = config["mcpServers"]["nersc"]
    env = {
        "PATH": os.environ["PATH"],
        "HOME": str(tmp_path),
        "NERSC_MCP_PYTHON": "/bin/true",
        "NERSC_MCP_DATA": str(data),
    }
    result = subprocess.run(
        [server["command"], *server["args"]],
        cwd=ROOT / "tests",
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "CHECKOUT_ROOT_OK"


def test_data_precedence_explicit_then_codex_then_claude(tmp_path):
    explicit = _healthy_data(tmp_path / "explicit", "SELECTED_EXPLICIT")
    plugin = _healthy_data(tmp_path / "plugin", "SELECTED_CODEX")
    claude = _healthy_data(tmp_path / "claude", "SELECTED_CLAUDE")
    option = _healthy_data(tmp_path / "claude-option", "SELECTED_CLAUDE_OPTION")
    common = {
        "PLUGIN_ROOT": str(ROOT),
        "PLUGIN_DATA": str(plugin),
        "CLAUDE_PLUGIN_DATA": str(claude),
        "CLAUDE_PLUGIN_OPTION_NERSC_DATA_DIR": str(option),
    }
    result = _run({**common, "NERSC_MCP_DATA": str(explicit)}, tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "SELECTED_EXPLICIT"
    result = _run(common, tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "SELECTED_CODEX"
    result = _run({
        "PLUGIN_ROOT": str(ROOT),
        "CLAUDE_PLUGIN_DATA": str(claude),
        "CLAUDE_PLUGIN_OPTION_NERSC_DATA_DIR": str(option),
    }, tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "SELECTED_CLAUDE"
    result = _run({
        "PLUGIN_ROOT": str(ROOT),
        "CLAUDE_PLUGIN_OPTION_NERSC_DATA_DIR": str(option),
    }, tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "SELECTED_CLAUDE_OPTION"


def test_default_data_and_script_relative_root(tmp_path):
    default = _healthy_data(tmp_path / ".local" / "share" / "nersc-mcp")
    result = _run({}, tmp_path)
    assert result.returncode == 0, result.stderr
    assert "BOOTSTRAP_OK" in result.stdout
    assert default.exists()


def test_failed_bootstrap_preserves_manifests_and_user_state(tmp_path):
    state = tmp_path / ".nersc-mcp" / "state.json"
    state.parent.mkdir()
    state.write_text('{"defaults":{"account":"m5020"}}\n', encoding="utf-8")
    data = _healthy_data(tmp_path / "broken-data", "OLD_INSTALL")
    failing_python = tmp_path / "failing-python"
    _write_executable(
        failing_python,
        "#!/bin/sh\n"
        "if [ \"${1:-}\" = \"-c\" ]; then exit 0; fi\n"
        "echo forced-venv-failure >&2\n"
        "exit 7\n",
    )
    before = {
        path: path.read_bytes()
        for path in [
            ROOT / ".mcp.json",
            ROOT / ".codex-plugin" / "plugin.json",
            ROOT / ".claude-plugin" / "plugin.json",
            state,
        ]
    }
    result = _run({
        "PLUGIN_ROOT": str(ROOT),
        "NERSC_MCP_DATA": str(data),
        "NERSC_MCP_PYTHON": str(failing_python),
    }, tmp_path, "--refresh")
    assert result.returncode != 0
    assert "failed to create virtualenv" in result.stderr
    assert "requested --refresh" in result.stderr
    assert str(failing_python) in result.stderr
    for path, content in before.items():
        assert path.read_bytes() == content
    assert not (data / "venv").exists()
    assert (data / "build-stamp").exists()
