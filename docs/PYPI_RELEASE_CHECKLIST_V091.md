# PyPI Release Checklist for Media2MD 0.9.1

Use this checklist immediately before triggering `release-pypi.yml`.

## Release decision

- [x] Runtime baseline preserved at `/Users/daniel/media2md`
- [x] Fresh verified runtime backup exists
- [x] Clean source repo reconstructed from signed source ZIP
- [x] Source repo pushed to GitHub `main`
- [x] TestPyPI publication succeeded for `media2md 0.9.1`
- [ ] Explicit human approval to publish to production PyPI

## Source and artifacts

- [x] `pytest` green (`118 passed`)
- [x] `python -m compileall -q src bin tests tools` green
- [x] `python -m build` green
- [x] `python -m twine check dist/*.whl dist/*.tar.gz` green
- [x] Clean wheel install smoke green
- [x] TestPyPI install smoke green
- [x] Wheel SHA matches uploaded TestPyPI wheel
- [x] sdist extracted contents match uploaded TestPyPI sdist contents
- [ ] Decide whether non-reproducible sdist tarball bytes are acceptable for production release

## Known non-blocking quality debt

- [ ] `ruff check .` still red; not fixed in the release-readiness pass
- [ ] `mypy src` still red; not fixed in the release-readiness pass
- [ ] README still contains historical local-install guidance that could be tightened after release

## Trusted publishing

- [x] GitHub workflow `release-pypi.yml` exists on `main`
- [x] GitHub workflow `release-testpypi.yml` exists on `main`
- [x] GitHub environment `pypi` configured by repository admin
- [x] GitHub environment `testpypi` configured by repository admin
- [x] TestPyPI trusted publisher configured and validated by successful publish
- [ ] PyPI trusted publisher confirmed with the same repo/workflow/environment claims

## Final production action

- [ ] Trigger `release-pypi.yml`
- [ ] Confirm workflow success in GitHub Actions
- [ ] Confirm project page appears on PyPI
- [ ] Run production PyPI install smoke in a fresh venv
- [ ] Record final artifact URLs and hashes
