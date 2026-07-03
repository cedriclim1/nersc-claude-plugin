# NERSC MCP — Design Specification (v1)

**Status:** approved design, Phase 1 (NM-4); user reviewed and approved 2026-07-03.
Changes to §2 (invariants) or §4 (tool semantics) require explicit user approval —
record the approval in the ticket before editing this file.

**Amendment log:**
- 2026-07-03 (user-approved): product is distributed as a **Claude Code plugin**
  (`nersc-claude-plugin` repo) bundling this MCP server + a `/nersc` skill (NM-6);
  the server itself is unchanged. Tool #9 `queue_wait_stats` added (§4.9, NM-10) per
  user feature request.
- 2026-07-03 (user-approved): roadmap extended to v0.7 (§8). Non-goals in §1 now carry
  their owning phase; the workflow-manager and file-deletion non-goals are **permanent**.
  §3 gains the executor-seam note (all subprocess execution behind `slurm.run()`) so the
  v0.7 SFAPI backend can swap executors without touching tool code. No v1 tool semantics
  changed.
- 2026-07-03 (user-approved on Loop board, NM-9): v0.2 adds tool #10
  `get_job_context` and tool #11 `save_job_profile`; `submit_job` gains profile/history
  UX warnings while keeping both original input paths.
- 2026-07-03 (user-approved in v0.2 review): for object-shaped tool params,
  I6 envelope preservation wins over nested tools/list schema pre-validation.
  `submit_job.spec` stays documented in the docstring and is validated inside
  the tool body with `SubmitSpec`.
