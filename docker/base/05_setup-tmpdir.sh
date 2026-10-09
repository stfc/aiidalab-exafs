#!/bin/bash
# Ensure TMPDIR points to user persistent home so calculations staging large
# model files don't exhaust the 64MB /tmp tmpfs under Apptainer --compat.
export TMPDIR="${HOME:-/home/jovyan}/.tmp"
mkdir -p "${TMPDIR}" 2>/dev/null || true
