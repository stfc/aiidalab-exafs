# Multi-app AiiDAlab container combining aiidalab-exafs and aiidalab-mlip.
#
# Builds on top of aiidalab-exafs:latest (or base) adding MLIP capabilities:
# - aiida-mlip (git main) and janus-core (with mace support)
# - aiidalab-mlip (UI, upstream main, includes Phonon support)
# - auto-setup of janus@localhost code and launcher symlinks

ARG BASE_TAG=aiidalab-exafs:latest
FROM ${BASE_TAG}

USER root

# aiidalab-mlip: stfc/aiidalab-mlip main (0.1.1, includes Phonon support); not on PyPI.
# aiida-mlip: stfc/aiida-mlip main (3e10f0a); the PyPI 0.5.0 release still caps
# aiida-core~=2.7.4, which conflicts with the aiida-core 2.9.x of the base image.
# alc-aiidalab-widgets >=0.2.2 (PyPI) provides widgets.vib_modes / widgets.tables.
# Note: pip install resolves in a single command to prevent downgrading ipywidgets.
ARG MLIP_REF=8f9d1e568b4c88fb8f407807432681bd2e9c5dfb
ARG AIIDA_MLIP_REF=3e10f0afae46dff73733193b9c4e052a455599e1
RUN git clone https://github.com/stfc/aiidalab-mlip.git /opt/aiidalab-mlip/app && \
    cd /opt/aiidalab-mlip/app && \
    git checkout ${MLIP_REF} && \
    pip install --no-cache-dir --no-user --pre \
        "backports.tarfile" \
        "janus-core[mace]" \
        "aiida-core[rest]" \
        "flask-cors" \
        "alc-aiidalab-widgets>=0.2.2" \
        "git+https://github.com/stfc/aiida-mlip.git@${AIIDA_MLIP_REF}" \
        /opt/aiidalab-mlip/app && \
    chown -R ${NB_UID}:${NB_GID} /opt/aiidalab-mlip

# Boot hooks for code provisioning and app linking
COPY docker/full/63_setup_mlip_codes.sh /usr/local/bin/before-notebook.d/63_setup_mlip_codes.sh
COPY docker/full/96_setup-aiidalab-mlip.sh /usr/local/bin/before-notebook.d/96_setup-aiidalab-mlip.sh
RUN chmod +x /usr/local/bin/before-notebook.d/63_setup_mlip_codes.sh \
             /usr/local/bin/before-notebook.d/96_setup-aiidalab-mlip.sh

USER ${NB_UID}
WORKDIR ${HOME}
