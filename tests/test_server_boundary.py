"""FastMCP boundary tests for envelope preservation."""

import asyncio
import json

from nersc_mcp import server
from nersc_mcp.tools import submit as submit_tool


VALID_SPEC = {
    "nodes": 1,
    "time": "00:10:00",
    "constraint": "gpu",
    "qos": "debug",
    "account": "m5020",
    "gpus": 4,
    "command": "hostname",
}


def _decode_tool_result(content):
    if isinstance(content, str):
        return json.loads(content)
    if isinstance(content, list):
        assert len(content) == 1
        item = content[0]
        text = getattr(item, "text", None)
        if text is None and isinstance(item, dict):
            text = item["text"]
        return json.loads(text)
    text = getattr(content, "text", None)
    assert text is not None
    return json.loads(text)


def _call_submit(arguments):
    async def _run():
        return await server.app.call_tool("submit_job", arguments)

    return _decode_tool_result(asyncio.run(_run()))


def test_submit_job_fastmcp_boundary_accepts_extra_spec_key(monkeypatch):
    def fake_run(argv, timeout=30, stdin_text=None):
        raise AssertionError(argv)

    monkeypatch.setattr(submit_tool.slurm, "run", fake_run)
    payload = _call_submit({
        "spec": {**VALID_SPEC, "unknown_extra": "ignored"},
        "dry_run": True,
    })

    assert payload["ok"] is True
    assert payload["data"]["submitted"] is False
    assert "unknown_extra" not in payload["data"]["script"]


def test_submit_job_fastmcp_boundary_returns_validation_envelope(monkeypatch):
    def fake_run(argv, timeout=30, stdin_text=None):
        raise AssertionError(argv)

    monkeypatch.setattr(submit_tool.slurm, "run", fake_run)
    payload = _call_submit({"spec": {**VALID_SPEC, "nodes": "x"}, "dry_run": True})
    assert payload["ok"] is False
    assert payload["error"]["kind"] == "validation"
