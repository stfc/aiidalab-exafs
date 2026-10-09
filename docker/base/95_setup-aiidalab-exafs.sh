#!/bin/bash
# First-boot (and every-boot) setup for the aiidalab-exafs app.
#
# Dropped into /usr/local/bin/before-notebook.d/ and run as part of the image's
# container startup. The numeric prefix (95) ensures it runs AFTER the base
# image has prepared the home directory and AiiDA.
#
# NOTE: /usr/local/bin/start.sh *sources* this file, so it must not change the
# parent shell's options. `set -u` in particular breaks start.sh's _log(),
# which reads the optional JUPYTER_DOCKER_STACKS_QUIET. Hence the subshell.
(
    set -uo pipefail

    export SHELL=/bin/bash

    HOME_DIR="${HOME:-/home/jovyan}"
    APPS_DIR="${AIIDALAB_APPS:-${HOME_DIR}/apps}"
    mkdir -p "${APPS_DIR}"

    # 1. Expose the app in user space (target the default jovyan home robustly).
    APP_DIR="${APPS_DIR}/exafs"
    if [[ ! -e "${APP_DIR}" ]] && [[ -d "/opt/aiidalab-exafs/app" ]]; then
        ln -sfn /opt/aiidalab-exafs/app "${APP_DIR}"
        echo "Linked aiidalab-exafs app at ${APP_DIR}"
    fi

    # Backward compatibility symlink
    LEGACY_APP_DIR="${APPS_DIR}/aiidalab-exafs"
    if [[ ! -e "${LEGACY_APP_DIR}" ]] && [[ -d "/opt/aiidalab-exafs/app" ]]; then
        ln -sfn /opt/aiidalab-exafs/app "${LEGACY_APP_DIR}"
    fi

    # 2. Idempotent AiiDA configuration (codes, computer, daemon).
    if [[ -f "/opt/aiidalab-exafs/setup-aiida.sh" ]]; then
        if ! /opt/aiidalab-exafs/setup-aiida.sh; then
            echo "WARNING: setup-aiida.sh failed; the app may need manual code setup." >&2
        fi
    fi
)
