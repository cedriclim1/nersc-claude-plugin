#!/usr/bin/env bash
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HARNESS_TMP="$(mktemp -d)"
SHIM_DIR="$HARNESS_TMP/shim"
failures=0

cleanup() {
    rm -rf "$HARNESS_TMP"
}
trap cleanup EXIT

mkdir -p "$SHIM_DIR"
export BOOTSTRAP_PYTHON_SHIM="$SHIM_DIR/python3"

cat > "$BOOTSTRAP_PYTHON_SHIM" <<'PY'
#!/usr/bin/env bash
set -euo pipefail

write_fake_python() {
    local target="$1"

    cat > "$target" <<PYTHON
#!/usr/bin/env bash
exec "$BOOTSTRAP_PYTHON_SHIM" "\$@"
PYTHON
    chmod +x "$target"
}

write_fake_pip() {
    local target="$1"

    cat > "$target" <<'PIP'
#!/usr/bin/env bash
exit 0
PIP
    chmod +x "$target"
}

write_fake_console() {
    local target="$1"
    local shebang="$2"

    cat > "$target" <<CONSOLE
#!$shebang
# fake nersc-mcp console script
CONSOLE
    chmod +x "$target"
}

if [ "${1:-}" = "-m" ] && [ "${2:-}" = "venv" ]; then
    venv="${3:?missing venv path}"
    count=0
    if [ -f "$BOOTSTRAP_BUILD_COUNT" ]; then
        count="$(cat "$BOOTSTRAP_BUILD_COUNT")"
    fi
    printf '%s\n' "$((count + 1))" > "$BOOTSTRAP_BUILD_COUNT"

    rm -rf "$venv"
    mkdir -p "$venv/bin"
    write_fake_python "$venv/bin/python3"
    write_fake_pip "$venv/bin/pip"
    write_fake_console "$venv/bin/nersc-mcp" "$venv/bin/python3"
    exit 0
fi

if [ "${1:-}" = "-c" ]; then
    exit 0
fi

case "${1:-}" in
    */nersc-mcp)
        printf 'BOOTSTRAP_OK\n'
        exit 0
        ;;
esac

exit 0
PY
chmod +x "$BOOTSTRAP_PYTHON_SHIM"

export PATH="$SHIM_DIR:$PATH"

write_fake_python() {
    local target="$1"

    cat > "$target" <<PYTHON
#!/usr/bin/env bash
exec "$BOOTSTRAP_PYTHON_SHIM" "\$@"
PYTHON
    chmod +x "$target"
}

write_fake_pip() {
    local target="$1"

    cat > "$target" <<'PIP'
#!/usr/bin/env bash
exit 0
PIP
    chmod +x "$target"
}

write_fake_console() {
    local target="$1"
    local shebang="$2"

    cat > "$target" <<CONSOLE
#!$shebang
# fake nersc-mcp console script
CONSOLE
    chmod +x "$target"
}

make_fake_venv() {
    local data="$1"
    local shebang="$2"
    local venv="$data/venv"

    mkdir -p "$venv/bin"
    write_fake_python "$venv/bin/python3"
    write_fake_pip "$venv/bin/pip"
    write_fake_console "$venv/bin/nersc-mcp" "$shebang"
}

write_stamp() {
    local data="$1"
    local root="$2"
    local python="$3"

    printf 'root=%s\npython=%s\n' "$root" "$python" > "$data/build-stamp"
}

prepare_case() {
    local name="$1"

    CASE_DIR="$HARNESS_TMP/$name"
    DATA_DIR="$CASE_DIR/data"
    COUNTER="$CASE_DIR/build-count"
    mkdir -p "$DATA_DIR"
    printf '0\n' > "$COUNTER"
}

run_bootstrap() {
    local data="$1"
    local counter="$2"
    shift 2
    local output

    if output="$(env \
        NERSC_MCP_DATA="$data" \
        NERSC_MCP_PYTHON="${NERSC_MCP_PYTHON:-}" \
        CLAUDE_PLUGIN_OPTION_NERSC_PYTHON="${CLAUDE_PLUGIN_OPTION_NERSC_PYTHON:-}" \
        CLAUDE_PLUGIN_ROOT="$ROOT" \
        BOOTSTRAP_BUILD_COUNT="$counter" \
        BOOTSTRAP_PYTHON_SHIM="$BOOTSTRAP_PYTHON_SHIM" \
        PATH="$PATH" \
        bash "$ROOT/bin/plugin-bootstrap.sh" "$@" 2>&1)"; then
        LAST_STATUS=0
    else
        LAST_STATUS=$?
    fi
    LAST_OUTPUT="$output"
}

