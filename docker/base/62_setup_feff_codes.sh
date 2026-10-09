#!/bin/bash
# Provision the localhost computer and the feff/python3 codes.
#
# Deliberately calls the same helper the in-app "Set up FEFF code" button uses,
# so container boots and registry installs converge on one implementation. A
# declarative `verdi code create --config` YAML cannot be used here because the
# localhost computer does not exist yet at this point in the boot sequence.
#
# NOTE: /usr/local/bin/start.sh *sources* this file, so it must not change the
# parent shell's options. `set -u` in particular breaks start.sh's _log(),
# which reads the optional JUPYTER_DOCKER_STACKS_QUIET. Hence the subshell.
(
    set -uo pipefail

    if ! python3 -c "from aiidalab_exafs.codes import setup_feff_code, setup_python3_code
feff, created = setup_feff_code()
print(('Created' if created else 'Found') + f' code {feff.full_label} -> {feff.filepath_executable}')
py, created = setup_python3_code()
print(('Created' if created else 'Found') + f' code {py.full_label}')"; then
        echo "WARNING: automatic FEFF code setup failed. Use the 'Set up FEFF code'" >&2
        echo "         button on the Resources step of the app to retry." >&2
    fi
)
