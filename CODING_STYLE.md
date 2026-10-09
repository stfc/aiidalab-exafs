# Coding Style Guide

`aiidalab-exafs` adheres to strict formatting and linting rules enforced via `ruff` and `mypy`.

## Standards

- **Python Version**: Python >= 3.10
- **Formatting**: Enforced via `ruff format` (100 character line length, double quotes).
- **Linting**: Enforced via `ruff check` (rule sets: E, W, F, I, UP, B, C4, SIM, N, D, PL).
- **Docstrings**: Google convention.
- **Type Hints**: Static typing annotations for public APIs and complex data models checked by `mypy`.
