.. _deployment:

Deployment Guide
================

Services and ports
------------------

The app runs three auxiliary services. None of them binds a host port: each
listens on ``127.0.0.1`` and is reached through Jupyter's authenticated
reverse proxy, so the only port the container exposes is 8888.

=====================  ==========================  ============================
Proxy path             Service                     Started by
=====================  ==========================  ============================
``exafs-marimo/``      Marimo app server           ``marimo run notebooks/``
``exafs-restapi/``     AiiDA REST API              ``verdi restapi``
``exafs-explorer/``    ``aiida-explorer`` web app  ``proxy.py`` (static server)
=====================  ==========================  ============================

``jupyter-server-proxy`` discovers these from the
``jupyter_serverproxy_servers`` entry points and starts them lazily on first
request. A freshly pip-installed copy of the app only registers its entry
points once the Jupyter server restarts.

The explorer is served through the proxy rather than Jupyter's ``/files/``
endpoint on purpose: ``/files/`` responses carry
``Content-Security-Policy: sandbox allow-scripts``, which gives the page an
opaque origin, and an opaque-origin document cannot send the Jupyter session
cookie to the proxied REST API.

ADA (STFC Cloud Workspace)
--------------------------

ADA uses Apptainer with host networking and isolated temporary storage. Launch the container image using the canonical ADA command:

.. code-block:: bash

   apptainer run --compat --cleanenv \
       --bind ${HOME}:/home/jovyan \
       --home /home/jovyan \
       docker://ghcr.io/stfc/aiidalab-exafs/base:latest

Or run with the provided startup script:

.. code-block:: bash

   ./scripts/startup.sh --docker-image=ghcr.io/stfc/aiidalab-exafs/base:latest

Local Workstation (Docker / Podman)
-----------------------------------

Run the container locally with Docker:

.. code-block:: bash

   docker run -it --rm -p 8888:8888 -v "$HOME":/home/jovyan ghcr.io/stfc/aiidalab-exafs/base:latest

Live Development (aiidalab-launch)
----------------------------------

For live development with editable mounts:

.. code-block:: bash

   python3 docker/base/launch.py --dev
