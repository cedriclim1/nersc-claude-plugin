#!/bin/bash
set -euo pipefail

refresh=0
if [ "${1:-}" = "--refresh" ]; then
    refresh=1
    shift
fi

ROOT="${CLAUDE_PLUGIN_ROOT:-}"
if [ -z "$ROOT" ]; then
    ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi

DATA="${NERSC_MCP_DATA:-${CLAUDE_PLUGIN_DATA:-$HOME/.local/share/nersc-mcp}}"
VENV="$DATA/venv"

die() {
    echo "nersc plugin bootstrap: $*" >&2
    exit 1
}

build_venv() {
    # Build directly at the final path because Python venv console scripts embed
    # absolute shebangs. Concurrent bootstraps are last-writer-wins; a second
    # single-user plugin start may rebuild the venv, which is acceptable.
    # Known limitation: rebuilding is not atomic, so a rebuild can stomp a venv
    # a still-running server holds open. The old tmp+mv pattern was unusable
    # because venv shebangs embed the build path.
    rm -rf "$VENV"
    python3 -m venv "$VENV" || die "failed to create virtualenv at $VENV"
    "$VENV/bin/pip" install --quiet --upgrade pip || die "failed to upgrade pip"
    "$VENV/bin/pip" install --quiet -e "$ROOT" || die "failed to install nersc-mcp from $ROOT"
}

sanity_ok() {
    "$VENV/bin/python3" -c 'import nersc_mcp' >/dev/null 2>&1
}

command -v python3 >/dev/null 2>&1 || die "python3 not found on PATH"
mkdir -p "$DATA" || die "cannot create data directory: $DATA"

if [ "$refresh" -eq 1 ] || [ ! -x "$VENV/bin/nersc-mcp" ]; then
    build_venv
fi

if [ ! -x "$VENV/bin/nersc-mcp" ]; then
    die "console script missing after bootstrap: $VENV/bin/nersc-mcp"
fi

if ! sanity_ok; then
    build_venv
    if ! sanity_ok; then
        die "stale or broken venv at $VENV; automatic rebuild failed — remove it or run with --refresh"
    fi
fi

if [ ! -x "$VENV/bin/nersc-mcp" ]; then
    die "console script missing after bootstrap: $VENV/bin/nersc-mcp"
fi

exec "$VENV/bin/nersc-mcp"
