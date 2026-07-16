# NM-38 verification — 2026-07-10 UTC

All checks ran on NERSC Perlmutter without a real submission, allocation, filesystem
scan, personal-config mutation, or online model session.
Literal command/output excerpts are retained in `transcript-2026-07-10.md`.

| Gate | Evidence |
|---|---|
| Unit/compatibility suite | `123 passed in 4.35s` |
| Repo plugin validation | `Plugin validation passed` |
| Marketplace staging | clean snapshot staged as `nersc-local` |
| Offline Codex install | `nersc@nersc-local`, installed/enabled, version `0.2.2` |
| Installed-cache validation | `Plugin validation passed` on the cached artifact |
| Codex env installed smoke | exact 11 tools, status/storage OK, submit dry-run OK, `SMOKE PASS` |
| Claude env regression smoke | exact 11 tools, status/storage OK, submit dry-run OK, `SMOKE PASS` |
| Scheduler no-submit proof | before and after job-ID sets both empty |

Client versions observed: `codex-cli 0.144.1`; Claude Code `2.1.206`.

The Codex install used an isolated `CODEX_HOME` under the authorized Loop output tree.
The Claude regression used an isolated `CLAUDE_CONFIG_DIR` and its installed 0.2.2
cache. Neither test contacted a model service; both exercised MCP stdio directly
through `tests/integration/mcp_smoke.py`.
