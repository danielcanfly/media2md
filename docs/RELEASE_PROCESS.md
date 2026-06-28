# Release Process

This document describes the recommended release workflow for Media2MD.

It separates three different things that are easy to mix up:

- source-repo changes
- local runtime changes
- public package publication

## Key Rules

1. A GitHub push does not publish to PyPI.
2. A new PyPI release requires a new version number.
3. Do not change runtime behavior casually on a released baseline without re-testing.
4. Treat `/Users/daniel/Github/media2md` as the source repository.
5. Treat the local runtime/project tree as a separate deployment target.

## Current Paths

- Source repo: `/Users/daniel/Github/media2md`
- Runtime tree: `/Users/daniel/media2md`
- Legacy compatibility symlink: `/Users/daniel/instagram-to-md` -> `/Users/daniel/media2md`

## Release States

There are three common states:

### 1. Source updated only

You can:

- change code
- change docs
- change tests
- bump the version in source
- push to GitHub

Without:

- publishing to PyPI
- updating the runtime tree

This is valid and often useful.

### 2. Source updated and runtime refreshed locally

You can:

- update the source repo
- test or deploy the new code into the local runtime tree

Without:

- publishing to PyPI

This is useful when validating behavior before a public release.

### 3. Public PyPI release

This requires:

- source changes committed
- version bumped
- tests/build checks passing
- manual publish workflow trigger

## Versioning

PyPI does not allow re-uploading the same version number.

That means:

- `0.9.1` can only be published once
- any new public release must use a new version such as `0.9.2`

You may still bump the version in source and choose not to publish yet.

## Typical Release Workflow

### A. Prepare source changes

Work in the source repo:

```bash
cd /Users/daniel/Github/media2md
```

Make code, docs, or test changes.

### B. Bump version

Update all version-bearing files consistently.

At minimum, check:

- `pyproject.toml`
- `src/media2md/__init__.py`
- `src/media2md/bootstrap.py`
- bundle/runtime scripts that carry `VERSION = "..."`

### C. Run validation

Recommended checks:

```bash
pytest
python -m compileall -q src bin tests tools
python -m build
python -m twine check dist/*.whl dist/*.tar.gz
```

Recommended smoke checks:

- clean install from local wheel
- command smoke such as `media2md version`
- any targeted regression checks needed by the release

### D. Commit and push

```bash
git add .
git commit -m "Release prep for vX.Y.Z"
git push origin main
```

### E. Publish to TestPyPI or PyPI

Publishing is manual through GitHub Actions:

- `release-testpypi.yml`
- `release-pypi.yml`

Publishing should only happen after validation is complete.

## Runtime Deployment Workflow

The runtime tree is separate from the source repo.

Source edits in:

- `/Users/daniel/Github/media2md`

do not automatically update:

- `/Users/daniel/media2md`

If you want runtime and source to match, you need an explicit refresh step.

That refresh can be done by:

- reinstalling from a wheel
- reinstalling from source
- using a controlled runtime update path
- copying/deploying code intentionally

Do not assume GitHub pushes update the runtime.

## Managed Runtime Migration Reality

When the packaged CLI boots a managed runtime for the first time, it may seed
config from a legacy local project registry.

Today that means Media2MD can carry forward config such as:

- `auth_profiles.json`
- `social2md.json`
- `creator_policies.json`
- `provider_policies.json`

from a legacy local project like:

- `/Users/daniel/media2md`
- `/Users/daniel/instagram-to-md`

through a previously registered project root.

This is helpful, but it is not magic. There is an important distinction:

- config files are portable
- browser session decryption is environment-dependent

In practice:

- a managed runtime can inherit the selected browser/profile settings
- a managed runtime can inherit exported cookie snapshot paths
- a fully isolated new `HOME` may still fail `auth verify` because browser
  cookie decryption depends on the real logged-in macOS user session, keychain,
  and browser profile storage

Typical failure modes in an isolated verification environment include:

- Instagram/TikTok: `Unable to get key for cookie decryption`
- YouTube: selected browser profile path does not exist in the isolated home

So the correct expectation is:

- migration should preserve config intent
- auth re-verification may still require the real user environment

This is especially relevant when doing package smoke tests in a temporary home
directory or CI-like local sandbox.

## Practical Smoke-Test Expectations

For package-first validation, split checks into two buckets.

### Portable checks

These should work in a clean or isolated environment:

- wheel install
- `media2md version`
- managed runtime bootstrap
- legacy project config seeding
- command routing
- provider Doctor flows that support anonymous or public-first access
- runtime-limit pause/resume behavior

### Environment-bound checks

These may require the real logged-in desktop environment:

- `auth verify instagram`
- `auth verify tiktok`
- `auth verify youtube`
- any path that depends on decrypting live browser cookies from the local OS

If those fail only inside an isolated `HOME`, do not immediately classify that
as a package regression. Re-run the same verification under the real user home
before concluding that auth is broken.

## Recommended Team Habit

Use this mental model:

- GitHub repo = source of truth for development
- runtime tree = deployed local environment
- PyPI = public distribution channel

They are related, but they are not automatically the same thing.

## Suggested Release Checklist

Before publishing a new version:

- source changes reviewed
- version bumped everywhere needed
- tests green
- build green
- artifact hashes recorded
- install smoke green
- runtime impact understood
- publish decision explicit

## What Does Not Trigger PyPI

These do not publish to PyPI by themselves:

- editing code
- editing README
- committing locally
- pushing to GitHub
- merging to `main`

PyPI changes only when you explicitly run the release workflow and publish a new version.
