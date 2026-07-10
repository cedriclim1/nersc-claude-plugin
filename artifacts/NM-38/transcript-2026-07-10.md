# NM-38 retained command transcript — 2026-07-10 UTC

All client writes used fresh task-local configuration directories below
`/global/cfs/cdirs/m5020/nersc_mcp_loop/scaffold-output/`. No personal client config,
model service, real submission, allocation, filesystem scan, or user-state file was
touched. Long JSON responses below retain the component fields under review and omit
unrelated interface metadata.

## Automated suite and validators

```text
$ PYTHONPATH=src /pscratch/sd/c/cedlim/nersc_mcp/.venv/bin/python -m pytest -q
........................................................................ [ 59%]
..................................................                       [100%]
123 passed in 4.35s

$ python .../plugin-creator/scripts/validate_plugin.py .
Plugin validation passed: /global/cfs/cdirs/m5020/nersc_mcp_loop/nm-38-worktree

$ claude plugin validate .
Validating marketplace manifest: .../.claude-plugin/marketplace.json
✔ Validation passed
```

The exact-schema test compares every `tools/list` input schema field, nested type,
default, required list, and title against `tests/fixtures/nm38_tool_schemas.json`.

## Reproducible marketplace snapshot

```text
$ scripts/stage-codex-marketplace.sh .../staged-marketplace-v6
staged NERSC marketplace at .../staged-marketplace-v6 from Git tree 75b87164fa00f21b6d1ee10346c1a1c08f674151
next: codex plugin marketplace add .../staged-marketplace-v6
```

The script archived the Git index tree, not the live checkout, and refused unstaged or
untracked input. `artifacts/` is marked `export-ignore`.

## Installed Codex 0.144.1 artifact

```text
$ CODEX_HOME=.../codex-home-nm38-v3 codex plugin remove nersc@nersc-local
Removed plugin `nersc` from marketplace `nersc-local`.

$ CODEX_HOME=.../codex-home-nm38-v3 codex plugin marketplace remove nersc-local
Removed marketplace `nersc-local`.

$ CODEX_HOME=.../codex-home-nm38-v3 codex plugin marketplace add .../staged-marketplace-v6
Added marketplace `nersc-local` from .../staged-marketplace-v6.

$ CODEX_HOME=.../codex-home-nm38-v3 codex plugin add nersc@nersc-local
Added plugin `nersc` from marketplace `nersc-local`.
Installed plugin root: .../codex-home-nm38-v3/plugins/cache/nersc-local/nersc/0.2.2

$ CODEX_HOME=.../codex-home-nm38-v3 codex plugin list
PLUGIN             STATUS              VERSION
nersc@nersc-local  installed, enabled  0.2.2

$ CODEX_HOME=.../codex-home-nm38-v3 codex mcp list
Name   Command  Args                                                                           Status
nersc  sh       -c root=${PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-}}; if [ -z "$root" ]; then root=$(git rev-parse --show-toplevel) || exit 1; fi; exec "$root/bin/plugin-bootstrap.sh"  enabled
```

Offline `plugin/read` through Codex app-server returned:

```json
{
  "summary": {"id":"nersc@nersc-local","localVersion":"0.2.2","installed":true,"enabled":true},
  "skills": [{"name":"nersc:nersc","enabled":true}],
  "hooks": [{"key":"nersc@nersc-local:hooks/hooks.json:session_start:0:0","eventName":"sessionStart"}],
  "mcpServers": ["nersc"]
}
```

Offline `hooks/list` returned the installed cached hook and persisted trust state:

```json
{
  "eventName":"sessionStart",
  "handlerType":"command",
  "command":"sh -c 'root=${PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-}}; if [ -z \"$root\" ]; then root=$(git rev-parse --show-toplevel) || exit 1; fi; exec \"$root/hooks/session-context.sh\"'",
  "sourcePath":".../codex-home-nm38-v3/plugins/cache/nersc-local/nersc/0.2.2/hooks/hooks.json",
  "source":"plugin",
  "pluginId":"nersc@nersc-local",
  "enabled":true,
  "currentHash":"sha256:5f88cadb1ec5f3e2a22d9f3ff8e9a7c933c73b09387d38d5534b416820579918",
  "trustStatus":"untrusted"
}
```

The isolated config intentionally retained `untrusted`; no trust decision was silently
persisted. Executing that exact vetted read-only command directly produced:

```text
This session runs on NERSC Perlmutter with the nersc plugin's MCP tools loaded.
For ANY storage, quota, disk-usage, data-placement, or data-movement question ($SCRATCH vs CFS vs $HOME, migrating projects, I/O problems), call check_storage FIRST.
Never run raw du/df/find scans on a login node.
Use queue_advise, queue_wait_stats, submit_job dry-run first, and job_postmortem for failures.
No compute on login nodes.
```

