#!/usr/bin/env bash
# setup-aiida.sh — run inside the demo container to configure AiiDA for the
# aiidalab-exafs app.  It is idempotent so it is safe to run more than once.
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
AIIDA_DB_HOST="${AIIDA_DB_HOST:-localhost}"
AIIDA_DB_PORT="${AIIDA_DB_PORT:-5432}"
AIIDA_DB_NAME="${AIIDA_DB_NAME:-aiida}"
AIIDA_DB_USER="${AIIDA_DB_USER:-aiida}"
AIIDA_DB_PASS="${AIIDA_DB_PASS:-aiida}"

# ── Locate the FEFF8L executable ───────────────────────────────────────────
# This is our `exafs-feff8l` wrapper, which runs xraylarch's bundled
# `feff8l.sh` under bash. Not xraylarch's own `feff8l` console script: that
# writes `feff8l.log` rather than FEFF's `log.dat`, and aiida-feff reads the
# version banner out of `log.dat`. Resolved here only so that a missing
# executable fails loudly and early; the code registration below re-resolves
# it through the same function.
FEFF_EXE="${FEFF_EXE:-}"
if [ -z "$FEFF_EXE" ]; then
    FEFF_EXE=$("$PYTHON_BIN" -c \
        'from aiidalab_exafs.codes import get_feff_executable; print(get_feff_executable())')
fi

if [ ! -x "$FEFF_EXE" ]; then
    echo "ERROR: FEFF executable not found or not executable at '$FEFF_EXE'" >&2
    exit 1
fi

# ── Wait for an AiiDA profile to become available ──────────────────────────
# The AiiDAlab base image creates the profile when the container starts, so
# this script must be run after the container is alive.
wait_for_profile() {
    local attempts=30
    local i
    for i in $(seq 1 $attempts); do
        if verdi profile show default >/dev/null 2>&1; then
            return 0
        fi
        echo "Waiting for AiiDA profile... ($i/$attempts)"
        sleep 2
    done
    return 1
}

if ! wait_for_profile; then
    # Some AiiDAlab images defer profile creation until the first login.  Try
    # to create a minimal profile ourselves using the standard full-stack
    # PostgreSQL/RabbitMQ credentials.
    echo "WARNING: no default profile found; attempting to create one..."
    mkdir -p "${HOME:-/home/jovyan}/aiida-exafs-repository"
    verdi profile setup core.psql_dos \
        --profile-name default \
        --set-as-default \
        --non-interactive \
        --database-hostname "$AIIDA_DB_HOST" \
        --database-port "$AIIDA_DB_PORT" \
        --database-name "$AIIDA_DB_NAME" \
        --database-username "$AIIDA_DB_USER" \
        --database-password "$AIIDA_DB_PASS" \
        --use-rabbitmq \
        --email "dev@local" \
        --first-name Dev \
        --last-name User \
        --institution Local \
        --repository-uri "file://${HOME:-/home/jovyan}/aiida-exafs-repository" \
        || {
            echo "ERROR: could not create AiiDA profile." >&2
            echo "       Make sure the container has started and services are ready." >&2
            exit 1
        }
fi

verdi profile setdefault default || true

# ── Set up a localhost computer for running calculations ────────────────────
if ! verdi computer show localhost >/dev/null 2>&1; then
    verdi computer setup \
        --label localhost \
        --hostname localhost \
        --transport core.local \
        --scheduler core.direct \
        --work-dir "${HOME:-/home/jovyan}/aiida-exafs-runs" \
        --mpirun-command "" \
        --non-interactive
    verdi computer configure core.local localhost --non-interactive --safe-interval 0
fi

# ── Register the AiiDA codes ───────────────────────────────────────────────
# Delegated to aiidalab_exafs.codes rather than open-coded with `verdi code
# create` here. A stored AiiDA code is immutable, so when the image's FEFF
# executable moves, an existing profile has to have its code retired and
# replaced. A shell `verdi code show || verdi code create` guard cannot do
# that: it sees the code exists, skips, and leaves the stale path in place.
# That is how a corrected image still produced exit 311 on every
# potentials-only run against a persistent $HOME.
"$PYTHON_BIN" - "$FEFF_EXE" "$PYTHON_BIN" <<'PY'
import sys

from aiidalab_exafs.codes import setup_feff_code, setup_python3_code

feff_exe, python_bin = sys.argv[1], sys.argv[2]

code, created = setup_feff_code(executable_path=feff_exe)
print(f"FEFF code   : {code.filepath_executable} ({'created' if created else 'unchanged'})")

code, created = setup_python3_code(executable_path=python_bin)
print(f"Python code : {code.filepath_executable} ({'created' if created else 'unchanged'})")
PY

# ── Start the AiiDA daemon ────────────────────────────────────────────────
if ! verdi daemon status 2>/dev/null | grep -q "Daemon is running"; then
    verdi daemon start 2
fi

echo ""
echo "=== aiidalab-exafs demo ready ==="
echo "  FEFF binary : $FEFF_EXE"
echo "  Python code : $PYTHON_BIN (python3@localhost)"
echo "  verdi shell : verdi shell"
