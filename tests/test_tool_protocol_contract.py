import json
from pathlib import Path

from nersc_mcp import server


SCHEMA_FIXTURE = (
    Path(__file__).resolve().parent / "fixtures" / "nm38_tool_schemas.json"
)


def test_exact_tool_names_and_complete_schemas_are_stable():
    actual = {
        tool.name: tool.parameters
        for tool in server.app._tool_manager.list_tools()
    }
    expected = json.loads(SCHEMA_FIXTURE.read_text(encoding="utf-8"))
    assert actual == expected


def test_safety_contract_remains_encoded_in_docs_and_server():
    instructions = server.NERSC_SERVER_INSTRUCTIONS
    assert "raw shell is not a fallback" in instructions
    assert "Never run du, df, find" in instructions
    by_name = {tool.name: tool for tool in server.app._tool_manager.list_tools()}
    assert "dry_run=true" in by_name["submit_job"].description
    assert "Requires confirm=true" in by_name["cancel_job"].description
