#!/bin/bash
# Provision localhost "janus" and "python3" codes for aiidalab-mlip if needed.
(
    set -uo pipefail

    # Only run if aiida_mlip is available
    if ! python3 -c "import aiida_mlip" &>/dev/null; then
        exit 0
    fi

    # Ensure profile loaded
    python3 -c "
from aiida.manage import get_manager
if get_manager().get_profile() is None:
    from aiida import load_profile
    load_profile()

import shutil, sys, os
from aiida.orm import load_computer, load_code, InstalledCode
from aiida.common.exceptions import NotExistent

computer = load_computer('localhost')

# 1. Janus code
janus_exe = shutil.which('janus') or os.path.join(os.path.dirname(sys.executable), 'janus')
if janus_exe and os.path.isfile(janus_exe):
    try:
        code = load_code('janus@localhost')
        if str(code.filepath_executable) != str(janus_exe):
            code.label = f'janus-legacy-{code.pk}'
            raise NotExistent()
    except NotExistent:
        c = InstalledCode(
            label='janus',
            computer=computer,
            filepath_executable=janus_exe,
            description='Janus MLIP executable from janus-core',
        )
        c.store()
        print(f'Created code janus@localhost -> {janus_exe}')
" || echo "WARNING: automated janus code setup failed." >&2
)
