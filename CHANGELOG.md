# Changelog

Notable changes to the server-deployment skill. Versions follow the annotated
tags pushed to this repository; see `AGENTS.md` for the release process.

## [0.1.2] - 2026-08-24

### Added

- `AGENTS.md` documenting verification commands, coding conventions, and the release process.
- CLI smoke tests for `inventory-server.sh` (`--help`, unknown option, missing value) — suite now 34 tests.
- Root changelog (this file).

### Changed

- CI installs pinned shellcheck **v0.9.0** from koalaman releases instead of the floating apt package, eliminating runner-version drift; the lint step now runs with `-x` to match local validation.

## [0.1.1] - 2026-08-24

### Fixed

- Shellcheck findings in `scripts/inventory-server.sh`, validated against both 0.9.0 (CI/apt) and 0.10 (stable) toolchains:
  - SC2016: intentional literal backticks now carry a disable directive with justification.
  - SC2086: container ID list expanded safely via `mapfile` array instead of unquoted variable (preserving single-invocation semantics).
  - SC2015: best-effort git-root resolution moved `|| true` outside the command substitution.

## [0.1.0] - 2026-08-24

### Added

- User guides: `README.md`, `HOW_TO_USE.md`, `SERVER_CONNECTION_GUIDE.md`, `SERVER_ASSESSMENT_PROTOCOL.md`, `CONFIG_COLLECTION_WORKFLOW.md`.
- Local configuration tooling: `scripts/setup-wizard.py` (interactive collection, hidden secret entry, masked review) and `scripts/load-config.py` (stdlib `.env` loader with permission checks), plus `.env.example`.
- Unit test suite (standard library only) covering profile validation exit codes, env parsing, wizard validators, and secret masking.
- GitHub Actions CI: unittest matrix on Ubuntu and Windows plus shellcheck job.
- `.gitattributes` enforcing LF for shell scripts; `.gitignore` protecting real `.env` files.
