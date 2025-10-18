#!/bin/bash

# ============================================
# isA Common - PyPI Release Script
# ============================================
# Builds and publishes the isa-common package to PyPI
#
# File: isA_common/scripts/pypi_release.sh
# Usage: ./scripts/pypi_release.sh [OPTIONS]
#
# Prerequisites:
#   - Python 3.8+
#   - build package (pip install build)
#   - twine package (pip install twine)
#   - PyPI account and API token configured
#
# Options:
#   --test          Upload to TestPyPI instead of PyPI
#   --skip-tests    Skip running tests before build
#   --skip-build    Skip building, only upload existing dist
#   --version VER   Set specific version (updates pyproject.toml and setup.py)
#   --dry-run       Build but don't upload
#   --help          Show this help message

set -e

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DIST_DIR="${PACKAGE_ROOT}/dist"
BUILD_DIR="${PACKAGE_ROOT}/build"
EGG_INFO_DIR="${PACKAGE_ROOT}/isa_common.egg-info"

# Default options
USE_TEST_PYPI=false
SKIP_TESTS=false
SKIP_BUILD=false
DRY_RUN=false
NEW_VERSION=""

# Function to print colored messages
print_header() {
    echo -e "${CYAN}========================================${NC}"
    echo -e "${CYAN}$1${NC}"
    echo -e "${CYAN}========================================${NC}"
}

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Function to check prerequisites
check_prerequisites() {
    print_info "Checking prerequisites..."

    # Check Python
    if ! command -v python3 &> /dev/null; then
        print_error "python3 is required but not installed"
        exit 1
    fi

    # Check build package
    if ! python3 -c "import build" 2>/dev/null; then
        print_error "build package is required but not installed"
        echo "Install with: pip install build"
        exit 1
    fi

    # Check twine package
    if ! python3 -c "import twine" 2>/dev/null; then
        print_error "twine package is required but not installed"
        echo "Install with: pip install twine"
        exit 1
    fi

    # Check git
    if ! command -v git &> /dev/null; then
        print_warning "git is not installed - version checks will be skipped"
    fi

    print_success "All prerequisites met"
}

# Function to get current version from pyproject.toml
get_current_version() {
    if [ -f "${PACKAGE_ROOT}/pyproject.toml" ]; then
        grep '^version' "${PACKAGE_ROOT}/pyproject.toml" | sed 's/version = "\(.*\)"/\1/' | tr -d ' '
    else
        echo "unknown"
    fi
}

# Function to update version in files
update_version() {
    local new_version=$1

    print_info "Updating version to ${new_version}..."

    # Update pyproject.toml
    if [ -f "${PACKAGE_ROOT}/pyproject.toml" ]; then
        sed -i.bak "s/^version = .*/version = \"${new_version}\"/" "${PACKAGE_ROOT}/pyproject.toml"
        rm -f "${PACKAGE_ROOT}/pyproject.toml.bak"
        print_info "Updated pyproject.toml"
    fi

    # Update setup.py
    if [ -f "${PACKAGE_ROOT}/setup.py" ]; then
        sed -i.bak "s/version=\"[^\"]*\"/version=\"${new_version}\"/" "${PACKAGE_ROOT}/setup.py"
        rm -f "${PACKAGE_ROOT}/setup.py.bak"
        print_info "Updated setup.py"
    fi

    print_success "Version updated to ${new_version}"
}

# Function to check for uncommitted changes
check_git_status() {
    if ! command -v git &> /dev/null; then
        return
    fi

    cd "${PACKAGE_ROOT}"

    if [ -d .git ]; then
        if ! git diff-index --quiet HEAD -- 2>/dev/null; then
            print_warning "You have uncommitted changes:"
            git status --short
            echo ""
            read -p "Continue anyway? (y/N) " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                print_error "Aborted by user"
                exit 1
            fi
        fi
    fi
}

# Function to run tests
run_tests() {
    print_info "Running tests..."

    cd "${PACKAGE_ROOT}"

    # Check if pytest is available
    if python3 -c "import pytest" 2>/dev/null; then
        if [ -d "tests" ] || [ -d "isa_common/tests" ]; then
            if python3 -m pytest; then
                print_success "All tests passed"
            else
                print_error "Tests failed"
                exit 1
            fi
        else
            print_warning "No tests directory found, skipping tests"
        fi
    else
        print_warning "pytest not installed, skipping tests"
    fi
}

