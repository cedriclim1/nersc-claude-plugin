# AGENTS.md — working agreement for Codex

This repository is the NERSC MCP server and dual Claude Code/Codex plugin. Read
`DESIGN.md` sections 2 and 7 before editing. The 11-tool API is closed: do not add,
rename, remove, or change a tool's semantics without explicit user approval.

## Hard rules

- Never weaken DESIGN.md invariants I1–I8.
- Never run compute, filesystem scans (`du`, `df`, `find`), pollers, watchers, or
  background daemons on a NERSC login node.
- Tool subprocesses go through `slurm.run()` with a timeout. Tests mock it.
- NERSC facts live only in `src/nersc_mcp/knowledge.py` and cite the project wiki.
- Keep registrations in `server.py`, tool logic in `tools/`, subprocess handling in
  `slurm.py`, and response-envelope helpers in `util.py`.
- Every tool returns `{ok, data, warnings, hints}`. Never leak a traceback over MCP.
- Work a claimed Loop ticket, preserve unrelated changes, use small imperative commits,
  never force-push, and never push unless the user explicitly authorizes it.

## NM ticket workflow

1. Ground in Loop project NERSC MCP (key NM), clear due decisions, and claim the ticket.
2. Confirm acceptance criteria before editing.
3. Implement inside the existing layers; do not change the 11-tool surface accidentally.
4. Run:

   ```bash
   PYTHONPATH=src .venv/bin/python -m pytest -q
   python tests/integration/mcp_smoke.py .venv/bin/nersc-mcp
   python "${PLUGIN_CREATOR_DIR:?set to the plugin-creator skill directory}/scripts/validate_plugin.py" .
   ```

5. On Perlmutter, installed-artifact validation is read-only plus `submit_job` dry-run.
   Real submissions, if separately authorized, are debug/interactive, one node, at most
   five minutes, and use only the allocation/job ID named by the task brief.
6. Write `wiki/tickets/NM-N.md`, run the Loop review gate, and close only when its
   diff-bound review passes.

## Distribution ownership

- Root `.mcp.json` is the one shared Claude/Codex MCP registration; do not add a second
  inline registration to `.claude-plugin/plugin.json`.
- `.codex-plugin/plugin.json` points Codex at root `.mcp.json`, `skills/`, and default
  `hooks/hooks.json`; their commands must retain both client-root fallbacks.
- `bin/plugin-bootstrap.sh` must remain compatible with both hosts and must not install
  into shared Python environments.

If observed NERSC, Claude, or Codex behavior contradicts the design, stop and file a
Loop issue rather than hiding the surprise.
