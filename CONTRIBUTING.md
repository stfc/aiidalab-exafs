# Contributing Guidelines

Thank you for contributing to `aiidalab-exafs`!

## Contribution Workflow

1. **Issues**: Open an issue describing bugs, enhancements, or proposed changes before starting large refactors.
2. **Branching**: Branch from `main` (e.g. `feature/my-feature` or `bugfix/issue-123`).
3. **Coding Standards**:
   - Follow PEP 8 guidelines.
   - Run `pre-commit run --all-files` (or `ruff check .` and `ruff format .`).
   - Use Google-style docstrings.
4. **Testing**:
   - Ensure new functionality has accompanying unit tests.
   - Respect repository test conventions (CI runs tests with PostgreSQL + RabbitMQ services).
5. **Pull Requests**:
   - Submit PRs against `main`.
   - Ensure CI checks pass.
