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


def test_tool_style_references_name_only_registered_tools():
    text = _skill_text()
    registered = _registered_tools()
    token_mentions = set(re.findall(r"\b[a-z_]+\b", text))
    assert token_mentions & registered

    backticked_calls = set(re.findall(r"`([a-z_]+)\s*\(", text))
    tool_fields = set(re.findall(r"\btool:\s*`?([a-z_]+)`?", text))
    suspicious = backticked_calls | tool_fields
    assert not (suspicious - registered)
