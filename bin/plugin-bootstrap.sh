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
    if ! rm -rf "$VENV"; then
        echo "failed to remove existing virtualenv at $VENV" >&2
        return 1
    fi
    if ! python3 -m venv "$VENV"; then
        echo "failed to create virtualenv at $VENV" >&2
        return 1
    fi
    if ! "$VENV/bin/pip" install --quiet --upgrade pip; then
        echo "failed to upgrade pip" >&2
        return 1
    fi
    if ! "$VENV/bin/pip" install --quiet -e "$ROOT"; then
        echo "failed to install nersc-mcp from $ROOT" >&2
        return 1
    fi
}

sanity_ok() {
    "$VENV/bin/python3" -c 'import nersc_mcp' >/dev/null 2>&1
}

command -v python3 >/dev/null 2>&1 || die "python3 not found on PATH"
mkdir -p "$DATA" || die "cannot create data directory: $DATA"

if [ "$refresh" -eq 1 ] || [ ! -x "$VENV/bin/nersc-mcp" ]; then
    build_venv || die "bootstrap build failed: check python3 --version (mcp needs >=3.10), disk space in $DATA, and network"
fi

if [ ! -x "$VENV/bin/nersc-mcp" ]; then
    die "console script missing after bootstrap: $VENV/bin/nersc-mcp"
fi

if ! sanity_ok; then
    if [ "$refresh" -eq 1 ]; then
        die "venv was stale or broken and the automatic rebuild failed — remove $VENV or run with --refresh; if this persists, python3 may be too old (mcp needs >=3.10)"
    fi
    build_venv || die "venv was stale or broken and the automatic rebuild failed — remove $VENV or run with --refresh; if this persists, python3 may be too old (mcp needs >=3.10)"
    if ! sanity_ok; then
        die "venv was stale or broken and the automatic rebuild failed — remove $VENV or run with --refresh; if this persists, python3 may be too old (mcp needs >=3.10)"
    fi
fi

if [ ! -x "$VENV/bin/nersc-mcp" ]; then
    die "console script missing after bootstrap: $VENV/bin/nersc-mcp"
fi

exec "$VENV/bin/nersc-mcp"
