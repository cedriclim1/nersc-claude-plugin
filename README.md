# NERSC MCP — Claude Code and Codex plugin

NERSC MCP v0.2.2 is a dual Claude Code/Codex plugin for NERSC Perlmutter. It
provides **exactly 11 knowledge-encoded SLURM/storage tools** plus a shared guided
workflow for materials science, physics, chemistry, ML, and other NERSC users. The
same MCP server and safety guardrails run in both clients.

## Quickstart

In Claude Code:

```text
/plugin marketplace add cedriclim1/nersc-claude-plugin
/plugin install nersc@nersc-claude-plugin
```

After install:

- Run `/mcp` and confirm server `nersc` is connected.
- Ask Claude to run `nersc_status`.
- Confirm `tools/list` reports the 11 tools listed below.
- Use `/nersc` for guided Perlmutter submission, monitoring, queue forecasts, postmortems, and storage checks.
- Platform note: the plugin targets Perlmutter login nodes (Linux); installing from a non-NERSC machine is not supported until the SFAPI backend in v0.7.
- Claude and Codex share root `.mcp.json`; Claude's manifest has no second inline registration, while `.codex-plugin/plugin.json` points Codex to that file.
- Tool schemas resolve when the MCP server starts; the `/nersc` skill's arm-first ToolSearch step covers clients that defer them.

The plugin bootstrap self-heals its data virtualenv. On startup it rebuilds the venv once when the console script is missing, import sanity fails, the console script shebang points at a missing interpreter, the plugin root moved (detected by build-stamp root mismatch), or an older venv has no build stamp. Run the bootstrap with `--refresh` for an unconditional rebuild.

If the install fails:

```text
/plugin uninstall nersc
```

Then delete the plugin data venv at `~/.claude/plugins/data/<plugin-id>/venv` and reinstall. The bare registration path below always works as a fallback.

## Choosing your Python and install location

The plugin prompts for two optional settings when enabled: **Python interpreter** and **Install/data directory**. Leave them empty to use `python3` from `PATH` and Claude's plugin data directory.

For bare or ssh-stdio registration, use the equivalent environment variables: `NERSC_MCP_PYTHON` for the Python used to build the venv, and `NERSC_MCP_DATA` for the venv/server data directory. Python selection is `NERSC_MCP_PYTHON`, then the Claude plugin option export, then `python3` from `PATH`; data directory selection is `NERSC_MCP_DATA`, `PLUGIN_DATA`, `CLAUDE_PLUGIN_DATA`, the Claude plugin option export, then `~/.local/share/nersc-mcp`.

On Perlmutter, run `module load python` before starting Claude, or set **Python interpreter** to an absolute conda/env Python path. The interpreter must be Python 3.10 or newer.

## Codex plugin and recovery

Codex loads `.codex-plugin/plugin.json`, the shared root `.mcp.json`,
`hooks/hooks.json`, and `skills/`. Claude discovers the same root MCP and hook files;
its manifest intentionally has no second inline MCP registration. Their portable root
fallback supports installed Codex, installed Claude, and checkout discovery from any repository subdirectory
without two manifest registrations. Stage a local development marketplace without
hand-editing personal config.

The staging command snapshots the exact Git index, refuses unstaged or untracked files,
and prints the immutable Git tree ID. Use a new empty target for every snapshot:

```bash
SNAPSHOT="$SCRATCH/nersc-codex-marketplace-v0.2.2"
scripts/stage-codex-marketplace.sh "$SNAPSHOT"
codex plugin marketplace add "$SNAPSHOT"
codex plugin add nersc@nersc-local
codex plugin list
codex mcp list
```

Review the bundled `SessionStart` hook, then start a new task. Plugin hook trust is
optional: declining it removes convenience context but does not disable the skill or
MCP server.

Treat staged marketplaces as immutable. To refresh during development, create a new
snapshot directory and explicitly switch the installed cached copy:

```bash
NEXT="$SCRATCH/nersc-codex-marketplace-v0.2.2-next"
scripts/stage-codex-marketplace.sh "$NEXT"
codex plugin remove nersc@nersc-local
codex plugin marketplace remove nersc-local
codex plugin marketplace add "$NEXT"
codex plugin add nersc@nersc-local
```

This switches Codex to a fresh cached artifact instead of mutating a source behind an
installed cache. The old snapshot is inert and may be deleted only after the plugin and
marketplace source no longer reference it.

To remove the Codex integration while preserving NERSC MCP user state:

```bash
codex plugin remove nersc@nersc-local
codex plugin marketplace remove nersc-local
```

This does not touch `~/.nersc-mcp/state.json` or a configured `NERSC_MCP_DATA` directory.
Once `$SNAPSHOT` is confirmed to be the staging directory you created, `rm -r --
"$SNAPSHOT"` removes only that local fixture.

Validate a checkout or cached artifact and inspect discovery with:

```bash
claude plugin validate .
python "${PLUGIN_CREATOR_DIR:?set to the plugin-creator skill directory}/scripts/validate_plugin.py" .
codex plugin list
codex mcp list
```

If a cached install is invalid, remove the plugin and marketplace as above, fix and
validate the checkout, create a new immutable snapshot, add it, and install again.
Never delete `~/.nersc-mcp/state.json` during recovery. Public marketplace publication
is outside NM-38.

For bare Codex MCP registration from a Perlmutter checkout:

```bash
codex mcp add nersc -- ./bin/plugin-bootstrap.sh
```

