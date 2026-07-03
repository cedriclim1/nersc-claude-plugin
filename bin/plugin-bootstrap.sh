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

command -v python3 >/dev/null 2>&1 || die "python3 not found on PATH"
mkdir -p "$DATA" || die "cannot create data directory: $DATA"

if [ "$refresh" -eq 1 ]; then
    rm -rf "$VENV"
fi

if [ ! -x "$VENV/bin/nersc-mcp" ]; then
    TMP="$VENV.tmp.$$"
    rm -rf "$TMP"
    python3 -m venv "$TMP" || die "failed to create virtualenv at $TMP"
    "$TMP/bin/pip" install --quiet --upgrade pip || die "failed to upgrade pip"
    "$TMP/bin/pip" install --quiet -e "$ROOT" || die "failed to install nersc-mcp from $ROOT"

    if [ ! -e "$VENV" ]; then
        if ! mv -T "$TMP" "$VENV" 2>/dev/null; then
            if [ -x "$VENV/bin/nersc-mcp" ]; then
                rm -rf "$TMP"
            else
                rm -rf "$VENV"
                mv "$TMP" "$VENV" || die "failed to publish virtualenv at $VENV"
            fi
        fi
    else
        rm -rf "$TMP"
    fi
fi

if [ ! -x "$VENV/bin/nersc-mcp" ]; then
    die "console script missing after bootstrap: $VENV/bin/nersc-mcp"
fi

exec "$VENV/bin/nersc-mcp"
