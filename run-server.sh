#!/bin/bash
# Start nersc-mcp over stdio from this repo's checkout (login node).
# Used by Claude Code registration on Perlmutter and by the ssh-stdio dev harness.
cd "$(dirname "$0")"
if [ -x .venv/bin/nersc-mcp ]; then
    exec .venv/bin/nersc-mcp
fi
exec python3 -m nersc_mcp.server
