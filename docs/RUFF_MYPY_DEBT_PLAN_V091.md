# Ruff and Mypy Debt Plan for Media2MD 0.9.1

This plan documents the intentional choice not to block the PyPI release on the current `ruff` and `mypy` red gates.

## Current state

- `ruff check .`: fails with large-volume style and legacy-format issues
- `ruff format --check .`: would reformat many legacy files
- `mypy src`: fails with import-path assumptions, missing optional dependency stubs, and type debt in legacy runtime scripts

## Why this was not fixed in the release pass

- The failures are broad and structural rather than one or two isolated regressions.
- A full style/type cleanup would create a large diff against the signed v0.9.1 baseline.
- The immediate release objective was to establish a safe Python publication path without changing runtime behavior.

## Recommended follow-up sequence

1. Split lint/type work from release work.
2. Start with packaging-facing files only:
   - `.github/workflows/*.yml`
   - `pyproject.toml`
   - `tests/test_package.py`
   - `tools/build_release_assets.py`
3. Add scoped Ruff configuration if needed so legacy historical installer files are excluded from the first pass.
4. Add scoped mypy configuration for runtime script import layout and optional dependencies.
5. Fix import-path errors before deeper type narrowing.
6. Treat optional dependency stubs such as `PyYAML` and `instaloader` explicitly rather than leaving them implicit.
7. Expand to bundle scripts only after the release path remains stable.

## Target outcome

- `ruff check` green on actively maintained packaging and release surfaces first
- `mypy` green on importable package modules before bundle-script deep typing
- No runtime-behavior drift introduced merely to satisfy style tooling
