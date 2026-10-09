.. _aiidalab_exafs_home:

AiiDAlab EXAFS Documentation
============================

Welcome to the **AiiDAlab EXAFS** application documentation.

`aiidalab-exafs` provides an interactive, provenance-tracked graphical user interface
for running FEFF calculations and Debye-Waller factor analysis from molecular dynamics
trajectories within `AiiDAlab <https://aiidalab.materialscloud.org/>`_.

Features
--------

- **Interactive 5-Step Wizard**: Structure selection, FEFF calculation settings, compute resource configuration, live calculation progress, and spectra results exploration.
- **Debye-Waller Analysis**: Real-time screening and exploration of mean square relative displacement (MSRD) via an integrated Marimo application.
- **AiiDA Provenance Browser**: Same-origin integration with ``aiida-explorer`` for visualizing full calculation graphs.
- **Cloud & HPC Deployment**: Ready for deployment on STFC ADA (Apptainer) and local workstations via Docker/Podman.

.. toctree::
   :maxdepth: 2
   :caption: Guides & Documentation:

   getting_started
   deployment

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
