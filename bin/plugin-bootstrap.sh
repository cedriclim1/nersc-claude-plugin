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
PY="${NERSC_MCP_PYTHON:-}"

die() {
    echo "nersc plugin bootstrap: $*" >&2
    exit 1
}

write_build_stamp() {
    printf 'root=%s\npython=%s\n' "$ROOT" "$PY" > "$STAMP" || {
        echo "failed to write build stamp at $STAMP" >&2
        return 1
    }
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
    if ! "$PY" -m venv "$VENV"; then
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

select_python() {
    local configured resolved

    configured="$PY"
    if [ -z "$configured" ]; then
        # Claude Code exports every plugin userConfig value as
        # CLAUDE_PLUGIN_OPTION_<KEY>, so this remains a live fallback when
        # manifest env substitution is unavailable.
        configured="${CLAUDE_PLUGIN_OPTION_NERSC_PYTHON:-}"
    fi

    if [ -z "$configured" ]; then
        resolved="$(command -v python3 || true)"
        [ -n "$resolved" ] || die "python3 not found on PATH; module load python or set the Python interpreter in plugin settings"
        PY="$resolved"
        return 0
    fi

    case "$configured" in
        */*)
            PY="$configured"
            ;;
        *)
            resolved="$(command -v "$configured" || true)"
            [ -n "$resolved" ] || die "Python interpreter not found: $configured; module load python or set the Python interpreter in plugin settings"
            PY="$resolved"
            ;;
    esac
}

validate_python() {
    local version

    [ -e "$PY" ] || die "Python interpreter not found: $PY; module load python or set the Python interpreter in plugin settings"
    [ -x "$PY" ] || die "Python interpreter is not executable: $PY; module load python or set the Python interpreter in plugin settings"

    if ! "$PY" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then
        version="$("$PY" -c 'import sys; print(".".join(map(str, sys.version_info[:3])))' 2>/dev/null || printf 'unknown')"
        die "Python interpreter $PY reports version $version, but nersc-mcp needs Python >=3.10; module load python or set the Python interpreter in plugin settings"
    fi
}

stamp_value() {
    local key line

    key="$1"
    [ -f "$STAMP" ] || return 1
    while IFS= read -r line || [ -n "$line" ]; do
        line="${line%$'\r'}"
        if [ "${line%%=*}" = "$key" ]; then
            printf '%s\n' "${line#*=}"
            return 0
        fi
    done < "$STAMP"
    return 1
}

stamp_matches_root() {
    local stamped_root

    stamped_root="$(stamp_value root)" || return 1
    [ "$stamped_root" = "$ROOT" ]
}

stamp_matches_python() {
    local line
    local stamped_python

    stamped_python="$(stamp_value python)" || return 1
    [ "$stamped_python" = "$PY" ]
}

stamp_mismatch_reason() {
    if [ ! -f "$STAMP" ]; then
        printf '%s\n' "venv build stamp is missing"
    else
        printf '%s\n' "venv build stamp does not match this plugin root or Python interpreter"
    fi
}


sanity_ok() {
    local script first interp leading_ws interp_base arg real_cmd

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
    [ -n "$interp" ] || return 1

    set -- $interp
    interp="${1:-}"
    [ -n "$interp" ] || return 1

    interp_base="${interp##*/}"
    if [ "$interp_base" = "env" ]; then
        real_cmd=""
        shift
        for arg in "$@"; do
            case "$arg" in
                -S|-*|*=*) continue ;;
                *) real_cmd="$arg"; break ;;
            esac
        done
        [ -n "$real_cmd" ] || return 1
        command -v "$real_cmd" >/dev/null 2>&1
        return $?
    fi
    command -v "$interp" >/dev/null 2>&1
}

select_python
validate_python
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
    rebuild_reason="$(stamp_mismatch_reason)"
elif ! stamp_matches_python; then
    needs_rebuild=1
    rebuild_reason="$(stamp_mismatch_reason)"
elif ! sanity_ok; then
    needs_rebuild=1
    rebuild_reason="venv failed bootstrap sanity check"
fi

if [ "$needs_rebuild" -eq 1 ]; then
    build_venv || die "$rebuild_reason and the automatic rebuild failed using Python interpreter $PY; check $PY --version (nersc-mcp needs >=3.10), disk space in $DATA, and network; on Perlmutter run 'module load python' or set the Python interpreter in plugin settings"
fi

if [ ! -x "$VENV/bin/nersc-mcp" ]; then
    die "console script missing after bootstrap: $VENV/bin/nersc-mcp; remove $VENV or run with --refresh"
fi

if ! stamp_matches_root; then
    die "venv build stamp missing or mismatched after bootstrap: $STAMP should contain root=$ROOT; remove $VENV or run with --refresh"
fi

if ! stamp_matches_python; then
    die "venv build stamp missing or mismatched after bootstrap: $STAMP should contain python=$PY; remove $VENV or run with --refresh"
fi

if ! sanity_ok; then
    die "venv failed bootstrap sanity check after bootstrap: console script shebang or imports are broken; remove $VENV or run with --refresh"
fi

exec "$VENV/bin/nersc-mcp"
