#!/usr/bin/env bash
# Build the aiidalab-feff AiiDAlab deployment image.
#
# Usage:  ./containers/build.sh [--tag <tag>] [--no-cache] [-- <docker build args>]
# Default tag: aiidalab-feff:latest
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

TAG="aiidalab-feff:latest"
BUILD_ARGS=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --tag)
            TAG="$2"
            shift 2
            ;;
        --no-cache)
            BUILD_ARGS+=("--no-cache")
            shift
            ;;
        *)
            BUILD_ARGS+=("$1")
            shift
            ;;
    esac
done

# Use podman if docker is not available.
ENGINE="${AIIDALAB_FEFF_ENGINE:-}"
if [[ -z "$ENGINE" ]]; then
    if command -v docker &>/dev/null; then
        ENGINE=docker
    elif command -v podman &>/dev/null; then
        ENGINE=podman
    else
        echo "ERROR: neither docker nor podman found." >&2
        exit 1
    fi
fi

echo "=== Building ${TAG} with ${ENGINE} ==="
"${ENGINE}" build \
    -f "${SCRIPT_DIR}/Dockerfile" \
    -t "${TAG}" \
    "${BUILD_ARGS[@]}" \
    "${REPO_ROOT}"

echo
echo "Built ${TAG}"
echo "Run it with:"
echo "  ${ENGINE} run -it --rm -p 8888:8888 -v \"\$HOME\":/home/jovyan ${TAG}"
echo "or use ./containers/startup.sh (or an AiiDAlab startup script wrapper)."