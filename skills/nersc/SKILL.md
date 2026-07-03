---
name: nersc
description: Drive NERSC Perlmutter through the nersc MCP tools — submit and monitor
  SLURM jobs with guardrails, forecast queue waits, diagnose failures, check storage.
  Use whenever the user wants to run, submit, monitor, or debug work on NERSC.
---

# /nersc

Use this skill whenever the user wants to run, submit, monitor, or debug work on NERSC
Perlmutter.

## Tool Composition Basics

<!-- wiki: slurm-jobs -->
<!-- wiki: qos-policy -->
<!-- wiki: friction-points -->

- Submission workflow: `check_storage` -> `queue_advise` -> `queue_wait_stats` ->
  `submit_job` with `dry_run=true` -> user review -> real `submit_job` -> `job_status`.
- Debugging is postmortem-first: when a job fails or finishes unexpectedly, call
  `job_postmortem` before guessing from symptoms.
- For interactive work, prefer the persistent allocation pattern encoded by
  `allocate_interactive`: `salloc --no-shell`, then run commands with the returned
  `SLURM_JOB_ID=<JID> srun --jobid=<JID>` form.
- NEVER cancel aged queued jobs. Queue age is scheduler priority; cancelling an old
  pending job discards that priority. `cancel_job` has an age guard, but the agent should
  also avoid recommending cancellation of aged queued work.

## The Submit-Job Interview

<!-- wiki: slurm-jobs -->
<!-- wiki: qos-policy -->
<!-- wiki: friction-points -->
<!-- wiki: ml-workflows -->

1. Locate the script. Ask only if the path or intended script is ambiguous.

2. INFER-FIRST: read the script before asking anything. Infer GPU usage from signals such
   as `torch.cuda`, `cupy`, or `jax`; distributed framework from `torchrun`,
   `dist.init_process_group`, or `mpi4py`; argparse surface; imports; and environment
   needs.

3. Call `get_job_context` with the script path. Interview only the unknowables:
   walltime and nodes. Environment is confirm-class: infer a prebuilt image such as
   `nersc/pytorch` via shifter or podman-hpc, a conda environment, or modules, but ask
   when ambiguous. Account is always confirmed with the user. Pre-fill the detected or
   remembered default from `get_job_context`, but never auto-apply it.

4. If `get_job_context` says `untested` or `changed_since_success`, always propose a
   debug timing run first. A debug timing run must be <=30 minutes and should validate
   the script while measuring walltime; extrapolate measured runtime with a +25% margin.
   If the user declines, do a mandatory readiness review: spawn one short-lived
   foreground subagent, never a background process, to statically screen the code against
   the claimed job shape. Check parallelism claim vs actual distributed setup, GPU claim
   vs code that uses CUDA, hardcoded local paths, and checkpointing presence when
   walltime is long (>6h). Rank findings as fatal, likely-waste, or cosmetic. Findings
   are advisory and require explicit acknowledgement. A fatal finding requires the user
   to literally say "submit anyway"; never silently block and never silently proceed.

5. CUDA mismatch check: if the code pins a CUDA version, such as a torch build CUDA,
   `cupy-cudaNNx`, or an `nvcc` requirement, compare it against `get_job_context`
   `cudatoolkit_modules` and suggest an aligned module or a matching `nersc/pytorch`
   image tag.

6. Before any real submission, always provide a pre-submit summary: the full generated
   script; every parameter including inferred ones, each individually overridable; the
   confirmed account; estimated node-hour cost as `nodes x walltime x QOS charge factor`;
   and the `queue_wait_stats` forecast for the chosen QOS. After the user confirms, call
   `submit_job`; never skip dry_run first. Report the jobid and start_estimate, then use
   `job_status` for monitoring.

7. After a debug timing run completes, offer one-confirm promotion to production. Read
   the run's elapsed time from `get_job_context` history, extrapolate with margin,
   pre-fill the production spec, confirm it, and submit. Persist the confirmed spec with
   `save_job_profile` so resubmissions skip the interview entirely. Re-ask only when the
   user wants changes.

8. QOS guidance: refuse >30 minutes in debug; suggest interactive for short GPU sessions;
   suggest preempt for checkpointed workloads because it can provide cheap capacity; warn
   before premium because it has a 2x charge factor.

## User Spectrum

<!-- wiki: ml-workflows -->

Users include materials scientists, physicists, chemists, and computer scientists. When
an application code is named, such as LAMMPS, VASP, GROMACS, or QE, prefer NERSC's
prebuilt images or modules over pip-installing. The catalog lives at
hub.docker.com/u/nersc.

## Subagent Policy

Readiness-review subagents are short-lived foreground tasks, bounded to one per
submission flow. They are never server processes.