Root precedence is `PLUGIN_ROOT`, `CLAUDE_PLUGIN_ROOT`, then the bootstrap script's
repository root. Data precedence is `NERSC_MCP_DATA`, `PLUGIN_DATA`,
`CLAUDE_PLUGIN_DATA`, the Claude `nersc_data_dir` plugin option, then
`~/.local/share/nersc-mcp`.
A failed rebuild can damage only its disposable plugin `venv/`; it never edits client
registration, checked-in manifests, a shared Python environment, or user data in
`~/.nersc-mcp/state.json`. Fix the Python/path/disk error and run
`bin/plugin-bootstrap.sh --refresh`. Existing state is reused in place.

## What you can say

| prompt | what happens |
|---|---|
| "Submit my train.py as a job" | The skill reads the script first, asks only walltime/nodes when needed, always confirms your account, nudges untested code to a debug timing run, and shows a full pre-submit summary with cost and queue-wait forecast before anything is submitted. |
| "Why did job 55391394 die?" | `job_postmortem` runs first and classifies the failure before guessing from symptoms. |
| "How long will a 4-node GPU job wait right now?" | `queue_wait_stats` queries Iris history for the requested shape and contrasts recent vs. long-window waits. |
| "Give me an interactive GPU node for 2 hours" | `allocate_interactive` creates a persistent allocation and returns the `srun --jobid` pattern Claude can reuse. |
| "Where should this checkpoint directory live?" | `check_storage` explains scratch, CFS, common, and HOME placement with quota and parallel-I/O warnings. |

## Guardrails

- Untested or changed scripts get a debug-first nudge; if you decline, the readiness review calls out fatal, likely-waste, and cosmetic findings, and fatal findings require an explicit `submit anyway`.
- Accounts are never auto-applied; the remembered or detected account is always confirmed.
- Job history is remembered per script, so unchanged successful scripts can skip the submit interview.
- CFS job I/O warnings are surfaced: parallel output belongs on `$SCRATCH`, not CFS or `$HOME`, and CFS flock hazards are called out.
- Aged pending jobs are protected; `cancel_job` refuses to throw away queue-age priority unless you force it.

## Tools

| tool | what it encodes |
|---|---|
| `nersc_status` | Your queue, recent completions, and decoded reason codes. |
| `submit_job` | Validated SLURM submission with required account/time/constraint/QOS, GPU requests, env exports, dry-run, and storage/history warnings. |
| `job_status` | `squeue` + `sacct` state, reason, start estimate, elapsed time, and plain-English explanation. |
| `job_postmortem` | Failure classification: OOM, time limit, node fail, cancelled, quota, script error, or unknown, with fix hints. |
| `cancel_job` | Confirm-gated `scancel` with an aged-pending-job guard. |
| `queue_advise` | QOS recommendation, node-hour cost, and policy warnings for debug, preempt, premium, shared, and big jobs. |
| `allocate_interactive` | `salloc --no-shell` plus the reusable `SLURM_JOB_ID=<JID> srun --jobid=<JID>` pattern. |
| `check_storage` | Quotas and placement advice for `$SCRATCH`, CFS, `/global/common`, and `$HOME`, including CFS/flock warnings. |
| `queue_wait_stats` | Iris queue-wait history for a requested constraint, QOS, hours, and node count. |
| `get_job_context` | Accounts, remembered defaults/profile, per-script history, current hash flags, and CUDA module versions. |
| `save_job_profile` | Persists a confirmed per-script submit profile and optional default account in `~/.nersc-mcp/state.json`. |

## Bare registration fallback

```bash
codex mcp add nersc -- /pscratch/sd/c/cedlim/nersc_mcp/run-server.sh
claude mcp add nersc -- /pscratch/sd/c/cedlim/nersc_mcp/run-server.sh
```

Then run `claude` on Perlmutter and ask for `/nersc` help or call a tool directly.

## Development

```bash
PYTHONPATH=src .venv/bin/python -m pytest -q
python "${PLUGIN_CREATOR_DIR:?set to the plugin-creator skill directory}/scripts/validate_plugin.py" .
python tests/integration/mcp_smoke.py .venv/bin/nersc-mcp
python tests/integration/mcp_smoke.py ssh perl /pscratch/sd/c/cedlim/nersc_mcp/run-server.sh
```

Tests mock SLURM. The smoke is read-only plus `submit_job(dry_run=true)`. Retain
installed-client evidence using `artifacts/NM-38/README.md`; before/after scheduler
job-ID sets must match. Read `DESIGN.md` before changing tool semantics.

## Roadmap

| version | scope | tools |
|---|---|---|
| v0.3 | Image tools with podman-hpc and login-node-limits caution. | `image_build`, `image_migrate` |
| v0.4 | ML/workflow enablement: TensorBoard, HPO/Ray-on-SLURM, distributed-training guidance, workflow-engine selection, Jupyter kernels. | `kernel_build` |
| v0.5 | Build doctor and applications: compiler/PrgEnv, math libs, module resolver, license preflight, Darshan/Drishti postmortems. | module resolver |
| v0.6 | Data movement: placement-aware Globus transfers and laptop-to-NERSC via Globus Connect Personal. | `transfer_start`, `transfer_status` |
| v0.7 | SFAPI local mode: executor abstraction, SFAPI executor, client setup skill, and explicit interactive-allocation degradation. | no new tools |
