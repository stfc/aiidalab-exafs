#!/bin/bash
# AiiDAlab EXAFS startup script.
#
# Launches the aiidalab-exafs deployment image (or any AiiDAlab image) with
# data persistence, an AiiDA profile, and optional port mapping.
# It detects and works with either Docker or Apptainer.
#
#   Usage:
#     ./docker/base/startup.sh [options]
#
#   Options:
#     --image <name|path>     Container image (default: aiidalab-exafs:latest).
#                             As a name it is resolved via docker:// (Apptainer)
#                             or the local daemon (Docker). A *.sif path is used
#                             directly with Apptainer.
#     --engine <docker|apptainer|auto>   Container engine (default: auto).
#     --port <host-port>      Host port for Jupyter (default: 8888).
#     --bind <path>           Host directory to persist as the container's
#                             /home/jovyan (default: $HOME).
#     --no-profile-setup      Never attempt to create an AiiDA profile.
#     -h, --help              Show this help.
set -euo pipefail

IMAGE="${AIIDALAB_EXAFS_IMAGE:-${AIIDALAB_FEFF_IMAGE:-aiidalab-exafs:latest}}"
ENGINE="${AIIDALAB_EXAFS_ENGINE:-${AIIDALAB_FEFF_ENGINE:-auto}}"
PORT="${AIIDALAB_EXAFS_PORT:-${AIIDALAB_FEFF_PORT:-8888}}"
BIND="${AIIDALAB_EXAFS_BIND:-${AIIDALAB_FEFF_BIND:-$HOME}}"
SETUP_PROFILE=auto

usage() {
    awk 'NR > 1 { if (/^#/) { sub(/^# ?/, ""); print } else exit }' "$0"
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --image) IMAGE="$2"; shift 2 ;;
        --engine) ENGINE="$2"; shift 2 ;;
        --port) PORT="$2"; shift 2 ;;
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
PROFILE_CONFIG="$BIND/.aiida/config.json"
AIIDA_PROFILE_NAME="${AIIDA_PROFILE_NAME:-default}"
AIIDA_ENV=()
if [[ "$SETUP_PROFILE" == no ]]; then
    AIIDA_ENV+=(--env "SETUP_DEFAULT_AIIDA_PROFILE=false")
    AIIDA_ENV+=(--env "AIIDA_PROFILE_NAME=${AIIDA_PROFILE_NAME}")
elif [[ -f "$PROFILE_CONFIG" ]]; then
    echo "Existing AiiDA profile detected; reusing it."
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
if [[ "$ENGINE" == "docker" ]]; then
    echo "=== Running AiiDAlab EXAFS with Docker (image: $IMAGE) ==="
    exec docker run -it --rm \
        -p "${PORT}:8888" \
        -v "${BIND}:/home/jovyan" \
        "${AIIDA_ENV[@]}" \
        "$IMAGE"
else
    # Apptainer shares the host network by default
    [[ "$IMAGE" == *.sif ]] && uri="$IMAGE" || uri="docker://${IMAGE}"
    echo "=== Running AiiDAlab EXAFS with Apptainer (image: $uri) ==="
    exec apptainer run --compat --cleanenv --home /home/jovyan \
        --bind "${BIND}:/home/jovyan" \
        "${AIIDA_ENV[@]}" \
        "$uri"
fi
