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

# --- Iris queue-wait QOS names (wiki: s-iris-queuewait) ---------------------
# User-facing (constraint, qos) pairs map to SLURM/Iris-internal QOS names.
# Design-probe names documented in DESIGN.md §4.9 (wiki: s-iris-queuewait).
IRIS_QOS = {
    ("cpu", "regular"): "regular_1",
    ("cpu", "debug"): "debug",
    ("cpu", "interactive"): "interactive",
    ("cpu", "preempt"): "preempt",
    ("cpu", "premium"): "premium",
    ("cpu", "shared"): "shared",
    ("cpu", "overrun"): "overrun",
    ("gpu", "regular"): "gpu_regular",
    ("gpu", "debug"): "gpu_debug",
    ("gpu", "interactive"): "gpu_interactive",
    ("gpu", "preempt"): "gpu_preempt",
    ("gpu", "premium"): "gpu_premium",
    ("gpu", "shared"): "shared",
    ("gpu", "overrun"): "overrun",
    # Live unfiltered 30d probe captured 2026-07-03; response appeared capped
    # at 1000 rows, so gpu_* rows from the earlier probe may be hidden
    # in that window (wiki: s-iris-queuewait).
    ("cpu", "RESERVE"): "RESERVE",
    ("gpu", "RESERVE"): "RESERVE",
    ("cpu", "badger"): "badger",
    ("gpu", "badger"): "badger",
    ("cpu", "cron"): "cron",
    ("gpu", "cron"): "cron",
    ("cpu", "debug_preempt"): "debug_preempt",
    ("gpu", "debug_preempt"): "debug_preempt",
    ("cpu", "express_amsc"): "express_amsc",
    ("gpu", "express_amsc"): "express_amsc",
    ("cpu", "jupyter"): "jupyter",
    ("gpu", "jupyter"): "jupyter",
    ("cpu", "realtime_als"): "realtime_als",
    ("gpu", "realtime_als"): "realtime_als",
    ("cpu", "realtime_desi"): "realtime_desi",
    ("gpu", "realtime_desi"): "realtime_desi",
    ("cpu", "realtime_lcls"): "realtime_lcls",
    ("gpu", "realtime_lcls"): "realtime_lcls",
    ("cpu", "realtime_m3795"): "realtime_m3795",
    ("gpu", "realtime_m3795"): "realtime_m3795",
    ("cpu", "realtime_m4616"): "realtime_m4616",
    ("gpu", "realtime_m4616"): "realtime_m4616",
    ("cpu", "realtime_m5070"): "realtime_m5070",
    ("gpu", "realtime_m5070"): "realtime_m5070",
    ("cpu", "realtime_m5149"): "realtime_m5149",
    ("gpu", "realtime_m5149"): "realtime_m5149",
    ("cpu", "realtime_nstaff"): "realtime_nstaff",
    ("gpu", "realtime_nstaff"): "realtime_nstaff",
    ("cpu", "regular_1"): "regular_1",
    ("gpu", "regular_1"): "regular_1",
    ("cpu", "gpu_regular"): "gpu_regular",
    ("gpu", "gpu_regular"): "gpu_regular",
    ("cpu", "gpu_debug"): "gpu_debug",
    ("gpu", "gpu_debug"): "gpu_debug",
    ("cpu", "gpu_interactive"): "gpu_interactive",
    ("gpu", "gpu_interactive"): "gpu_interactive",
    ("cpu", "gpu_preempt"): "gpu_preempt",
    ("gpu", "gpu_preempt"): "gpu_preempt",
    ("cpu", "gpu_premium"): "gpu_premium",
    ("gpu", "gpu_premium"): "gpu_premium",
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

# --- Filesystem roots (wiki: filesystems) -----------------------------------
CFS_ROOT = "/global/cfs"
CFS_CDIRS = "/global/cfs/cdirs"
GLOBAL_COMMON_ROOT = "/global/common/software"

# --- Global common constraints (wiki: filesystems; showquota --cmn live
# capture 2026-07-04: m5020 quota 100GiB space / 1M inodes) -------------------
GLOBAL_COMMON_FACTS = {
    "why_it_matters": "conda environments and shared software stacks live here; "
                      "read-optimized and mounted read-only on compute nodes",
    "write_from": "login nodes only (read-only on compute nodes)",
    "quota_note": "small per-project quota (space AND inodes) — conda envs are "
                  "inode-heavy and fill it fast",
}

# Warn when a filesystem crosses this used-percentage (space or inodes).
# Threshold is ours, not NERSC's; jobs are rejected at 100% (wiki: filesystems).
QUOTA_WARN_PERCENT = 85.0

# Quota enforcement fact (wiki: filesystems; friction-points §4).
QUOTA_ENFORCEMENT = ("quota is enforced at job submission AND at srun execution — "
                     "an over-quota filesystem rejects your jobs")
