#!/bin/bash

# ISA Common PyPI Release Script
#
# This script handles building and publishing the ISA Common package to PyPI
#
# Usage:
#   ./pypi_release.sh [OPTIONS]
#
# Options:
#   -v, --version VERSION  Version to release (default: auto from pyproject.toml)
#   -e, --env ENV          Environment to load credentials from (default: dev)
#   --test-pypi            Release to TestPyPI instead of PyPI
#   --skip-tests           Skip running tests before release
#   --skip-build           Skip building (use existing dist/)
#   --dry-run              Build but don't publish
#   -h, --help             Show this help message

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
NC='\033[0m' # No Color

# Default values
VERSION=""
ENV="dev"
TEST_PYPI=false
SKIP_TESTS=false
SKIP_BUILD=false
DRY_RUN=false
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Logging functions
log_info() {
    echo -e "${BLUE}ℹ ${NC}$1"
}

log_success() {
    echo -e "${GREEN}✓ ${NC}$1"
}

log_warning() {
    echo -e "${YELLOW}⚠  ${NC}$1"
}

log_error() {
    echo -e "${RED}✗ ${NC}$1"
}

log_step() {
    echo -e "${MAGENTA}▶${NC}  $1"
}

show_help() {
    cat << EOF
ISA Common PyPI Release Script

Usage: ./pypi_release.sh [OPTIONS]

Options:
  -v, --version VERSION  Version to release (default: auto from pyproject.toml)
  -e, --env ENV          Environment to load credentials from (default: dev)
  --test-pypi            Release to TestPyPI instead of PyPI
  --skip-tests           Skip running tests before release
  --skip-build           Skip building (use existing dist/)
  --dry-run              Build but don't publish
  -h, --help             Show this help message

Examples:
  # Standard release (uses version from pyproject.toml)
  ./pypi_release.sh

  # Release specific version
  ./pypi_release.sh -v 0.1.5

  # Test release to TestPyPI
  ./pypi_release.sh --test-pypi

  # Dry run (build only, no publish)
  ./pypi_release.sh --dry-run

  # Quick release (skip tests)
  ./pypi_release.sh --skip-tests

Environment Variables:
  PYPI_API_TOKEN         PyPI API token (loaded from .env)
  TEST_PYPI_API_TOKEN    TestPyPI API token (optional)

EOF
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -v|--version)
            VERSION="$2"
            shift 2
            ;;
        -e|--env)
            ENV="$2"
            shift 2
            ;;
        --test-pypi)
            TEST_PYPI=true
            shift
            ;;
        --skip-tests)
            SKIP_TESTS=true
            shift
            ;;
        --skip-build)
            SKIP_BUILD=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Change to project root
cd "$PROJECT_ROOT"

echo ""
log_info "═══════════════════════════════════════════════════════════"
log_info "  ISA Common PyPI Release"
log_info "═══════════════════════════════════════════════════════════"
echo ""

# Load environment file
ENV_FILE="$PROJECT_ROOT/.env"

if [[ ! -f "$ENV_FILE" ]]; then
    log_error "Environment file not found: $ENV_FILE"
    log_info "Create $ENV_FILE with PYPI_API_TOKEN variable"
    exit 1
fi

log_info "Loading credentials from: $ENV_FILE"
set -a
source "$ENV_FILE"
set +a

# Check for PyPI token
if [[ "$TEST_PYPI" == "true" ]]; then
    if [[ -z "$TEST_PYPI_API_TOKEN" ]]; then
        log_error "TEST_PYPI_API_TOKEN not found in $ENV_FILE"
        log_info "Get your TestPyPI token from: https://test.pypi.org/manage/account/token/"
        exit 1
    fi
    PYPI_TOKEN="$TEST_PYPI_API_TOKEN"
    PYPI_REPO="https://test.pypi.org/legacy/"
    PYPI_NAME="TestPyPI"
else
    if [[ -z "$PYPI_API_TOKEN" ]]; then
        log_error "PYPI_API_TOKEN not found in $ENV_FILE"
        log_info "Get your PyPI token from: https://pypi.org/manage/account/token/"
        exit 1
    fi
    PYPI_TOKEN="$PYPI_API_TOKEN"
    PYPI_REPO="https://upload.pypi.org/legacy/"
    PYPI_NAME="PyPI"
