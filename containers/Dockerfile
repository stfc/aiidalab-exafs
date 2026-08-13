# Dockerfile for the aiidalab-feff AiiDAlab deployment image.
#
# Builds a self-contained AiiDAlab image with the aiidalab-feff app baked in,
# based on the STFC ALC-UX Python 3.10 port of the official AiiDAlab
# full-stack image (ghcr.io/stfc/alc-ux/base:py310).
#
#   # official AiiDAlab full-stack image, capped at Python 3.9:
#   # FROM aiidalab/full-stack:latest
#   # Python 3.10 port used here:
#   FROM ghcr.io/stfc/alc-ux/base:py310
#
# Install:
#   docker build -f containers/Dockerfile -t aiidalab-feff:latest .
#   (or just run ./containers/build.sh)
#
# Run:
#   docker run -it --rm -p 8888:8888 -v "$HOME":/home/jovyan aiidalab-feff:latest
#   (or use ./containers/startup.sh)

FROM ghcr.io/stfc/alc-ux/base:py310

USER root

# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------
# aiida-feff is not published to PyPI, and although alc-aiidalab-widgets is, we
# install both from source so the image stays consistent with the packages used
# for development. ``--pre`` allows the alpha pre-releases of these plugins.
RUN pip install --no-cache-dir --no-user --pre \
        "git+https://github.com/stfc/aiida-feff.git" \
        "git+https://github.com/stfc/alc-aiidalab-widgets.git"

# ---------------------------------------------------------------------------
# The AiiDAlab app
# ---------------------------------------------------------------------------
# We install the app into /opt (system space) and let the first-boot hook
# symlink it into <home>/apps/aiidalab-feff. This mirrors how the base image
# installs its own home app and ensures the app remains discoverable even when
# the user's home directory is bind-mounted for data persistence (a fresh bind
# would otherwise shadow anything baked into /home/jovyan/apps).
COPY . /opt/aiidalab-feff/app
RUN pip install --no-cache-dir --no-user --pre /opt/aiidalab-feff/app

# ---------------------------------------------------------------------------
# First-boot / every-boot AiiDA setup
# ---------------------------------------------------------------------------
# The base image's before-notebook.d hooks already create the AiiDA profile +
# localhost computer (40_prepare-aiida.sh) and start the daemon
# (90_start_aiida_daemon.sh). Our hook (95_*, numeric ordering) runs after them
# to register the FEFF + python3 codes and start the REST API the app needs.
# All referenced scripts are idempotent, so they are safe on every start.
COPY containers/setup-aiida.sh /opt/aiidalab-feff/setup-aiida.sh
COPY containers/start_restapi.sh /opt/aiidalab-feff/start_restapi.sh
COPY containers/95_setup-aiidalab-feff.sh \
    /usr/local/bin/before-notebook.d/95_setup-aiidalab-feff.sh
RUN chmod +x /opt/aiidalab-feff/*.sh \
    /usr/local/bin/before-notebook.d/95_setup-aiidalab-feff.sh

# ---------------------------------------------------------------------------
# FEFF8l launcher shell-compatibility fix
# ---------------------------------------------------------------------------
# xraylarch ships feff8l.sh with a "#!/bin/sh" shebang but uses the bash-only
# variable ${BASH_SOURCE[0]} to locate its own directory. Under /bin/sh the
# substitution is empty, so every feff8l_* binary is invoked from the job's
# working directory instead of larch/bin/linux64 -> FEFF produces no xmu.dat
# and every calculation fails with exit status 310. Baking the shebang fix into
# the image ensures all runs are unaffected.
RUN F="$(find /opt/conda -path '*/larch/bin/linux64/feff8l.sh' 2>/dev/null | head -n1)"; \
    if [ -n "$F" ] && head -n1 "$F" | grep -q '#!/bin/sh'; then \
        sed -i '1s|#!/bin/sh|#!/usr/bin/env bash|' "$F" && echo "patched FEFF8 launcher: $F"; \
    else \
        echo "FEFF8 launcher not found or already patched: ${F:-none}"; \
    fi

# ---------------------------------------------------------------------------
# Restore the non-root runtime user
# ---------------------------------------------------------------------------
USER ${NB_UID}
WORKDIR ${HOME}