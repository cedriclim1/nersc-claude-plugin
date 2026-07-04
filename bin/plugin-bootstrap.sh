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
STAMP="$DATA/build-stamp"

die() {
    echo "nersc plugin bootstrap: $*" >&2
    exit 1
}

write_build_stamp() {
    if ! printf 'root=%s\n' "$ROOT" > "$STAMP"; then
        echo "failed to write build stamp at $STAMP" >&2
        return 1
    fi
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
    write_build_stamp || return 1
}

stamp_root() {
    local line

    [ -f "$STAMP" ] || return 1
    while IFS= read -r line || [ -n "$line" ]; do
        case "$line" in
            root=*)
                printf '%s\n' "${line#root=}"
                return 0
                ;;
        esac
    done < "$STAMP"
    return 1
}

stamp_matches_root() {
    local stamped_root

    stamped_root="$(stamp_root)" || return 1
    [ "$stamped_root" = "$ROOT" ]
}

sanity_ok() {
    local script first interp leading_ws

    script="$VENV/bin/nersc-mcp"
    [ -x "$script" ] || return 1
    "$VENV/bin/python3" -c 'import nersc_mcp' >/dev/null 2>&1 || return 1

    first=""
    IFS= read -r first < "$script" || [ -n "$first" ] || return 1
    case "$first" in
        '#!'*) ;;
        *) return 1 ;;
    esac

    interp="${first#\#!}"
    leading_ws="${interp%%[![:space:]]*}"
    interp="${interp#"$leading_ws"}"
    interp="${interp%%[[:space:]]*}"
    [ -n "$interp" ] && [ -x "$interp" ]
}

command -v python3 >/dev/null 2>&1 || die "python3 not found on PATH"
mkdir -p "$DATA" || die "cannot create data directory: $DATA"

needs_rebuild=0
rebuild_reason=""

if [ "$refresh" -eq 1 ]; then
    needs_rebuild=1
    rebuild_reason="requested --refresh"
elif [ ! -x "$VENV/bin/nersc-mcp" ]; then
    needs_rebuild=1
    rebuild_reason="console script missing at $VENV/bin/nersc-mcp"
elif ! stamp_matches_root; then
    needs_rebuild=1
    if [ -f "$STAMP" ]; then
        rebuild_reason="venv build stamp does not match this plugin root"
    else
        rebuild_reason="venv build stamp is missing"
    fi
elif ! sanity_ok; then
    needs_rebuild=1
    rebuild_reason="venv failed bootstrap sanity check"
fi

if [ "$needs_rebuild" -eq 1 ]; then
    build_venv || die "$rebuild_reason and the automatic rebuild failed: check python3 --version (mcp needs >=3.10), disk space in $DATA, and network"
fi

if [ ! -x "$VENV/bin/nersc-mcp" ]; then
    die "console script missing after bootstrap: $VENV/bin/nersc-mcp; remove $VENV or run with --refresh"
fi

if ! stamp_matches_root; then
    die "venv build stamp missing or mismatched after bootstrap: $STAMP should contain root=$ROOT; remove $VENV or run with --refresh"
fi

if ! sanity_ok; then
    die "venv failed bootstrap sanity check after bootstrap: console script shebang or imports are broken; remove $VENV or run with --refresh; if this persists, python3 may be too old (mcp needs >=3.10)"
fi

exec "$VENV/bin/nersc-mcp"
