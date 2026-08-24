# Agent Working Conventions

Instructions for AI agents and contributors working in this repository.

## Verification commands (run before claiming work is done)

```bash
# Full test suite (stdlib only, no installs needed)
python -m unittest discover -s tests -v

# Bash syntax check (Windows: use Git-bash)
bash -n scripts/inventory-server.sh

# Lint shell scripts — CI pins v0.9.0; test against it, not only latest
shellcheck -x scripts/inventory-server.sh
```

Local Windows shellcheck binaries used during development live under
`C:\Users\kashe\AppData\Local\Temp\kilo\shellcheck\` (`shellcheck.exe` = 0.10 stable,
`v9\shellcheck.exe` = 0.9.0). CI runs the 0.9.0 build; a script that passes only on
0.10 will break CI.

## Conventions

- **Commits**: imperative mood, concise, matching existing history
  (e.g. `Add profile validator and server inventory`). Never commit secrets,
  real `.env` files, or `.kilo/` working artifacts.
- **Python**: standard library only — no third-party runtime dependencies.
  Type-hinted, `from __future__ import annotations`, argparse CLIs with
  documented exit codes. Script filenames use hyphens; tests load them via
  `importlib.util.spec_from_file_location` because hyphenated names cannot be
  imported directly.
- **Bash**: `set -Eeuo pipefail`, read-only by design for inventory tooling,
  LF line endings enforced via `.gitattributes`. Validate against both
  shellcheck 0.9 and 0.10 before pushing.
- **Safety invariants** (from SKILL.md): fail closed on conflicts, no implicit
  git push, no secret values in Git/logs/profiles — only `*_secret_ref` names.
- **Docs**: user-facing guides at repo root (`README.md`, `HOW_TO_USE.md`,
  `SERVER_CONNECTION_GUIDE.md`, `SERVER_ASSESSMENT_PROTOCOL.md`,
  `CONFIG_COLLECTION_WORKFLOW.md`) must stay consistent when scripts change.

## Release process

1. All verification commands pass locally.
2. Commit(s) pushed to `main`; CI run concludes `success` across all jobs.
3. Annotated tag `vX.Y.Z` created and pushed. Never move existing tags;
   cut a new patch version instead.
