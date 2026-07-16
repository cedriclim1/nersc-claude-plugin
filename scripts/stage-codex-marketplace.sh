#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
    echo "usage: $0 TARGET_DIRECTORY" >&2
    exit 2
fi

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TARGET=$1

if [ -e "$TARGET/plugins/nersc" ] || [ -e "$TARGET/.agents/plugins/marketplace.json" ]; then
    echo "refusing to replace an existing staged marketplace under $TARGET" >&2
    echo "choose a new empty target; staged marketplaces are immutable snapshots" >&2
    exit 1
fi

if ! git -C "$ROOT" diff --quiet; then
    echo "refusing to stage with unstaged tracked changes; stage or revert them first" >&2
    exit 1
fi
if [ -n "$(git -C "$ROOT" ls-files --others --exclude-standard)" ]; then
    echo "refusing to stage with untracked files; add or remove them first" >&2
    exit 1
fi

TREE=$(git -C "$ROOT" write-tree)
mkdir -p "$TARGET/plugins/nersc" "$TARGET/.agents/plugins"
git -C "$ROOT" archive "$TREE" | tar -x -C "$TARGET/plugins/nersc"
cp "$ROOT/packaging/codex-marketplace.json" "$TARGET/.agents/plugins/marketplace.json"

echo "staged NERSC marketplace at $TARGET from Git tree $TREE"
echo "next: codex plugin marketplace add $TARGET"
