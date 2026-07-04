# nersc-claude-plugin

`nersc-claude-plugin` v0.2 is a Claude Code plugin for NERSC Perlmutter: an MCP server with **11 knowledge-encoded SLURM/storage tools** plus a `/nersc` skill that carries the guided submit workflow. It is for anyone who runs `ssh perlmutter -> claude`, from materials science, physics, chemistry, ML, and every other domain that needs HPC without becoming a SLURM specialist. The promise is simple: the invisible NERSC knowledge (QOS traps, the `04:00`-means-4-minutes walltime trap, GPU binding, scratch-vs-CFS placement) is encoded so you stop learning it the expensive way.

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
- MCP registration lives inline in `.claude-plugin/plugin.json`; the repo intentionally has no root `.mcp.json`.
- On Claude Code >= 2.1.121, the plugin's tool schemas load eagerly at session start via `alwaysLoad`; on older versions they are deferred, and the `/nersc` skill's arm-first ToolSearch step covers it.

The plugin bootstrap self-heals its data virtualenv. On startup it rebuilds the venv once when the console script is missing, import sanity fails, the console script shebang points at a missing interpreter, the plugin root moved (detected by build-stamp root mismatch), or an older venv has no build stamp. Run the bootstrap with `--refresh` for an unconditional rebuild.

If the install fails:

```text
/plugin uninstall nersc
```

Then delete the plugin data venv at `~/.claude/plugins/data/<plugin-id>/venv` and reinstall. The bare registration path below always works as a fallback.

## Choosing your Python and install location

The plugin prompts for two optional settings when enabled: **Python interpreter** and **Install/data directory**. Leave them empty to use `python3` from `PATH` and Claude's plugin data directory.

For bare or ssh-stdio registration, use the equivalent environment variables: `NERSC_MCP_PYTHON` for the Python used to build the venv, and `NERSC_MCP_DATA` for the venv/server data directory. Python selection is `NERSC_MCP_PYTHON`, then the plugin option export, then `python3` from `PATH`; data directory selection is `NERSC_MCP_DATA`, then `CLAUDE_PLUGIN_DATA`, then `~/.local/share/nersc-mcp`.

On Perlmutter, run `module load python` before starting Claude, or set **Python interpreter** to an absolute conda/env Python path. The interpreter must be Python 3.10 or newer.

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
claude mcp add nersc -- /pscratch/sd/c/cedlim/nersc_mcp/run-server.sh
```

Then run `claude` on Perlmutter and ask for `/nersc` help or call a tool directly.

## Development

```bash
.venv/bin/pytest
python tests/integration/mcp_smoke.py .venv/bin/nersc-mcp
python tests/integration/mcp_smoke.py ssh perl /pscratch/sd/c/cedlim/nersc_mcp/run-server.sh
```

Tests use mocked SLURM for unit coverage; the smoke checks exercise MCP stdio and stay read-only/dry-run. Layout: `src/nersc_mcp/server.py` registers tools, `tools/` holds one module per tool, `knowledge.py` holds NERSC facts, and `skills/nersc/SKILL.md` defines the Claude workflow. Read `DESIGN.md` before changing tool semantics; the 11-tool surface and invariants are load-bearing.

## Roadmap

| version | scope | tools |
|---|---|---|
| v0.3 | Image tools with podman-hpc and login-node-limits caution. | `image_build`, `image_migrate` |
| v0.4 | ML/workflow enablement: TensorBoard, HPO/Ray-on-SLURM, distributed-training guidance, workflow-engine selection, Jupyter kernels. | `kernel_build` |
| v0.5 | Build doctor and applications: compiler/PrgEnv, math libs, module resolver, license preflight, Darshan/Drishti postmortems. | module resolver |
| v0.6 | Data movement: placement-aware Globus transfers and laptop-to-NERSC via Globus Connect Personal. | `transfer_start`, `transfer_status` |
| v0.7 | SFAPI local mode: executor abstraction, SFAPI executor, client setup skill, and explicit interactive-allocation degradation. | no new tools |
