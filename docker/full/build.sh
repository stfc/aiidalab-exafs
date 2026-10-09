#!/bin/bash
# Build the multi-app aiidalab-exafs:full image (aiidalab-exafs + aiidalab-mlip).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

TAG="aiidalab-exafs:full"
BASE_TAG="${BASE_TAG:-aiidalab-exafs:latest}"

ENGINE="${AIIDALAB_EXAFS_ENGINE:-}"
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

echo "=== Building ${TAG} using base ${BASE_TAG} with ${ENGINE} ==="
"${ENGINE}" build \
    --build-arg BASE_TAG="${BASE_TAG}" \
    -f "${SCRIPT_DIR}/Dockerfile" \
    -t "${TAG}" \
    "${REPO_ROOT}"

echo
echo "Built ${TAG}"
