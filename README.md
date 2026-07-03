# NERSC MCP

An MCP server that runs **natively on a NERSC Perlmutter login node** and gives Claude
Code safe, knowledge-encoded tools for using NERSC: validated SLURM submission, job
postmortems, queue strategy, persistent interactive allocations, and storage hygiene —
the invisible knowledge most users learn the expensive way.

## Install (on Perlmutter)

```bash
cd /global/cfs/cdirs/m5020/nersc_mcp        # or your own clone
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

## Register in Claude Code (on Perlmutter)

```bash
claude mcp add nersc -- /global/cfs/cdirs/m5020/nersc_mcp/run-server.sh
```

Then `claude` and ask things like *"submit a 2-node GPU debug job that runs
hostname"* or *"why did job 55391394 die?"*.

## Tools (v1 — closed list, see DESIGN.md)

| tool | what it encodes |
|---|---|
| `nersc_status` | your queue + last 24 h, reason codes decoded |
| `submit_job` | mandatory-flag validation, GPU `-G` trap, env exports, dry-run |
| `job_status` | squeue/sacct merge with plain-English state |
| `job_postmortem` | oom / time_limit / node_fail / cancelled / quota / script_error |
| `cancel_job` | confirm-gated; refuses aged pending jobs (queue age = priority) |
| `queue_advise` | QOS choice + node-hour cost from the policy table |
| `allocate_interactive` | `salloc --no-shell` + `srun --jobid` pattern for stateless shells |
| `check_storage` | quotas + where data belongs (+ flock-on-CFS warning) |

## Tests

```bash
.venv/bin/pytest                                   # unit — mocked SLURM, runs anywhere
python tests/integration/mcp_smoke.py .venv/bin/nersc-mcp   # stdio smoke, read-only
```

From a dev machine (ssh-stdio harness):

```bash
python tests/integration/mcp_smoke.py ssh perl /global/cfs/cdirs/m5020/nersc_mcp/run-server.sh
```

## Development

Read **DESIGN.md** (the spec — tool list is closed, invariants are load-bearing) and
**CLAUDE.md** (agent working agreement) before changing anything. Knowledge base and
board live in the companion Loop project.
