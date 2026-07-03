#!/usr/bin/env python3
"""MCP stdio smoke test (DESIGN.md §6.2) — read-only + dry-run only; safe anytime.

Speaks JSON-RPC to a nersc-mcp server over a subprocess's stdio and verifies:
initialize, tools/list (11 tools), queue_advise, submit_job(dry_run).

Usage:
  python tests/integration/mcp_smoke.py <command to start the server...>
e.g. on Perlmutter:   python tests/integration/mcp_smoke.py .venv/bin/nersc-mcp
from a dev machine:   python tests/integration/mcp_smoke.py ssh perl /global/cfs/cdirs/m5020/nersc_mcp/run-server.sh
"""

import json
import subprocess
import sys

EXPECTED_TOOLS = {
    "nersc_status", "submit_job", "job_status", "job_postmortem",
    "cancel_job", "queue_advise", "allocate_interactive", "check_storage",
    "queue_wait_stats",
    "get_job_context", "save_job_profile",
}


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    proc = subprocess.Popen(argv[1:], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            text=True, bufsize=1)
    msg_id = [0]

    def send(method, params=None, notify=False):
        payload = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        if not notify:
            msg_id[0] += 1
            payload["id"] = msg_id[0]
        proc.stdin.write(json.dumps(payload) + "\n")
        proc.stdin.flush()
        if notify:
            return None
        while True:
            line = proc.stdout.readline()
            if not line:
                raise RuntimeError("server closed stdout")
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if msg.get("id") == msg_id[0]:
                if "error" in msg:
                    raise RuntimeError(f"{method} -> {msg['error']}")
                return msg["result"]

    failures = []
    try:
        info = send("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "mcp-smoke", "version": "0"}})
        send("notifications/initialized", notify=True)
        print(f"initialize ok: {info['serverInfo']['name']}")

        tools = {t["name"] for t in send("tools/list")["tools"]}
        missing = EXPECTED_TOOLS - tools
        if missing:
            failures.append(f"missing tools: {missing}")
        print(f"tools/list ok: {sorted(tools)}")

        adv = send("tools/call", {"name": "queue_advise",
                                  "arguments": {"nodes": 2, "time_minutes": 20}})
        body = json.loads(adv["content"][0]["text"])
        if body["data"]["qos"] != "debug":
            failures.append(f"queue_advise wrong: {body}")
        print("queue_advise ok (debug)")

        dry = send("tools/call", {"name": "submit_job", "arguments": {
            "spec": {"nodes": 1, "time": "00:05:00", "constraint": "gpu",
                     "qos": "debug", "account": "m5020", "gpus": 1,
                     "command": "hostname"},
            "dry_run": True}})
        body = json.loads(dry["content"][0]["text"])
        script = body["data"]["script"]
        if "--constraint=gpu" not in script or body["data"]["submitted"]:
            failures.append(f"submit_job dry_run wrong: {body}")
        print("submit_job dry_run ok")

        st = send("tools/call", {"name": "nersc_status", "arguments": {}})
        body = json.loads(st["content"][0]["text"])
        print(f"nersc_status ok={body['ok']} queued={len(body['data']['queued']) if body['ok'] else 'n/a'}")
    finally:
        proc.stdin.close()
        proc.wait(timeout=10)

    if failures:
        print("FAILURES:", *failures, sep="\n  ")
        return 1
    print("SMOKE PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