Offline `codex debug prompt-input` listed skill `nersc:nersc` from the installed cache at
`.../plugins/cache/nersc-local/nersc/0.2.2/skills/nersc/SKILL.md`.

The official validator then checked the cached root:

```text
Plugin validation passed: .../codex-home-nm38-v3/plugins/cache/nersc-local/nersc/0.2.2
```

## Installed Codex-cache MCP stdio smoke

```text
initialize ok: nersc
tools/list ok: ['allocate_interactive', 'cancel_job', 'check_storage', 'get_job_context', 'job_postmortem', 'job_status', 'nersc_status', 'queue_advise', 'queue_wait_stats', 'save_job_profile', 'submit_job']
queue_advise ok (debug)
submit_job dry_run ok
nersc_status ok=True queued=0
check_storage ok quotas=2 projects=['m5020', 'm5169', 'm5241'] common=True
SMOKE PASS
```

The command under test was the exact installed `.mcp.json` shell command with
`PLUGIN_ROOT` and `PLUGIN_DATA` pointed at the isolated cache/data directories.

## Installed Claude Code 2.1.206 artifact

```text
$ CLAUDE_CONFIG_DIR=.../claude-home-nm38-v6 claude plugin install nersc@nersc-claude-plugin
✔ Successfully installed plugin: nersc@nersc-claude-plugin (scope: user)

$ CLAUDE_CONFIG_DIR=.../claude-home-nm38-v6 claude plugin list
nersc@nersc-claude-plugin
Version: 0.2.2
Status: ✔ enabled

$ CLAUDE_CONFIG_DIR=.../claude-home-nm38-v6 claude plugin details nersc@nersc-claude-plugin
Component inventory
  Skills (1)  nersc
  Hooks (1)  SessionStart  (harness-only — no model context cost)
  MCP servers (1)  nersc  (tool schemas resolved at runtime; not counted)
```

`claude plugin list --json` retained the exact installed cache path and shared command:

```json
{
  "id":"nersc@nersc-claude-plugin",
  "version":"0.2.2",
  "enabled":true,
  "installPath":".../claude-home-nm38-v6/plugins/cache/nersc-claude-plugin/nersc/0.2.2",
  "mcpServers":{"nersc":{"command":"sh","args":["-c","root=${PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-}}; if [ -z \"$root\" ]; then root=$(git rev-parse --show-toplevel) || exit 1; fi; exec \"$root/bin/plugin-bootstrap.sh\""]}}
}
```

The official validator reported:

```text
Plugin validation passed: .../claude-home-nm38-v6/plugins/cache/nersc-claude-plugin/nersc/0.2.2
```

The installed Claude-cache MCP smoke retained its command environment and output:

```text
$ CLAUDE_PLUGIN_ROOT=.../claude-home-nm38-v6/plugins/cache/nersc-claude-plugin/nersc/0.2.2 \
  CLAUDE_PLUGIN_DATA=.../claude-home-nm38-v6/plugin-data \
  NERSC_MCP_PYTHON=/pscratch/sd/c/cedlim/nersc_mcp/.venv/bin/python \
  python tests/integration/mcp_smoke.py sh -c 'root=${PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-}}; if [ -z "$root" ]; then root=$(git rev-parse --show-toplevel) || exit 1; fi; exec "$root/bin/plugin-bootstrap.sh"'
initialize ok: nersc
tools/list ok: ['allocate_interactive', 'cancel_job', 'check_storage', 'get_job_context', 'job_postmortem', 'job_status', 'nersc_status', 'queue_advise', 'queue_wait_stats', 'save_job_profile', 'submit_job']
queue_advise ok (debug)
submit_job dry_run ok
nersc_status ok=True queued=0
check_storage ok quotas=2 projects=['m5020', 'm5169', 'm5241'] common=True
SMOKE PASS
```

## Scheduler no-submission proof

```text
$ date -u; squeue --me -h -o %A
2026-07-10T23:42:48Z
<empty job-ID set>

# Codex v6 installed-cache smoke completed before the final check
# Claude installed-cache smoke completed before the final check

$ date -u; squeue --me -h -o %A
2026-07-10T23:43:40Z
<empty job-ID set>
```

The before and after job-ID sets are identical. Both client smokes used only
`queue_advise`, `submit_job(dry_run=true)`, `nersc_status`, and `check_storage` after
`tools/list`; neither created a job or allocation.