# Function to clean build artifacts
clean_build() {
    print_info "Cleaning previous build artifacts..."

    cd "${PACKAGE_ROOT}"

    # Remove dist directory
    if [ -d "${DIST_DIR}" ]; then
        rm -rf "${DIST_DIR}"
        print_info "Removed ${DIST_DIR}"
    fi

    # Remove build directory
    if [ -d "${BUILD_DIR}" ]; then
        rm -rf "${BUILD_DIR}"
        print_info "Removed ${BUILD_DIR}"
    fi

    # Remove egg-info directory
    if [ -d "${EGG_INFO_DIR}" ]; then
        rm -rf "${EGG_INFO_DIR}"
        print_info "Removed ${EGG_INFO_DIR}"
    fi

    # Remove __pycache__ directories
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find . -type f -name "*.pyc" -delete 2>/dev/null || true

    print_success "Build artifacts cleaned"
}

# Function to build package
build_package() {
    print_info "Building package..."

    cd "${PACKAGE_ROOT}"

    # Build using python -m build
    if python3 -m build; then
        print_success "Package built successfully"
    else
        print_error "Build failed"
        exit 1
    fi

    # List built files
    print_info "Built files:"
    ls -lh "${DIST_DIR}"
}

# Function to check package with twine
check_package() {
    print_info "Checking package with twine..."

    cd "${PACKAGE_ROOT}"

    if python3 -m twine check "${DIST_DIR}"/*; then
        print_success "Package check passed"
    else
        print_error "Package check failed"
        exit 1
    fi
}

# Function to upload to PyPI
upload_package() {
    local repository=$1

    if [ "${DRY_RUN}" = true ]; then
        print_warning "DRY RUN: Skipping upload"
        print_info "Would upload to: ${repository}"
        print_info "Files:"
        ls -lh "${DIST_DIR}"
        return
    fi

    print_info "Uploading to ${repository}..."

    cd "${PACKAGE_ROOT}"

    if [ "${repository}" = "testpypi" ]; then
        # Upload to TestPyPI
        if python3 -m twine upload --repository testpypi "${DIST_DIR}"/*; then
            print_success "Package uploaded to TestPyPI"
            echo ""
            print_info "Install with:"
            echo "  pip install --index-url https://test.pypi.org/simple/ isa-common"
        else
            print_error "Upload to TestPyPI failed"
            exit 1
        fi
    else
        # Upload to PyPI
        if python3 -m twine upload "${DIST_DIR}"/*; then
            print_success "Package uploaded to PyPI"
            echo ""
            print_info "Install with:"
            echo "  pip install isa-common"
        else
            print_error "Upload to PyPI failed"
            exit 1
        fi
    fi
}

# Function to create git tag
create_git_tag() {
    if ! command -v git &> /dev/null; then
        return
    fi

    cd "${PACKAGE_ROOT}"

    if [ ! -d .git ]; then
        return
    fi

    local version=$(get_current_version)
    local tag="v${version}"

    print_info "Creating git tag: ${tag}"

    # Check if tag already exists
    if git rev-parse "${tag}" >/dev/null 2>&1; then
        print_warning "Tag ${tag} already exists"
        return
    fi

    # Create tag
    if git tag -a "${tag}" -m "Release ${version}"; then
        print_success "Created tag: ${tag}"
        print_info "Push tag with: git push origin ${tag}"
    else
        print_warning "Failed to create git tag"
    fi
}

# Function to print summary
print_summary() {
    local version=$(get_current_version)
    local repository=$1

    echo ""
    print_header "Release Summary"
    echo ""
    print_info "Package:       isa-common"
    print_info "Version:       ${version}"
    print_info "Repository:    ${repository}"

    if [ "${DRY_RUN}" = true ]; then
        print_warning "Mode:          DRY RUN (no upload performed)"
    else
        print_success "Mode:          LIVE (package uploaded)"
    fi

    echo ""
    print_info "Distribution files:"
    ls -lh "${DIST_DIR}" 2>/dev/null | tail -n +2 | awk '{print "  " $9 " (" $5 ")"}'

    echo ""

    if [ "${DRY_RUN}" = false ]; then
        if [ "${repository}" = "testpypi" ]; then
            print_info "TestPyPI URL:"
            echo "  https://test.pypi.org/project/isa-common/${version}/"
            echo ""
            print_info "Install command:"
            echo "  pip install --index-url https://test.pypi.org/simple/ isa-common==${version}"
        else
            print_info "PyPI URL:"
            echo "  https://pypi.org/project/isa-common/${version}/"
            echo ""
            print_info "Install command:"
            echo "  pip install isa-common==${version}"
        fi
    fi

    echo ""
    print_success "Release process completed!"
}

# Function to show help
show_help() {
    cat << EOF
Usage: $0 [OPTIONS]

Build and publish isa-common package to PyPI.

Options:
  --test              Upload to TestPyPI instead of PyPI
  --skip-tests        Skip running tests before build
  --skip-build        Skip building, only upload existing dist
  --version VERSION   Set specific version (updates pyproject.toml and setup.py)
  --dry-run           Build but don't upload
  --help              Show this help message

Examples:
  # Test release to TestPyPI
  $0 --test

  # Release to production PyPI
  $0

  # Release specific version
  $0 --version 0.2.0

  # Dry run (build only, no upload)
  $0 --dry-run

  # Quick upload (skip tests and use existing build)
  $0 --skip-tests --skip-build

Prerequisites:
  pip install build twine

PyPI Configuration:
  Configure your PyPI credentials in ~/.pypirc or use environment variables:

  For PyPI:
    export TWINE_USERNAME=__token__
    export TWINE_PASSWORD=pypi-...

  For TestPyPI:
    export TWINE_USERNAME=__token__
    export TWINE_PASSWORD=pypi-...
    export TWINE_REPOSITORY_URL=https://test.pypi.org/legacy/

EOF
}

# Main execution
main() {
    # Parse command line arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --test)
                USE_TEST_PYPI=true
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
            --version)
                NEW_VERSION="$2"
                shift 2
                ;;
            --dry-run)
                DRY_RUN=true
                shift
                ;;
            --help)
                show_help
                exit 0
                ;;
            *)
                print_error "Unknown option: $1"
                echo "Use --help for usage information"
                exit 1
                ;;
        esac
    done

    print_header "isA Common - PyPI Release"
    echo ""

    # Show current configuration
    local current_version=$(get_current_version)
    print_info "Current version: ${current_version}"

    if [ -n "${NEW_VERSION}" ]; then
        print_info "Target version:  ${NEW_VERSION}"
    fi

    if [ "${USE_TEST_PYPI}" = true ]; then
        print_info "Repository:      TestPyPI"
    else
        print_info "Repository:      PyPI (production)"
    fi

    if [ "${DRY_RUN}" = true ]; then
        print_warning "Mode:            DRY RUN"
    fi

    echo ""

    # Confirm if releasing to production PyPI
    if [ "${USE_TEST_PYPI}" = false ] && [ "${DRY_RUN}" = false ]; then
        print_warning "You are about to release to production PyPI!"
        read -p "Are you sure? (y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            print_error "Aborted by user"
            exit 1
        fi
    fi

    # Execute release steps
    check_prerequisites

    # Update version if specified
    if [ -n "${NEW_VERSION}" ]; then
        update_version "${NEW_VERSION}"
    fi

    check_git_status

    # Run tests unless skipped
    if [ "${SKIP_TESTS}" = false ]; then
        run_tests
    else
        print_warning "Skipping tests"
    fi

    # Build package unless skipped
    if [ "${SKIP_BUILD}" = false ]; then
        clean_build
        build_package
        check_package
    else
        print_warning "Skipping build"

        # Check if dist directory exists
        if [ ! -d "${DIST_DIR}" ] || [ -z "$(ls -A ${DIST_DIR})" ]; then
            print_error "No distribution files found in ${DIST_DIR}"
            print_error "Cannot skip build when no files exist"
            exit 1
        fi
    fi

    # Upload package
    if [ "${USE_TEST_PYPI}" = true ]; then
        upload_package "testpypi"
    else
        upload_package "pypi"
    fi

    # Create git tag if successful and not dry run
    if [ "${DRY_RUN}" = false ]; then
        create_git_tag
    fi

    # Print summary
    if [ "${USE_TEST_PYPI}" = true ]; then
        print_summary "TestPyPI"
    else
        print_summary "PyPI"
    fi
}

# Run main function
main "$@"