record_result() {
    local name="$1"
    local expected_count="$2"
    local count

    count=0
    if [ -f "$COUNTER" ]; then
        count="$(cat "$COUNTER")"
    fi

    if [ "$LAST_STATUS" -eq 0 ] && [ "$count" = "$expected_count" ]; then
        case "$LAST_OUTPUT" in
            *BOOTSTRAP_OK*)
                printf 'PASS %s\n' "$name"
                return
                ;;
        esac
    fi

    printf 'FAIL %s\n' "$name"
    printf '  expected rebuilds: %s\n' "$expected_count"
    printf '  actual rebuilds:   %s\n' "$count"
    printf '  exit status:       %s\n' "$LAST_STATUS"
    printf '  output:\n%s\n' "$LAST_OUTPUT"
    failures=$((failures + 1))
}

record_stamp_python() {
    local name="$1"
    local data="$2"
    local expected="$3"
    local actual=""

    if [ -f "$data/build-stamp" ]; then
        actual="$(awk -F= '$1 == "python" { print substr($0, index($0, "=") + 1); found=1; exit } END { if (!found) exit 1 }' "$data/build-stamp" || true)"
    fi

    if [ "$actual" = "$expected" ]; then
        printf 'PASS %s\n' "$name"
        return
    fi

    printf 'FAIL %s\n' "$name"
    printf '  expected stamp python: %s\n' "$expected"
    printf '  actual stamp python:   %s\n' "$actual"
    failures=$((failures + 1))
}

prepare_case healthy_matching_stamp
make_fake_venv "$DATA_DIR" "$DATA_DIR/venv/bin/python3"
write_stamp "$DATA_DIR" "$ROOT" "$BOOTSTRAP_PYTHON_SHIM"
unset NERSC_MCP_PYTHON
run_bootstrap "$DATA_DIR" "$COUNTER"
record_result "healthy fake venv + matching stamp" 0

prepare_case healthy_venv_no_stamp
make_fake_venv "$DATA_DIR" "$DATA_DIR/venv/bin/python3"
unset NERSC_MCP_PYTHON
run_bootstrap "$DATA_DIR" "$COUNTER"
record_result "healthy fake venv + no stamp first run" 1
run_bootstrap "$DATA_DIR" "$COUNTER"
record_result "healthy fake venv + no stamp second run" 1

prepare_case env_shebang_resolvable
make_fake_venv "$DATA_DIR" "/usr/bin/env python3"
write_stamp "$DATA_DIR" "$ROOT" "$BOOTSTRAP_PYTHON_SHIM"
unset NERSC_MCP_PYTHON
run_bootstrap "$DATA_DIR" "$COUNTER"
record_result "env console-script shebang with resolvable python3" 0

prepare_case env_shebang_missing
make_fake_venv "$DATA_DIR" "/usr/bin/env definitely-missing-cmd-xyz"
write_stamp "$DATA_DIR" "$ROOT" "$BOOTSTRAP_PYTHON_SHIM"
unset NERSC_MCP_PYTHON
run_bootstrap "$DATA_DIR" "$COUNTER"
record_result "env console-script shebang with missing command" 1

prepare_case dead_shebang
make_fake_venv "$DATA_DIR" "/nonexistent/python3"
write_stamp "$DATA_DIR" "$ROOT" "$BOOTSTRAP_PYTHON_SHIM"
unset NERSC_MCP_PYTHON
run_bootstrap "$DATA_DIR" "$COUNTER"
record_result "dead console-script shebang" 1

prepare_case stamp_root_mismatch
make_fake_venv "$DATA_DIR" "$DATA_DIR/venv/bin/python3"
write_stamp "$DATA_DIR" "/old/plugin/root" "$BOOTSTRAP_PYTHON_SHIM"
unset NERSC_MCP_PYTHON
run_bootstrap "$DATA_DIR" "$COUNTER"
record_result "stamp root mismatch" 1

prepare_case refresh
make_fake_venv "$DATA_DIR" "$DATA_DIR/venv/bin/python3"
write_stamp "$DATA_DIR" "$ROOT" "$BOOTSTRAP_PYTHON_SHIM"
unset NERSC_MCP_PYTHON
run_bootstrap "$DATA_DIR" "$COUNTER" --refresh
record_result "--refresh" 1

prepare_case custom_python
export NERSC_MCP_PYTHON="$BOOTSTRAP_PYTHON_SHIM"
run_bootstrap "$DATA_DIR" "$COUNTER"
record_result "custom Python interpreter first build" 1
record_stamp_python "custom Python interpreter stamped" "$DATA_DIR" "$BOOTSTRAP_PYTHON_SHIM"
run_bootstrap "$DATA_DIR" "$COUNTER"
record_result "custom Python interpreter second run" 1

prepare_case custom_python_changed
ALT_PYTHON="$SHIM_DIR/python-alt"
write_fake_python "$ALT_PYTHON"
export NERSC_MCP_PYTHON="$BOOTSTRAP_PYTHON_SHIM"
run_bootstrap "$DATA_DIR" "$COUNTER"
record_result "custom Python before change" 1
export NERSC_MCP_PYTHON="$ALT_PYTHON"
run_bootstrap "$DATA_DIR" "$COUNTER"
record_result "custom Python changed rebuilds once" 2
run_bootstrap "$DATA_DIR" "$COUNTER"
record_result "custom Python changed then stable" 2

exit "$failures"
