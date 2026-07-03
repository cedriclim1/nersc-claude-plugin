# CLAUDE.md — working agreement for agents in this repo

You are working on **nersc-mcp**, an MCP server that runs on NERSC Perlmutter login
nodes. This file is your contract. It is deliberately prescriptive: follow it exactly,
and when it conflicts with your own judgment, **the contract wins**.

## The one-paragraph orientation

The design is settled and documented in **DESIGN.md** — read §2 (invariants) and §7
(working agreement) before your first edit, every session. The v1 tool list (8 tools) is
**closed**: you may not add, rename, remove, or change the semantics of a tool without
the user approving a spec change first. Your job is almost always: implement or fix ONE
ticket from the Loop board, inside the existing structure, with its acceptance criteria
as the definition of done.

## Hard rules (violations = the work is wrong, even if it runs)

1. **Never weaken a DESIGN.md §2 invariant** (I1–I8). If a change seems to require it,
   stop and file a Loop issue.
2. **No compute on login nodes** — the server only shells out to fast SLURM/quota
   commands. Never add anything that trains, reconstructs, or crunches.
3. **No background processes** — no pollers, watchers, daemons, threads that outlive a
   tool call. Every subprocess goes through `slurm.run()` with a timeout.
4. **NERSC facts live in `knowledge.py` only**, each with a wiki citation comment. Never
   hardcode a QOS limit, node spec, or path in a tool. If the fact isn't in
   `knowledge.py`, it must come from the project wiki or docs.nersc.gov (ingest to the
   wiki first) — never from your training-data memory of NERSC.
5. **Layer discipline**: `server.py` = registrations only; `tools/<name>.py` = one tool's
   logic; `slurm.py` = subprocess + parsing; `util.py` = the result envelope. Don't blur.
6. **Every tool returns the `{ok, data, warnings, hints}` envelope** — no bare strings,
   no tracebacks across the MCP boundary.
7. **Tests mock `slurm.run`** — unit tests must never call real SLURM. Real submissions
   (integration/smoke only) use debug or interactive QOS, ≤1 node, ≤5 min.
8. **Git**: repo is `github.com/cedriclim1/nersc-mcp`. Small commits, imperative mood.
   For this project only, Claude may be listed as an author. Never force-push.

## The loop for any change

1. Ground in the Loop project (board + wiki) and **claim your ticket** before editing.
2. Write/confirm the acceptance criteria in the ticket BEFORE coding.
3. Implement inside the layer structure above.
4. `pytest` — all green, including new tests covering every AC.
5. Smoke: `python tests/integration/mcp_smoke.py .venv/bin/nersc-mcp` (on Perlmutter)
   or via `ssh perl .../run-server.sh` from a dev machine. Must print `SMOKE PASS`.
6. Write the wiki ticket summary; run the review gate; mark done.
7. Push, then sync the CFS clone: `ssh perl "cd /global/cfs/cdirs/m5020/nersc_mcp && git pull"`.

## When you are surprised

If a real command's output doesn't match a parser, if NERSC behavior contradicts the
wiki, if a test only passes with a change you don't understand: **stop coding, file a
Loop issue describing the surprise, and ask.** An incorrect "fix" that hides a surprise
is the most expensive failure mode in this codebase.

## Where things are

| thing | where |
|---|---|
| Design spec (authoritative) | `DESIGN.md` |
| Knowledge base / board / rules | Loop project `NERSC MCP` (key NM) — wiki concepts `mcp-tool-surface`, `friction-points`, `slurm-jobs`, `qos-policy` |
| Deployment | `/global/cfs/cdirs/m5020/nersc_mcp` (git clone on CFS) |
| Dev harness | `tests/integration/mcp_smoke.py` over `ssh perl` |
| v2 backlog (do NOT start unbidden) | image build/migrate, DTN/Globus transfers, sfapi backend — see wiki `underused-features` |
