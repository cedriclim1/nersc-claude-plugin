# Installed client component evidence

## Codex 0.144.1

- `codex plugin list` reported `nersc@nersc-local` installed and enabled at 0.2.2.
- `codex mcp list` reported the bundled `nersc` server enabled with the expected
  portable `PLUGIN_ROOT`/`CLAUDE_PLUGIN_ROOT`/working-directory command.
- Offline `codex debug prompt-input "Check my NERSC storage quota and placement"`
  included skill `nersc:nersc` from the installed 0.2.2 cache with the expected
  storage/submit trigger description.
- Offline app-server `plugin/read` reported one enabled NERSC skill, one installed
  `SessionStart` hook, and one `nersc` MCP server.
- Offline `hooks/list` resolved the hook from the installed cache, enabled, hash
  `sha256:5f88cadb1ec5f3e2a22d9f3ff8e9a7c933c73b09387d38d5534b416820579918`, with
  persisted trust state `untrusted`; no trust choice was silently changed.
- The installed cached artifact passed `validate_plugin.py` and MCP `SMOKE PASS`.

## Claude Code 2.1.206

- An isolated `CLAUDE_CONFIG_DIR` installed and enabled
  `nersc@nersc-claude-plugin` at 0.2.2.
- `claude plugin details` reported one NERSC skill, one `SessionStart` hook, and one
  `nersc` MCP server.
- The actual Claude cache path ran through `CLAUDE_PLUGIN_ROOT` and
  `CLAUDE_PLUGIN_DATA` and produced MCP `SMOKE PASS` with the exact 11 tools.

All installation/configuration writes were confined to isolated directories under the
authorized Loop output tree; personal Codex and Claude configuration was untouched.
