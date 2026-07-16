# AiiDAlab FEFF

AiiDAlab app for FEFF-based EXAFS and MD-EXAFS calculations.

## Usage

Launch the app from AiiDAlab or run the notebook:

```python
from aiidalab_feff.main import main
main()
```

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
