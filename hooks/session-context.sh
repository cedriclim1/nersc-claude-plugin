#!/bin/sh
cat <<'EOF'
This session runs on NERSC Perlmutter with the nersc plugin's 11 MCP tools loaded.
For ANY storage, quota, disk-usage, data-placement, or data-movement question ($SCRATCH vs CFS vs $HOME, migrating projects, I/O problems), call check_storage FIRST.
check_storage reports quotas, placement advice, and purge policy.
Never run raw du/df/find scans on a login node.
Sizing a large tree is an xfer-queue job.
For running, submitting, monitoring, or debugging SLURM jobs, load the /nersc skill and follow its workflow.
Use queue_advise, queue_wait_stats, submit_job dry-run first, and job_postmortem for failures.
No compute on login nodes.
EOF
