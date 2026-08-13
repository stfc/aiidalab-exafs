#!/bin/bash
# First-boot (and every-boot) setup for the aiidalab-feff app.
#
# Dropped into /usr/local/bin/before-notebook.d/ and run as part of the image's
# container startup. The numeric prefix (95) ensures it runs AFTER the base
# image has prepared the home directory and AiiDA (40_prepare-aiida.sh creates
# the AiiDA profile + localhost computer, 60_prepare-aiidalab.sh installs the
# home app, 90_start_aiida_daemon.sh starts the AiiDA daemon).
#
# On every start it:
#   1. Links the app into <home>/apps/aiidalab-feff (from system space), so it
#      stays discoverable even when the home directory is bind-mounted;
#   2. Runs the (idempotent) AiiDA setup: registers localhost "feff" and
#      "python3" codes if missing, and starts the AiiDA daemon if needed;
#   3. (Re)starts the AiiDA REST API used by the app's aiida-explorer button.
#
set -x
export SHELL=/bin/bash

# 1. Expose the app in user space (target the default jovyan home robustly).
# Only link when nothing exists yet, so a user's own install is never replaced.
HOME_DIR="${HOME:-/home/jovyan}"
APPS_DIR="${AIIDALAB_APPS:-${HOME_DIR}/apps}"
APP_DIR="${APPS_DIR}/aiidalab-feff"
if [[ ! -e "${APP_DIR}" ]]; then
    mkdir -p "${APPS_DIR}"
    if [[ -d "/opt/aiidalab-feff/app" ]]; then
        ln -sfn /opt/aiidalab-feff/app "${APP_DIR}"
        echo "Linked aiidalab-feff app at ${APP_DIR}"
    else
        echo "WARNING: app source missing at /opt/aiidalab-feff/app" >&2
    fi
fi

# 2 + 3. Idempotent AiiDA configuration (codes, daemon, REST API).
if /opt/aiidalab-feff/setup-aiida.sh; then
    /opt/aiidalab-feff/start_restapi.sh \
        || echo "WARNING: could not start AiiDA REST API" >&2
else
    echo "WARNING: AiiDA setup for aiidalab-feff failed; see logs above." >&2
fi

# Never propagate a failure to the enclosing startup script (it is sourced by
# start.sh, which runs with `set -e`).
true