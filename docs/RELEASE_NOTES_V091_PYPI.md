# Media2MD 0.9.1

Media2MD 0.9.1 is the first public Python package release of the signed private-production baseline.

## Highlights

- CLI-first media-to-Markdown workflow for Instagram, YouTube, and TikTok
- Local-first runtime with structured Markdown output and machine-readable status surfaces
- Verified browser-profile auth flow with explicit human boundaries for passwords, 2FA, CAPTCHA, and challenges
- Exact-catalog protection for TikTok rebuilds and bounded transport fallback behavior
- SQLite-backed state backup and verification commands
- Agent-ready status, creator, auth, doctor, and scheduler interfaces

## Release state

- Version: `0.9.1`
- Python requirement: `>=3.11`
- TestPyPI validation: passed
- Build and Twine metadata checks: passed
- Clean install smoke test: passed

## Notes

- This release preserves the v0.9.1 runtime behavior that was validated in the signed closure evidence.
- The public release path is currently Python-first. npm and Homebrew publication were intentionally removed from the active release workflow.
- `ruff` and `mypy` are still tracked as follow-up quality debt and were not treated as blockers for the packaging release path.
