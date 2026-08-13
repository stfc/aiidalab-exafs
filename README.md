# AiiDAlab FEFF

AiiDAlab app for FEFF-based EXAFS and MD-EXAFS calculations.

## Usage

Launch the app from AiiDAlab or run the notebook:

```python
from aiidalab_feff.main import main
main()
```

## Experimental references

The **Spectrum** results tab accepts experimental files supported by Larch,
including plain text/CSV, XDI, and Athena project files. Uploaded files are
stored in AiiDA before Larch imports the selected spectrum, preserving both
the source upload and the import parameters. Select an Athena group when a
project contains more than one spectrum. For unlabelled or ambiguously labelled
text files, choose **Specify column labels** and enter Larch labels such as
`k,chi` or `energy,mu,mu0` in file-column order.

Use the live `S₀²` and `ΔE₀` controls to compare the selected FEFF spectrum
against the experimental reference in χ(k) and χ(R). **Save scaled
simulation** stores the current adjusted FEFF spectrum as a provenance-linked
`XasData` node; it never modifies the original calculation output.

## Development

Install in editable mode:

```bash
pip install -e ".[testing]"
```

Run linting:

```bash
ruff check aiidalab_feff/ tests/
ruff format aiidalab_feff/ tests/
```

Run tests:

```bash
pytest
```
