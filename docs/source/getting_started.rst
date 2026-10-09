.. _getting_started:

Getting Started
===============

Installation
------------

Within an existing AiiDAlab environment:

.. code-block:: bash

   pip install aiidalab-exafs

Or install from the AiiDAlab App Store by searching for ``exafs``.

Launching the App
-----------------

1. Navigate to the AiiDAlab home page.
2. Click the **AiiDAlab EXAFS** tile, or open ``main.ipynb`` directly.
3. If running on a stock AiiDAlab image, visit the **Resources** tab or click **Set up FEFF code** to register the local FEFF8L executable.

Workflow Overview
-----------------

1. **Structure**: Upload a CIF, XYZ, or trajectory file, or query the Materials Project / local database.
2. **Settings**: Select absorbing elements, edges (K, L1, L2, L3), and calculation parameters.
3. **Review & Run**: Select your compute target (Localhost or SCARF cluster) and submit the calculation.
4. **Progress**: Monitor calculation steps and view process state.
5. **Results**: Inspect computed :math:`\mu(E)` and :math:`\chi(k)` spectra, adjust Fourier transform parameters, and compare against experimental data.
