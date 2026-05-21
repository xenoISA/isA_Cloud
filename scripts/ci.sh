#!/usr/bin/env bash
#
# scripts/ci.sh — Local CI gate for isA_Cloud
# ============================================
# Runs the same checks the team relies on before shipping — lint + unit-layer
# tests — entirely on your machine. Built so the team can verify and ship
# safely even when GitHub Actions is unavailable (Actions billing has been
# failing org-wide). Tracking: xenoISA/isA_Cloud#287 (epic #284).
#
# WHAT IT RUNS
#   1. Lint   — black --check + flake8 on the isa_common Python library.
#               By default lint is scoped to files changed vs origin/main so
#               the gate does not retroactively fail on the repo's pre-existing
#               lint backlog. Pass --all to lint the whole library.
#   2. Tests  — pytest unit + component layers (fast; no infrastructure).
#               Mirrors the `test` job in .github/workflows/ci-cd.yml.
#
# Slow / integration / smoke tests are intentionally excluded — this gate is
# meant to be fast enough to run on every push.
#
# USAGE
#   scripts/ci.sh            # lint changed files + run unit/component tests
#   scripts/ci.sh --all      # lint the entire isa_common library
#   scripts/ci.sh --no-lint  # tests only
#   scripts/ci.sh --help     # this help
#
# EXIT CODE
#   0  all checks passed
#   1  one or more checks failed (lint or tests)
#
# This script is also invoked by the pre-push git hook — see .githooks/pre-push.
#
set -uo pipefail

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
# pwd -P resolves symlinks (e.g. macOS /tmp -> /private/tmp) so the path
# matches what `black` expects when checking files are within the project.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
SDK_DIR="${REPO_ROOT}/isA_common"
PYTHON="${PYTHON:-python3}"
BASE_REF="${CI_BASE_REF:-origin/main}"

LINT_SCOPE="changed"   # changed | all
RUN_LINT=1

for arg in "$@"; do
  case "$arg" in
    --all)     LINT_SCOPE="all" ;;
    --no-lint) RUN_LINT=0 ;;
    -h|--help)
      sed -n '2,33p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "ci.sh: unknown argument '$arg' (try --help)" >&2
      exit 1
      ;;
  esac
done

# ANSI colours (disabled when stdout is not a TTY)
if [ -t 1 ]; then
  RED=$'\033[31m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; BOLD=$'\033[1m'; RESET=$'\033[0m'
else
  RED=''; GREEN=''; YELLOW=''; BOLD=''; RESET=''
fi

FAILED=0

step()  { printf '\n%s==> %s%s\n' "${BOLD}" "$1" "${RESET}"; }
pass()  { printf '%s  PASS%s  %s\n' "${GREEN}" "${RESET}" "$1"; }
fail()  { printf '%s  FAIL%s  %s\n' "${RED}"   "${RESET}" "$1"; FAILED=1; }
skip()  { printf '%s  SKIP%s  %s\n' "${YELLOW}" "${RESET}" "$1"; }

# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------
if [ ! -d "${SDK_DIR}" ]; then
  echo "ci.sh: cannot find isA_common at ${SDK_DIR}" >&2
  exit 1
fi

printf '%s isA_Cloud local CI gate %s\n' "${BOLD}" "${RESET}"
printf 'repo: %s\n' "${REPO_ROOT}"

# ---------------------------------------------------------------------------
# 1. Lint  (black --check + flake8)
# ---------------------------------------------------------------------------
# black config: line-length=100 (isA_common/pyproject.toml [tool.black]).
# flake8 args mirror .pre-commit-config.yaml: max-line-length=120, ignore
# E501/W503/E203.
if [ "${RUN_LINT}" -eq 1 ]; then
  step "Lint (black --check + flake8)"

  # LINT_FILES holds repo-root-relative paths. black/flake8 are invoked with
  # the repo root as cwd so relative paths resolve cleanly on all platforms.
  LINT_FILES=()
  if [ "${LINT_SCOPE}" = "all" ]; then
    echo "  scope: entire isa_common library"
    while IFS= read -r f; do LINT_FILES+=("$f"); done < <(
      cd "${REPO_ROOT}" &&
        find isA_common/isa_common isA_common/tests -name '*.py' -type f 2>/dev/null
    )
  else
    # Diff vs the merge-base with BASE_REF; fall back to staged/working changes.
    DIFF_BASE=""
    if git -C "${REPO_ROOT}" rev-parse --verify --quiet "${BASE_REF}" >/dev/null; then
      DIFF_BASE="$(git -C "${REPO_ROOT}" merge-base HEAD "${BASE_REF}" 2>/dev/null || true)"
    fi
    if [ -n "${DIFF_BASE}" ]; then
      echo "  scope: Python files changed vs ${BASE_REF} (${DIFF_BASE:0:8})"
      DIFF_RANGE="${DIFF_BASE}"
    else
      echo "  scope: ${BASE_REF} unavailable — linting uncommitted changes only"
      DIFF_RANGE="HEAD"
    fi
    while IFS= read -r f; do
      [ -n "$f" ] && [ -f "${REPO_ROOT}/$f" ] && LINT_FILES+=("$f")
    done < <(git -C "${REPO_ROOT}" diff --name-only --diff-filter=ACMR "${DIFF_RANGE}" -- '*.py')
  fi

  if [ "${#LINT_FILES[@]}" -eq 0 ]; then
    skip "lint — no Python files in scope"
  else
    echo "  ${#LINT_FILES[@]} file(s) in scope"

    if ( cd "${REPO_ROOT}" && "${PYTHON}" -m black --check --quiet --line-length=100 "${LINT_FILES[@]}" ); then
      pass "black --check"
    else
      fail "black --check — run: ${PYTHON} -m black --line-length=100 <files>"
    fi

    if ( cd "${REPO_ROOT}" && "${PYTHON}" -m flake8 --max-line-length=120 --extend-ignore=E501,W503,E203 "${LINT_FILES[@]}" ); then
      pass "flake8"
    else
      fail "flake8 — fix the violations listed above"
    fi
  fi
else
  step "Lint"
  skip "lint disabled (--no-lint)"
fi

# ---------------------------------------------------------------------------
# 2. Unit + component tests
# ---------------------------------------------------------------------------
# Mirrors the `test` job in .github/workflows/ci-cd.yml:
#   pytest tests/unit/ tests/component/
# These layers use mocked dependencies — no Docker / infrastructure needed.
step "Unit + component tests (pytest)"
if ( cd "${SDK_DIR}" && "${PYTHON}" -m pytest tests/unit/ tests/component/ -q --tb=short -p no:cacheprovider ); then
  pass "pytest tests/unit/ tests/component/"
else
  fail "pytest tests/unit/ tests/component/"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo
if [ "${FAILED}" -eq 0 ]; then
  printf '%s==> CI GATE PASSED%s — safe to push\n' "${GREEN}${BOLD}" "${RESET}"
  exit 0
else
  printf '%s==> CI GATE FAILED%s — fix the items above (or push with --no-verify to bypass)\n' "${RED}${BOLD}" "${RESET}"
  exit 1
fi
