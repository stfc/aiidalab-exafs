#!/bin/bash
# First-boot (and every-boot) setup for aiidalab-mlip app in multi-app container.
(
    set -uo pipefail

    export SHELL=/bin/bash

    HOME_DIR="${HOME:-/home/jovyan}"
    APPS_DIR="${AIIDALAB_APPS:-${HOME_DIR}/apps}"
    mkdir -p "${APPS_DIR}"

    APP_DIR="${APPS_DIR}/aiidalab-mlip"
    if [[ ! -e "${APP_DIR}" ]] && [[ -d "/opt/aiidalab-mlip/app" ]]; then
        # Ensure writable for AppMode temp notebooks
        chmod -R g+rwX /opt/aiidalab-mlip/app 2>/dev/null || true
        ln -sfn /opt/aiidalab-mlip/app "${APP_DIR}"
        echo "Linked aiidalab-mlip app at ${APP_DIR}"
    fi

    # Also symlink as 'mlip' for cleaner launcher naming
    SHORT_APP_DIR="${APPS_DIR}/mlip"
    if [[ ! -e "${SHORT_APP_DIR}" ]] && [[ -d "/opt/aiidalab-mlip/app" ]]; then
        ln -sfn /opt/aiidalab-mlip/app "${SHORT_APP_DIR}"
    fi
)