- 2026-07-03: v0.2 SHIPPED (PR #1 merged) — plugin packaging + /nersc skill,
  queue_wait_stats, get_job_context/save_job_profile, submit_job UX warnings. 11 tools
  live; 95 unit tests + MCP stdio smoke green on Perlmutter. Outstanding v0.2 items:
  NM-7 user-path smoke and the live on-Perlmutter plugin-install validation.

This document is written to be executed by agents of varying capability. If you are an
agent working on this codebase: **read §2 and §7 before writing any code, and re-read the
acceptance criteria for a tool before marking its ticket done.** When this spec and your
intuition disagree, the spec wins; if you believe the spec is wrong, file an issue on the
Loop board and stop — do not improvise.

---

## 1. What this is

An MCP (Model Context Protocol) server that runs **natively on a NERSC Perlmutter login
node** and gives Claude Code (or any MCP client) safe, knowledge-encoded tools for using
NERSC: submitting and diagnosing SLURM jobs, choosing queues, allocating interactive
sessions, and keeping data/storage hygiene. The target user does:

```
ssh perlmutter.nersc.gov
claude          # Claude Code, with nersc-mcp registered as a stdio MCP server
```

The server wraps the *invisible knowledge* documented in the project wiki (concepts:
`slurm-jobs`, `qos-policy`, `friction-points`, `underused-features`) so users don't need
to learn it the expensive way.

**Non-goals for v1** (do not build these, even if they seem easy). Each deferred item
names the roadmap phase (§8) that owns it — it stays a non-goal until that phase's
front gate approves the amendment:
- No SSH bridging inside the server (the server IS on NERSC; decision `dec_mr4h81u2fqq`).
  **Permanent** — remote access is the SFAPI executor's job (v0.7), never SSH.
- No Superfacility API backend (→ **v0.7**, NM-24..27: opt-in executor behind the
  `slurm.run()` seam; native stays primary — decision `dec_mr4l4uv5u5b`).
- No container tools (→ **v0.3**, NM-8, 28, 29, 30 — podman-hpc + Shifter run-path,
  containerized job submission, image visibility, conda→container skill).
- No Globus/DTN transfer execution (→ **v0.6**, NM-21..23; until then `check_storage`
  only *advises*).
- No workflow-manager reimplementation. **Permanent** — a bespoke orchestrator would
  violate I2 and duplicate the nine engines NERSC documents; v0.4 (NM-14) ships a
  decision matrix + config scaffolding instead.
- No file deletion or modification tools of any kind. **Permanent.**

## 2. Hard invariants (safety rails — NEVER weaken these)

These are load-bearing. Each maps to documented evidence (wiki cite in parens). A change
to any invariant requires user sign-off; a PR that weakens one must be rejected.

- **I1 — No compute on login nodes.** No tool may execute reconstruction, training,
  scoring, or any CPU/GPU-heavy work in the server process. Tools run `sbatch`, `salloc`,
  `squeue`, `sacct`, `sinfo`, `sqs`, quota commands — nothing else heavy. Even "tiny"
  compute is banned (friction-points §1; tomo lesson `no-cpu-recon-on-login`).
- **I2 — Minimal process footprint.** The server spawns no background pollers, watchers,
  or monitor loops. Every subprocess is short-lived (default timeout 30 s) and reaped.
  A login-node process-budget kill takes the whole session down (friction-points §1).
- **I3 — Submission completeness.** `submit_job` always emits `--constraint`, `--qos`,
  `--time`, `--nodes`, `--account`; never relies on SLURM defaults (constraint has no
  default and debug-QOS is the silent fallback — slurm-jobs, qos-policy). GPU jobs always
  carry an explicit GPU request (`-G`/`--gpus*`).
- **I4 — Never cancel aged work silently.** `cancel_job` refuses PENDING jobs older than
  60 min unless `force=true`, and the refusal message explains queue-age priority
  (friction-points §3; lesson `queue-age-is-priority`).
- **I5 — Destructive ops are explicit.** Anything that cancels/changes existing state
  requires a `confirm=true` parameter. Read-only tools must be genuinely side-effect-free.
- **I6 — Structured output.** Every tool returns JSON: `{ok, data, warnings[], hints[]}`.
  Raw SLURM text goes in `data.raw` only as a supplement. Warnings carry the encoded
  knowledge (e.g. "debug QOS caps at 30 min — use interactive for 4 h").
- **I7 — No flock on CFS.** Any locking the server ever needs uses atomic `mkdir`
  spin-locks (lesson `flock-unsupported-on-cfs`).
- **I8 — stdlib-only runtime deps** beyond the `mcp` package. No heavy imports at server
  startup (login-node budget, I2). `pydantic` is allowed as the MCP validation stack.

## 3. Architecture

- **Language/runtime:** Python ≥3.9 (Perlmutter's `module load python` provides it),
  official `mcp` Python SDK, **stdio transport only**.
- **Layout:**
  ```
  nersc-mcp/
    pyproject.toml          # deps: mcp, pydantic; dev: pytest
    src/nersc_mcp/
      server.py             # FastMCP app: tool registrations only — no logic
      slurm.py              # subprocess wrappers: run(), parse helpers (pure functions)
      knowledge.py          # QOS table, node specs, env exports — DATA, not code
      tools/                # one module per tool, one public function each
        status.py submit.py jobinfo.py postmortem.py cancel.py
        queue_advise.py allocate.py storage.py
    tests/                  # pytest; mock subprocess — tests never call SLURM
    DESIGN.md  CLAUDE.md  README.md
  ```
- **`knowledge.py` is the single source of NERSC facts** (QOS limits, charge factors,
  memory ceilings, env exports like `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`).
  Facts cite the wiki concept they came from in a comment. Update facts there, never
  inline in tools.
- **Subprocess discipline:** one helper `slurm.run(argv, timeout=30)` — list argv (never
  `shell=True`), captured output, explicit timeout, non-zero exit → structured error.
- **Executor seam (forward compatibility, added 2026-07-03):** `slurm.run()` is the ONLY
  place tool code touches execution. Never call `subprocess` from a tool module. In v0.7
  this seam becomes an executor abstraction (local subprocess vs. SFAPI HTTPS, NM-24/25)
  and the promise is that no `tools/` code changes — every bypass of `slurm.run()` added
  before then breaks that promise.

## 4. v1 tool surface (11 tools — build exactly these)

Every tool: snake_case name, typed primitive params, docstring = what Claude sees.
For object-shaped params, the I6 envelope invariant wins over FastMCP nested field
pre-validation: register the boundary as an object/dict, document fields in the
docstring, and validate inside tool code. Acceptance
criteria (AC) are testable; a tool's ticket is not done until its ACs pass.

1. **`nersc_status()`** — read-only. User's queue (`squeue --me`), recent completions
   (`sacct` last 24 h), headline system state. AC: returns within 10 s; JSON lists jobs
   with jobid/name/state/reason/elapsed; works with zero jobs.
2. **`submit_job(script_body?, spec?, dry_run=False)`** — EITHER validate+submit a
   user-provided script OR build one from a spec `{nodes, time, constraint, qos, account,
   gpus?, ntasks_per_node?, command}`. Applies I3; injects affinity defaults
   (`--cpu-bind=cores`) and known-good env exports; `dry_run=True` returns the exact
   script without submitting. AC: dry-run of a GPU spec contains `-C gpu`, a `--gpus`
   line, `--cpu-bind=cores`; submitting without account/time/constraint returns a
   validation error naming the missing field; a real debug-QOS submit returns a jobid.
3. **`job_status(jobid)`** — squeue + sacct merge: state, reason (decoded:
   `QOSMaxJobsPerUserLimit` → "you hit the per-user run limit for this QOS"), start
   estimate (`squeue --start`), elapsed/limit. AC: pending, running, and finished jobs
   all return a decoded `state_explained` string.
4. **`job_postmortem(jobid)`** — sacct exit codes + DerivedExitCode + state → classified
   cause: `oom | time_limit | node_fail | cancelled | quota | script_error | unknown`,
   each with a one-line fix hint (e.g. oom → "reduce per-task memory or request more
   nodes; GPU nodes have ~150 GB usable GPU RAM"). AC: classifier unit-tested against
   captured sacct fixtures for each category.
5. **`cancel_job(jobid, confirm=False, force=False)`** — I4+I5 guarded scancel.
   AC: refuses without confirm; refuses aged pending job without force and explains why.
6. **`queue_advise(nodes, time_minutes, gpus=0, interactive=False)`** — recommends QOS
   from the knowledge table with cost estimate (charge formula) and warnings (debug ≤30
   min, premium 2-4×, preempt min 2 h, shared ≤0.5 node, big-job 50% discount).
   AC: table-driven tests cover each boundary.
7. **`allocate_interactive(nodes=1, time="04:00:00", constraint="gpu")`** — runs
   `salloc ... --no-shell`, returns JID + ready-to-copy usage pattern
   (`SLURM_JOB_ID=<JID> srun --jobid=<JID> ...`) — the agent-shell ergonomics fix
   (friction-points §2). AC: returns the granted JID; the response includes the srun
   pattern verbatim.
8. **`check_storage(path?)`** — quotas (`showquota`), placement advice for a given need
   (software → /global/common; job I/O → $SCRATCH with purge warning; shared data → CFS;
   never $HOME for parallel I/O), flock-on-CFS warning when relevant. AC: advice table
   unit-tested; quota parse handles the real command output.
9. **`queue_wait_stats(constraint, qos, hours, nodes=1, window_days=30)`** — expected
   queue wait for a job shape, from NERSC's queue-wait database (added by amendment
   2026-07-03, NM-10). Data source (probed and verified unauthenticated, from both
   inside and outside NERSC): `POST https://iris.nersc.gov/graphql_web` with GraphQL
   `query { queueWaitTime { queueWaitTime(qos: "<internal>", startMin: "<%Y-%m-%dT%H:%M:%S>",
   startMax: "...") { qos nodes hours waitHours jobCount maxWaitHours } } }`.
   Both date args are REQUIRED (server 500s otherwise); rows are bucketed by
   (qos, nodes, requested-hours); `qos` uses SLURM-internal names — the user-facing
   (constraint, qos) pair maps via a table in `knowledge.py` (cpu+regular → `regular_1`,
   gpu+regular → `gpu_regular`, gpu+debug → `gpu_debug`, etc. — enumerate from a live
   unfiltered query at implementation time). The tool returns BOTH a long-term window
   (default 30 days) and a short-term window (previous day 00:00 → now) so the agent can
   contrast "typically" vs "right now", plus a plain recommendation (e.g. "expect ~2 h;
   yesterday's max for this shape was 18 h — consider preempt or fewer nodes").
   Uses stdlib `urllib.request` only (I8); 10 s timeout; on any HTTP/parse failure returns
   a structured error and NEVER blocks submission decisions (advice, not a gate).
   AC: qos-mapping table unit-tested; response parser fixture-tested against captured API
   output; empty-bucket result returns ok with an explicit "no jobs matched this shape"
   hint rather than fabricating a number.
10. **`get_job_context(script_path)`** — read-only pre-submit context for a batch script.
   Returns available accounts from `sacctmgr show assoc user=$USER format=account -nP`,
   remembered default account if present, stored per-script profile, capped submission
   history joined to one bounded `sacct -j <comma ids> -o JobID,State,Elapsed -nP` call,
   current-file hash safety flags (`untested`, `changed_since_success`), and parsed
   `module avail cudatoolkit` versions for CUDA mismatch advice. It never applies an
   account automatically; the calling agent must confirm choices with the user. AC:
   table-driven tests cover new, unchanged-completed, edited-since-success, and
   failed-only histories; module parser handles captured module output.
11. **`save_job_profile(script_path, profile, set_default_account=False)`** — persists a
   user-confirmed submit profile for an absolute script path in the local state store,
   optionally also saving `defaults.account`. The state store is
   `~/.nersc-mcp/state.json`, never CFS; writes are atomic via same-directory tmp +
   `os.replace`; concurrency is last-writer-wins with no locks; corrupt JSON is moved to
   `state.json.bad` and treated as empty with an envelope warning. AC: atomic failure
   leaves the original store intact; corrupt-store recovery backs up and warns.

## 5. Error handling

- Subprocess timeout/nonzero → `{ok:false, error:{kind, message, raw}}` — never a Python
  traceback across the MCP boundary.
- SLURM textual errors are *translated*: the raw line plus a plain-English `hint`.
- Unknown states pass through as `unknown` with raw text — never guess silently.

## 6. Testing & verification (the gate for every code ticket)

1. **Unit (required, runs anywhere):** `pytest` with mocked `slurm.run` — parser and
   policy logic only. Target: every tool's AC has a test. No test may invoke real SLURM.
2. **Integration (from the dev machine):** `tests/integration/mcp_smoke.py` speaks MCP
   JSON-RPC over stdio to the real server on Perlmutter via
   `ssh perl "cd /global/cfs/cdirs/m5020/nersc_mcp && ./run-server.sh"` — initialize,
   tools/list, `nersc_status`, `submit_job(dry_run=True)`, `queue_advise`. Read-only +
   dry-run only; safe to run any time.
3. **User-path smoke (before calling a phase done):** on Perlmutter, register the bare
   server path with
   `claude mcp add nersc -- /global/cfs/cdirs/m5020/nersc_mcp/run-server.sh`, then in a
   live Claude Code session on Perlmutter run this five-call sequence: (1)
   `nersc_status`; (2) `submit_job` with a spec for a 1-node, 5-min, debug-QOS CPU job
   running `hostname`; (3) `job_status` until done; (4) `job_postmortem` on that job,
   expecting `sacct` state `COMPLETED` classified as a non-failure (none of
   `oom`/`time_limit`/`node_fail`/`cancelled`/`quota`); (5) `cancel_job` denial paths
   without `confirm`. Guardrail: debug QOS, 1 node, ≤5 min, and never touch other queued
   jobs. A parallel plugin-path validation covers `/plugin marketplace add` +
   `/plugin install` + `tools/list == 11` + `/nersc` skill load.

## 7. Working agreement for downstream agents (READ THIS)

- **Scope control.** Build only what a claimed NM ticket asks. The v1 tool list is
  closed: adding, renaming, or removing a tool = spec change = user approval first.
- **Facts come from the wiki.** If you need a NERSC fact not in `knowledge.py`, it must
  come from a wiki concept (cite it) or from docs.nersc.gov (then ingest it into the wiki
  first). Never from your own priors — they are frequently stale for NERSC specifics.
- **Never test against production.** Real submissions in tests/experiments use debug or
  interactive QOS, ≤1 node, ≤5 min, and are cancelled (with confirm) when done.
- **The checklist for adding/altering a tool:** (1) ticket claimed; (2) AC written in the
  ticket *before* code; (3) logic in `tools/<name>.py`, facts in `knowledge.py`, no logic
  in `server.py`; (4) unit tests for every AC; (5) integration smoke passes; (6) wiki
  ticket summary written; (7) review gate + done.
- **When blocked or surprised** (a command's output doesn't match this spec, a NERSC
  behavior contradicts the wiki): stop, file a Loop issue, ask. Do not code around it.
- **Git:** repo `github.com/cedriclim1/nersc-claude-plugin` (renamed from nersc-mcp,
  2026-07-03; private until the group-testing milestone). Small commits, imperative
  messages. For this project only, Claude may be listed as an author. After each session:
  push, then `ssh perl "cd /global/cfs/cdirs/m5020/nersc_mcp && git pull"` (project rule).

## 8. Roadmap (user-approved 2026-07-03)

Version phases mirror the Loop board. The tool list stays closed at all times; a phase
that adds tools gets its amendment to §4 approved by the user at that phase's **front
gate**, before any code. v0.4+ tickets are deliberately coarse — their detailed specs
are written at the front gate, not before. Do not start a ticket whose phase hasn't
been front-gated.

| phase | scope | tickets | new tools |
|---|---|---|---|
| v0.2 — Plugin packaging & queue intelligence | plugin + `/nersc` skill, user-path smoke, queue_wait_stats, submit-job UX context/profile (SHIPPED 2026-07-03, PR #1; NM-7 + plugin-install validation pending) | NM-6, 7, 9, 10 | queue_wait_stats, get_job_context, save_job_profile |
| v0.3 — Container tools (podman-hpc + Shifter run-path) | container build chain + containerized job submission + image visibility + conda→container skill | NM-8, 28, 29, 30 | image_build, image_build_status, image_migrate, image_list, image_pull (+ submit_job container field) |
| v0.4 — ML & workflow enablement | TensorBoard, HPO/Ray-on-SLURM, distributed training, workflow-engine selector, Jupyter kernels | NM-11..15 | kernel_build |
| v0.5 — Build doctor & applications | compiler/PrgEnv doctor, math libs, module resolver, license preflight, Darshan/Drishti postmortem | NM-16..20 | module resolver |
| v0.6 — Data movement (Globus) | placement-aware transfers, laptop↔NERSC via Globus Connect Personal | NM-21..23 | transfer_start, transfer_status |
| v0.7 — SFAPI backend (local mode) | executor abstraction + SFAPI executor + client-setup skill; `allocate_interactive` degrades explicitly | NM-24..27 | — (backend, not tools) |

Knowledge for each phase lives in the project wiki (concepts: `ml-workflows`,
`build-and-compile`, `applications-catalog`, `jupyter-kernels`, `io-and-checkpoint`,
`data-movement`, `sfapi`); the SFAPI endpoint/auth ground truth is wiki source
`s-sfapi-openapi` (probed 2026-07-03). Direction contract: `dec_mr4l4uv5u5b`.
