#!/usr/bin/env bash
# Run a repo's *future* test suite against its code as of a cutoff date.
# Tests that fail are the latent defects / requirements the old code didn't anticipate.
#
# usage: future_tests.sh <github owner/repo> <cutoff YYYY-MM-DD> <package path in repo> <tests dir> [future ref]
# example: future_tests.sh msiemens/tinydb 2026-06-01 tinydb tests
# set INSTALL=1 for packages that need to be pip-installed (e.g. src/ layouts)
# PYTEST_ARGS is passed through to pytest (e.g. --ignore=tests/slow.py)
set -euo pipefail
repo=$1 cutoff=$2 pkg=$3 tests=$4 future=${5:-HEAD}
work=${WORK:-$(mktemp -d)}
name=$(basename "$repo")
[ -d "$work/$name" ] || git clone -q --filter=blob:none "https://github.com/$repo" "$work/$name"
snap=$(git -C "$work/$name" rev-list -1 --before="$cutoff" HEAD)
echo "snapshot $snap ($(git -C "$work/$name" log -1 --format=%cs "$snap")) vs $future"
run() {  # $1 = label, $2 = ref for package code
  d="$work/run-$1"; rm -rf "$d"; mkdir -p "$d"
  git -C "$work/$name" archive "$future" | tar -x -C "$d"           # future tree (tests, config)
  rm -rf "$d/$pkg"; git -C "$work/$name" archive "$2" "$pkg" | tar -x -C "$d"  # swap in code from $2
  [ -n "${INSTALL:-}" ] && (cd "$d" && pip install -q --no-deps -e . >/dev/null 2>&1)
  (cd "$d" && python -m pytest -q -p no:cacheprovider -o addopts="" ${PYTEST_ARGS:-} "$tests" 2>&1 | grep -E '^(FAILED|ERROR)|passed|failed' | sort -u)
}
echo "== future tests on future code (sanity)"; run future "$future"
echo "== future tests on snapshot code";        run snap "$snap"
