#!/usr/bin/env bash
# AiiDAlab FEFF startup script.
#
# Launches the aiidalab-feff deployment image (or any AiiDAlab image) with
# data persistence, an AiiDA profile, and optional REST API port mapping.
# It detects and works with either Docker or Apptainer.
#
#   Usage:
#     ./startup.sh [options]
#
#   Options:
#     --image <name|path>     Container image (default: aiidalab-feff:latest).
#                             As a name it is resolved via docker:// (Apptainer)
#                             or the local daemon (Docker). A *.sif path is used
#                             directly with Apptainer.
#     --engine <docker|apptainer|auto>   Container engine (default: auto).
#     --port <host-port>      Host port for Jupyter (default: 8888).
#     --restapi-port <port>   Host port for the AiiDA REST API (default: 5050,
#                             Docker only; pass 0 to disable).
#     --bind <path>           Host directory to persist as the container's
#                             /home/jovyan (default: $HOME).
#     --no-profile-setup      Never attempt to create an AiiDA profile.
#     -h, --help              Show this help.
#
# If no AiiDA profile exists in the bind path, the script asks for the user's
# details and passes them to the container so it can create a profile on first
# start (see the "AiiDA User Profile Setup" docs).
#
# NOTE: AiiDAlab images run as uid 1000 (jovyan). The --bind directory must be
# readable/writable by uid 1000. On most single-user Linux/macOS systems the
# user's uid is already 1000; otherwise either chown the directory to 1000:100
# or start with `--user root -e CHOWN_HOME=1` so the container fixes ownership
# on first boot.
set -euo pipefail

IMAGE="${AIIDALAB_FEFF_IMAGE:-aiidalab-feff:latest}"
ENGINE="${AIIDALAB_FEFF_ENGINE:-auto}"
PORT="${AIIDALAB_FEFF_PORT:-8888}"
RESTAPI_PORT="${AIIDALAB_FEFF_RESTAPI_PORT:-5050}"
BIND="${AIIDALAB_FEFF_BIND:-$HOME}"
SETUP_PROFILE=auto

usage() {
    # Print the leading "#" header block (usage text) of this script.
    awk 'NR > 1 { if (/^#/) { sub(/^# ?/, ""); print } else exit }' "$0"
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --image) IMAGE="$2"; shift 2 ;;
        --engine) ENGINE="$2"; shift 2 ;;
        --port) PORT="$2"; shift 2 ;;
        --restapi-port) RESTAPI_PORT="$2"; shift 2 ;;
        --bind) BIND="$2"; shift 2 ;;
        --no-profile-setup) SETUP_PROFILE=no; shift ;;
        --help|-h) usage ;;
        *) echo "Unknown argument: $1" >&2; usage ;;
    esac
done

detect_engine() {
    case "$ENGINE" in
        auto) command -v docker &>/dev/null && ENGINE=docker || ENGINE=apptainer ;;
    esac
    command -v "$ENGINE" &>/dev/null || {
        echo "ERROR: container engine '$ENGINE' not found on PATH." >&2
        exit 1
    }
}

# --- Container engine ---
detect_engine

# --- Data persistence bind path ---
if [[ ! -d "$BIND" ]]; then
    echo "ERROR: bind path '$BIND' does not exist." >&2
    exit 1
fi

# --- AiiDA profile ---
# If a profile has already been created, a config.json exists in the core
# .aiida directory of the bind path. Otherwise request user data so the
# container can create a profile on first start.
PROFILE_CONFIG="$BIND/.aiida/config.json"
AIIDA_PROFILE_NAME="${AIIDA_PROFILE_NAME:-default}"
AIIDA_ENV=()
if [[ "$SETUP_PROFILE" == no ]]; then
    AIIDA_ENV+=(--env "SETUP_DEFAULT_AIIDA_PROFILE=false")
    AIIDA_ENV+=(--env "AIIDA_PROFILE_NAME=${AIIDA_PROFILE_NAME}")
elif [[ -f "$PROFILE_CONFIG" ]]; then
    echo "Existing AiiDA profile detected; reusing it."
    # Skip profile creation, keep services + migration on the base image.
    AIIDA_ENV+=(--env "SETUP_DEFAULT_AIIDA_PROFILE=false")
    AIIDA_ENV+=(--env "AIIDA_PROFILE_NAME=${AIIDA_PROFILE_NAME}")
else
    echo "No existing AiiDA profile. Profile creation will be enabled;"
    echo "please provide the details used for the new profile."
    read -r -p "Email [aiida@localhost]: " AIIDA_USER_EMAIL
    AIIDA_USER_EMAIL="${AIIDA_USER_EMAIL:-aiida@localhost}"
    read -r -p "First name [Giuseppe]: " AIIDA_USER_FIRST_NAME
    AIIDA_USER_FIRST_NAME="${AIIDA_USER_FIRST_NAME:-Giuseppe}"
    read -r -p "Last name [Verdi]: " AIIDA_USER_LAST_NAME
    AIIDA_USER_LAST_NAME="${AIIDA_USER_LAST_NAME:-Verdi}"
    read -r -p "Institution [Khedivial]: " AIIDA_USER_INSTITUTION
    AIIDA_USER_INSTITUTION="${AIIDA_USER_INSTITUTION:-Khedivial}"
    AIIDA_ENV+=(--env "SETUP_DEFAULT_AIIDA_PROFILE=true")
    AIIDA_ENV+=(--env "AIIDA_PROFILE_NAME=${AIIDA_PROFILE_NAME}")
    AIIDA_ENV+=(--env "AIIDA_USER_EMAIL=${AIIDA_USER_EMAIL}")
    AIIDA_ENV+=(--env "AIIDA_USER_FIRST_NAME=${AIIDA_USER_FIRST_NAME}")
    AIIDA_ENV+=(--env "AIIDA_USER_LAST_NAME=${AIIDA_USER_LAST_NAME}")
    AIIDA_ENV+=(--env "AIIDA_USER_INSTITUTION=${AIIDA_USER_INSTITUTION}")
fi

# --- Compose and run the container ---
# `--env` is understood by both Docker and Apptainer, so the profile
# environment list is reused verbatim.
if [[ "$ENGINE" == "docker" ]]; then
    port_args=(-p "${PORT}:8888")
    [[ "$RESTAPI_PORT" != 0 ]] && port_args+=(-p "${RESTAPI_PORT}:5000")
    echo "=== Running AiiDAlab FEFF with Docker (image: $IMAGE) ==="
    exec docker run -it --rm \
        "${port_args[@]}" \
        -v "${BIND}:/home/jovyan" \
        "${AIIDA_ENV[@]}" \
        "$IMAGE"
else
    # Apptainer shares the host network by default, so no port mapping is needed.
    [[ "$IMAGE" == *.sif ]] && uri="$IMAGE" || uri="docker://${IMAGE}"
    echo "=== Running AiiDAlab FEFF with Apptainer (image: $uri) ==="
    exec apptainer run --compat --cleanenv --home /home/jovyan \
        --bind "${BIND}:/home/jovyan" \
        "${AIIDA_ENV[@]}" \
        "$uri"
fi