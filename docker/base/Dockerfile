# Dockerfile for the aiidalab-exafs AiiDAlab deployment image.
#
# Builds a self-contained AiiDAlab image with the aiidalab-exafs app baked in,
# based on the official AiiDAlab full-stack image (same base as aiidalab-mlip).

# ---------------------------------------------------------------------------
# Stage 1: build the aiida-explorer web app from upstream source
# ---------------------------------------------------------------------------
# Not vendored in the repo. Upstream's demo App.jsx is replaced by our small
# wrapper (same-origin REST API default, full-page layout), and the base path
# is relative so the app works under jupyter-server-proxy's /exafs-explorer/.
FROM node:22-bookworm AS explorer-build
ARG EXPLORER_REF=v0.6.2
RUN npm install -g pnpm@11.5.3 && \
    git clone --depth 1 --branch ${EXPLORER_REF} \
        https://github.com/aiidateam/aiida-explorer.git /src
WORKDIR /src
RUN pnpm install --frozen-lockfile
COPY docker/base/explorer/App.jsx src/App.jsx
RUN VITE_BASE_PATH=./ pnpm build

# ---------------------------------------------------------------------------
# Stage 2: the AiiDAlab image
# ---------------------------------------------------------------------------
FROM aiidalab/full-stack:edge@sha256:a277fedb89cf590c31272fc925e62eddc734b79b6b338cdb18a3021a0b185cef

LABEL maintainer="J. Kane Shenton <kane.shenton@stfc.ac.uk>"
LABEL org.opencontainers.image.source="https://github.com/stfc/aiidalab-exafs"

# Cap BLAS/OpenMP thread pools. The FEFF parser drives larch/numpy/scipy linear
# algebra inside the AiiDA daemon worker, and OpenBLAS defaults to one thread
# per host core: on a 64-core host each parsed job fans a 64-thread pool hot,
# adding tens of cores of load on top of the FEFF jobs themselves (observed as
# a load average of ~70 for a 32-job ensemble). The parse math is tiny
# (100-point spectra), so one thread is plenty; FEFF is a separate Fortran
# binary and is unaffected.
ENV OPENBLAS_NUM_THREADS=1 \
    OMP_NUM_THREADS=1 \
    MKL_NUM_THREADS=1

USER root

# ---------------------------------------------------------------------------
# Dependencies (PyPI pinned releases)
# ---------------------------------------------------------------------------
RUN pip install --no-cache-dir --no-user --pre \
        "aiida-feff>=0.1.0a1" \
        "alc-aiidalab-widgets>=0.1.0"

# ---------------------------------------------------------------------------
# The AiiDAlab app
# ---------------------------------------------------------------------------
# We install the app into /opt (system space) and let the first-boot hook
# symlink it into <home>/apps/exafs. This mirrors how the base image
# installs its own home app and ensures the app remains discoverable even when
# the user's home directory is bind-mounted for data persistence.
COPY . /opt/aiidalab-exafs/app
# Owned by the runtime user: appmode writes temporary notebooks (main-N.ipynb)
# next to the app's main.ipynb and returns 403 if the directory is not writable.
RUN pip install --no-cache-dir --no-user --pre /opt/aiidalab-exafs/app && \
    chown -R ${NB_UID}:${NB_GID} /opt/aiidalab-exafs

# Explorer SPA built in stage 1; found by aiidalab_exafs.proxy.find_explorer_dir.
COPY --from=explorer-build /src/dist/app /opt/aiidalab-exafs/explorer

# ---------------------------------------------------------------------------
# First-boot / every-boot AiiDA setup and code provisioning
# ---------------------------------------------------------------------------
COPY docker/base/05_setup-tmpdir.sh /usr/local/bin/before-notebook.d/05_setup-tmpdir.sh
COPY docker/base/setup-aiida.sh /opt/aiidalab-exafs/setup-aiida.sh
COPY docker/base/62_setup_feff_codes.sh /usr/local/bin/before-notebook.d/62_setup_feff_codes.sh
COPY docker/base/95_setup-aiidalab-exafs.sh /usr/local/bin/before-notebook.d/95_setup-aiidalab-exafs.sh
RUN chmod +x /opt/aiidalab-exafs/*.sh \
    /usr/local/bin/before-notebook.d/*.sh

# ---------------------------------------------------------------------------
# Restore the non-root runtime user
# ---------------------------------------------------------------------------
USER ${NB_UID}
WORKDIR ${HOME}
