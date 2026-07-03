"""NERSC facts — the single source of truth for policy data (DESIGN.md §3).

Every entry cites the wiki concept it came from (wiki/ in the Loop project).
Update facts HERE, never inline in tools. If a fact is missing, ingest it into
the wiki first (from docs.nersc.gov), then add it here with its citation.
"""

# --- QOS policy (wiki: qos-policy; docs.nersc.gov/jobs/policy/) -------------
# max_nodes None = unlimited; times in minutes; charge_factor per node-hour.
QOS = {
    "regular": {"max_nodes": None, "max_minutes": 48 * 60, "min_minutes": 0,
                "submit_limit": 5000, "run_limit": None, "charge_factor": 1.0,
                "note": "50% discount at >=128 GPU nodes / >=256 CPU nodes"},
    "debug": {"max_nodes": 8, "max_minutes": 30, "min_minutes": 0,
              "submit_limit": 5, "run_limit": 2, "charge_factor": 1.0,
              "note": "the silent DEFAULT when --qos is omitted"},
    "interactive": {"max_nodes": 4, "max_minutes": 4 * 60, "min_minutes": 0,
                    "submit_limit": 2, "run_limit": 2, "charge_factor": 1.0,
                    "note": "granted quickly; preferred over debug for test allocations"},
    "shared": {"max_nodes": 0.5, "max_minutes": 48 * 60, "min_minutes": 0,
               "submit_limit": 5000, "run_limit": None, "charge_factor": 1.0,
               "note": "charged only for the node fraction used"},
    "preempt": {"max_nodes": 128, "max_minutes": 48 * 60, "min_minutes": 120,
                "submit_limit": 5000, "run_limit": None, "charge_factor": 0.25,
                "note": "GPU factor 0.25 / CPU 0.5 after the first 2 h; can be preempted"},
    "premium": {"max_nodes": None, "max_minutes": 48 * 60, "min_minutes": 0,
                "submit_limit": 5, "run_limit": None, "charge_factor": 2.0,
                "note": "factor escalates 2 -> 4 once 20% of allocation spent on premium"},
    "overrun": {"max_nodes": None, "max_minutes": 48 * 60, "min_minutes": 0,
                "submit_limit": 5000, "run_limit": None, "charge_factor": 0.0,
                "note": "free but very low priority; only when allocation is exhausted"},
}

# --- Node specs (wiki: slurm-jobs; docs.nersc.gov/systems/perlmutter/architecture/)
NODES = {
    "gpu": {"cores": 64, "gpus": 4, "usable_cpu_mem_gb": 246, "usable_gpu_mem_gb": 150,
            "note": "1x EPYC 7763 + 4x A100 (40 or 80 GB)"},
    "cpu": {"cores": 128, "gpus": 0, "usable_cpu_mem_gb": 502,
            "note": "2x EPYC 7763, 4 NUMA domains/socket"},
}

# --- Env exports worth injecting into GPU job scripts (wiki: s-tomo-runbook) -
GPU_ENV_EXPORTS = {
    "PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True",  # reserved VRAM 22-25GB -> ~10GB
    "PYTHONUNBUFFERED": "1",  # stream loss lines live
}

# --- SLURM reason codes, decoded (wiki: slurm-jobs) --------------------------
REASONS = {
    "Priority": "waiting behind higher-priority jobs; queue age accrues priority — do not cancel/resubmit",
    "QOSMaxJobsPerUserLimit": "you hit this QOS's per-user run limit; wait or use another QOS",
    "QOSMaxSubmitJobPerUserLimit": "you hit this QOS's per-user submit limit",
    "Dependency": "waiting on a job dependency",
    "Resources": "waiting for free nodes matching the request",
    "AssocGrpBillingMinutes": "project allocation exhausted — consider overrun QOS",
}

# --- Storage placement advice (wiki: filesystems) ----------------------------
PLACEMENT = {
    "software": ("/global/common/software/<project>/",
                 "performant, read-only on compute nodes; the right home for conda envs and code"),
    "job_io": ("$SCRATCH",
               "fast Lustre for job I/O and checkpoints; PURGED — copy results off promptly"),
    "shared_data": ("/global/cfs/cdirs/<project>/",
                    "per-project bulk storage, snapshots, no purge; flock() DOES NOT WORK here"),
    "archive": ("HPSS via hsi/htar",
                "tape archive for long-term inactive data"),
    "never": ("$HOME",
              "never for parallel job I/O; small permanent files only"),
}