fi

log_success "Credentials loaded"

# Get version from pyproject.toml if not specified
if [[ -z "$VERSION" ]]; then
    if [[ -f "pyproject.toml" ]]; then
        VERSION=$(grep '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/')
        log_info "Auto-detected version from pyproject.toml: $VERSION"
    elif [[ -f "setup.py" ]]; then
        VERSION=$(grep 'version=' setup.py | sed 's/.*version="\([^"]*\)".*/\1/')
        log_info "Auto-detected version from setup.py: $VERSION"
    else
        log_error "Could not find version in pyproject.toml or setup.py"
        exit 1
    fi
else
    log_info "Using specified version: $VERSION"

    # Update version files with new version
    log_step "Updating version to $VERSION..."

    if [[ -f "pyproject.toml" ]]; then
        sed -i.bak "s/^version = .*/version = \"$VERSION\"/" pyproject.toml
        rm pyproject.toml.bak
        log_success "Version updated in pyproject.toml"
    fi

    if [[ -f "setup.py" ]]; then
        sed -i.bak "s/version=\"[^\"]*\"/version=\"$VERSION\"/" setup.py
        rm setup.py.bak
        log_success "Version updated in setup.py"
    fi
fi

# Validate version format
if [[ ! "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[a-zA-Z0-9]+)?$ ]]; then
    log_error "Invalid version format: $VERSION"
    log_info "Version should be in format: X.Y.Z or X.Y.Z-alpha/beta/rc1"
    exit 1
fi

echo ""
log_info "Release Configuration:"
log_info "  Package:      isa-common"
log_info "  Version:      $VERSION"
log_info "  Repository:   $PYPI_NAME"
log_info "  Skip Tests:   $SKIP_TESTS"
log_info "  Skip Build:   $SKIP_BUILD"
log_info "  Dry Run:      $DRY_RUN"
echo ""

# Check if version already exists on PyPI
log_step "Checking if version $VERSION already exists on PyPI..."
if pip index versions isa-common 2>/dev/null | grep -q "$VERSION"; then
    log_error "Version $VERSION already exists on PyPI!"
    log_info "Please bump the version or use -v flag with a new version"
    exit 1
fi
log_success "Version $VERSION is available"

# Check for uncommitted changes
if [[ -n $(git status --porcelain) ]]; then
    log_warning "You have uncommitted changes!"
    git status --short
    echo ""
    read -p "Continue anyway? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Release cancelled"
        exit 0
    fi
fi

# Check if we're on main/master branch
CURRENT_BRANCH=$(git branch --show-current)
if [[ "$CURRENT_BRANCH" != "main" ]] && [[ "$CURRENT_BRANCH" != "master" ]] && [[ ! "$CURRENT_BRANCH" =~ ^release/ ]]; then
    log_warning "You're not on main/master/release branch (current: $CURRENT_BRANCH)"
    read -p "Continue anyway? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Release cancelled"
        exit 0
    fi
fi

# Install/check build tools
log_step "Checking build tools..."
if ! python3 -c "import build" 2>/dev/null; then
    log_warning "build package not found, installing..."
    pip install build
fi
log_success "Build tools ready"

# Run tests (unless skipped)
if [[ "$SKIP_TESTS" == "false" ]]; then
    log_step "Running tests..."

    if python3 -c "import pytest" 2>/dev/null; then
        # Check if there are any test files
        TEST_FILES=$(find . -name "test_*.py" -o -name "*_test.py" 2>/dev/null | head -1)
        if [[ -n "$TEST_FILES" ]]; then
            log_info "Running tests with pytest..."
            if python3 -m pytest -v; then
                log_success "Tests passed"
            else
                log_error "Tests failed!"
                log_info "Fix tests before releasing or use --skip-tests"
                exit 1
            fi
        else
            log_warning "No test files found, skipping tests..."
        fi
    else
        log_warning "pytest not installed, skipping tests..."
    fi
else
    log_warning "Skipping tests as requested"
fi

# Clean previous builds
if [[ "$SKIP_BUILD" == "false" ]]; then
    log_step "Cleaning previous builds..."
    rm -rf dist/ build/ *.egg-info 2>/dev/null || true
    log_success "Cleaned"

    # Build package
    log_step "Building package..."
    echo ""

    if python3 -m build; then
        echo ""
        log_success "Package built successfully"
    else
        echo ""
        log_error "Build failed!"
        exit 1
    fi

    # List built files
    echo ""
    log_info "Built files:"
    ls -lh dist/
    echo ""

    # Verify build - check for either underscore or hyphen naming
    if [[ ! -f "dist/isa_common-${VERSION}.tar.gz" ]] && [[ ! -f "dist/isa-common-${VERSION}.tar.gz" ]] && \
       [[ ! -f "dist/isa_common-${VERSION}-py3-none-any.whl" ]] && [[ ! -f "dist/isa-common-${VERSION}-py3-none-any.whl" ]]; then
        log_error "Expected build artifacts not found!"
        exit 1
    fi
    log_success "Build verified"
else
    log_warning "Skipping build as requested, using existing dist/"

    if [[ ! -d "dist" ]] || [[ -z "$(ls -A dist/)" ]]; then
        log_error "No existing build found in dist/"
        exit 1
    fi
fi

# Check package with twine
log_step "Checking package with twine..."
if ! command -v twine &> /dev/null; then
    log_info "Installing twine..."
    pip install twine
fi

if twine check dist/*; then
    log_success "Package check passed"
else
    log_error "Package check failed!"
    exit 1
fi

# Dry run exit
if [[ "$DRY_RUN" == "true" ]]; then
    echo ""
    log_success "═══════════════════════════════════════════════════════════"
    log_success "  Dry Run Complete!"
    log_success "═══════════════════════════════════════════════════════════"
    echo ""
    log_info "Package built successfully but not published (--dry-run)"
    log_info "To publish, run without --dry-run flag"
    echo ""
    exit 0
fi

# Final confirmation
echo ""
log_warning "═══════════════════════════════════════════════════════════"
log_warning "  Ready to Publish"
log_warning "═══════════════════════════════════════════════════════════"
echo ""
log_info "Package:      isa-common"
log_info "Version:      $VERSION"
log_info "Repository:   $PYPI_NAME"
echo ""
read -p "Publish to $PYPI_NAME? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    log_info "Release cancelled"
    exit 0
fi

# Publish to PyPI
log_step "Publishing to $PYPI_NAME..."
echo ""

if twine upload --repository-url "$PYPI_REPO" -u __token__ -p "$PYPI_TOKEN" dist/*; then
    echo ""
    log_success "═══════════════════════════════════════════════════════════"
    log_success "  Successfully Published!"
    log_success "═══════════════════════════════════════════════════════════"
    echo ""
    log_info "Package:      isa-common"
    log_info "Version:      $VERSION"
    log_info "Repository:   $PYPI_NAME"
    echo ""

    if [[ "$TEST_PYPI" == "true" ]]; then
        log_info "View at: https://test.pypi.org/project/isa-common/$VERSION/"
        echo ""
        log_info "Install with:"
        echo "  pip install -i https://test.pypi.org/simple/ isa-common==$VERSION"
    else
        log_info "View at: https://pypi.org/project/isa-common/$VERSION/"
        echo ""
        log_info "Install with:"
        echo "  pip install isa-common==$VERSION"
    fi
    echo ""

    # Tag git commit
    if git rev-parse --git-dir > /dev/null 2>&1; then
        read -p "Create git tag v$VERSION? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            git tag -a "v$VERSION" -m "Release v$VERSION"
            log_success "Git tag created: v$VERSION"

            read -p "Push tag to remote? (y/N): " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                git push origin "v$VERSION"
                log_success "Tag pushed to remote"
            fi
        fi
    fi

    echo ""
    log_success "Release complete! 🚀"
    echo ""

else
    echo ""
    log_error "Publication failed!"
    log_info "Check your credentials and try again"
    exit 1
fi
