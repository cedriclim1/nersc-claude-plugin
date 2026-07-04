import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "nersc" / "SKILL.md"
SERVER = ROOT / "src" / "nersc_mcp" / "server.py"

REQUIRED_MARKERS = [
    "submit anyway",
    "fatal",
    "likely-waste",
    "cosmetic",
    "debug timing run",
    "pre-submit summary",
]

REQUIRED_TOOLS = [
    "submit_job",
    "get_job_context",
    "save_job_profile",
    "queue_wait_stats",
    "job_status",
    "job_postmortem",
    "check_storage",
    "queue_advise",
]


def _skill_text():
    return SKILL.read_text(encoding="utf-8")


def _frontmatter(text):
    assert text.startswith("---\n")
    end = text.find("\n---\n", 4)
    assert end != -1
    fields = {}
    current = None
    for line in text[4:end].splitlines():
        if not line.strip():
            continue
        if not line.startswith(" ") and ":" in line:
            key, value = line.split(":", 1)
            current = key.strip()
            fields[current] = value.strip()
        elif current:
            fields[current] = (fields[current] + " " + line.strip()).strip()
    return fields


def _registered_tools():
    server = SERVER.read_text(encoding="utf-8")
    return set(re.findall(r"@app\.tool\(\)\s*\ndef\s+([a-z_]+)\(", server))


def test_skill_frontmatter_has_name_and_description():
    fields = _frontmatter(_skill_text())
    assert fields["name"] == "nersc"
    assert fields["description"]


def test_skill_contains_required_marker_strings():
    text = _skill_text()
    for marker in REQUIRED_MARKERS:
        assert marker in text


def test_required_tool_mentions_are_registered_and_present():
    text = _skill_text()
    registered = _registered_tools()
    assert set(REQUIRED_TOOLS) <= registered
    for tool in REQUIRED_TOOLS:
        assert re.search(rf"\b{re.escape(tool)}\b", text), f"missing {tool}"


def test_skill_arms_tools_first_before_composition_guidance():
    text = _skill_text()
    intro = (
        "Use this skill whenever the user wants to run, submit, monitor, or debug work "
        "on NERSC\nPerlmutter.\n\n"
    )
    assert intro + "## Arm the tools first" in text
    assert text.index("## Arm the tools first") < text.index("## Tool Composition Basics")

    section = text.split("## Arm the tools first", 1)[1].split("## Tool Composition Basics", 1)[0]
    assert "Before ANY other action on ANY /nersc request" in section
    assert "ONE batched ToolSearch call" in section
    assert "FULLY-QUALIFIED tool names" in section
    assert "NEVER use bare\nnames like `check_storage`" in section
    assert "A second ToolSearch round-trip is a bug" in section
    for tool in _registered_tools():
        assert f"mcp__plugin_nersc_nersc__{tool}" in section


def test_skill_bans_login_node_filesystem_scans():
    text = _skill_text()
    assert "NEVER run `du`, `df`, `find`, or other filesystem scans on a login node" in text
    assert "Directory sizes\nand quota come from `check_storage`" in text
    assert "xfer-queue job" in text


def test_tool_style_references_name_only_registered_tools():
    text = _skill_text()
    registered = _registered_tools()
    token_mentions = set(re.findall(r"\b[a-z_]+\b", text))
    assert token_mentions & registered

    backticked_calls = set(
        re.findall(r"`((?:mcp__[A-Za-z0-9_]*__)?[a-z_]+)\s*\(", text)
    )
    tool_fields = set(
        re.findall(r"\btool:\s*`?((?:mcp__[A-Za-z0-9_]*__)?[a-z_]+)`?", text)
    )
    suspicious = backticked_calls | tool_fields

    def is_registered_tool_reference(token):
        if token in registered:
            return True
        match = re.fullmatch(r"mcp__[A-Za-z0-9_]*__([a-z_]+)", token)
        return bool(match and match.group(1) in registered)

    assert not {token for token in suspicious if not is_registered_tool_reference(token)}


def test_fastmcp_server_exposes_instructions():
    from nersc_mcp import server

    assert server.app.instructions == server.NERSC_SERVER_INSTRUCTIONS
    assert "one batched ToolSearch call" in server.app.instructions
    assert "Never run du, df, find" in server.app.instructions
