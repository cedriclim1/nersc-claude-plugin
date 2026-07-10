# NM-38 verification evidence

This directory retains the reproducible verification contract for the Codex/Claude
compatibility release. Populate command transcripts only with non-sensitive output.
The completed retained record is `transcript-2026-07-10.md`.

## Automated gates

- [x] Unit suite: `PYTHONPATH=src <project-python> -m pytest -q`
- [x] Plugin manifest: `validate_plugin.py .`
- [x] Local stdio MCP smoke: `tests/integration/mcp_smoke.py <server command>`
- [x] Installed Codex artifact on Perlmutter
- [x] Installed Claude Code artifact on Perlmutter

## Installed-client safety checklist

For each client record its version, plugin install source, hook-trust state, exact
11-tool list, `nersc_status`, `check_storage`, and `submit_job(dry_run=true)` result.
Capture `squeue --me -h -o %A` immediately before and after the dry-run and verify the
sets are identical. Do not run `du`, `df`, `find`, create an allocation, or submit a
real job for NM-38.
