#!/usr/bin/env bash
#
# scripts/install-hooks.sh — wire up the tracked git hooks for isA_Cloud
# ======================================================================
# Points git at the version-controlled .githooks/ directory so the pre-push
# CI gate (scripts/ci.sh) runs before every push. Tracking: isA_Cloud#287.
#
# This is a convenience wrapper. The install is a single git command:
#
#     git config core.hooksPath .githooks
#
# Run this script once per clone:
#
#     scripts/install-hooks.sh
#
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "${REPO_ROOT}"

git config core.hooksPath .githooks
chmod +x .githooks/* scripts/ci.sh 2>/dev/null || true

echo "Git hooks installed: core.hooksPath -> .githooks"
echo "  pre-push  ->  runs scripts/ci.sh (lint + unit-layer tests)"
echo
echo "Bypass a single push with: git push --no-verify"
echo "Uninstall with:            git config --unset core.hooksPath"
