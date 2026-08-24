# Server Deployment Skill

A safe, profile-driven agent skill for deploying applications to servers. It guides an AI agent through **inventorying, bootstrapping, deploying, verifying, and rolling back** applications on approved Debian servers over SSH — without ever touching cloud platforms or pushing code implicitly.

## What it does

| Operation | Purpose | Mutates server? |
|---|---|---|
| `inventory` | Read-only report of OS, tools, Docker resources, ports, projects | No |
| `bootstrap` | Install Docker, create directories, prepare infrastructure (explicit approval required) | Yes |
| `deploy` | Build, migrate, release, and health-check a new version | Yes |
| `rollback` | Return to a known-good previous release | Yes |

## Key safety principles

- **Profile first** — every operation validates a project-specific `deployment-profile.yml` before running.
- **Read-only before mutation** — inventory and conflict checks always run before any change.
- **Fail closed** — any unresolved path, port, image, volume, network, systemd, or proxy conflict blocks deployment.
- **No implicit git push** — deployment consumes an approved branch/tag/commit; never pushes.
- **No secrets in Git or logs** — profiles hold only secret *references* (`PRODUCTION_SSH_HOST`, etc.), never values.
- **Server-only by default** — Vercel, Cloudflare Workers, GitHub Pages, and similar targets are disabled unless explicitly allowlisted.
- **Health is a gate** — a deploy is not successful until configured health/smoke checks pass.
- **Database rollback is manual** — application rollback and schema rollback are separate operations.

## Repository layout

```
deployment-skill/
├── SKILL.md                          # Skill definition loaded by the agent
├── deployment-profile.example.yml    # Copy this per project; review every value
├── SERVER_ASSESSMENT_PROTOCOL.md     # Connection + diagnostic assessment protocol
├── SERVER_CONNECTION_GUIDE.md        # How to connect via SSH/SFTP/RDP, tools & troubleshooting
├── CONFIG_COLLECTION_WORKFLOW.md     # Interactive CLI vs .env config collection, with code
├── CHANGELOG.md                      # Notable changes per release tag
├── scripts/
│   ├── validate-profile.py           # Dependency-free profile validator
│   ├── inventory-server.sh           # Read-only server/project inventory
│   ├── setup-wizard.py               # Interactive CLI that collects connection settings
│   └── load-config.py                # Loads/verifies .env settings with masked output
├── .env.example                      # Template for local connection settings
├── tests/                            # Stdlib unittest suite (no third-party deps)
└── templates/
    └── DEPLOYMENT_CHANGELOG.md       # Audit record template for each deploy
```

## Supported stacks

Stack adapters are selected from actual server/repository inventory — never assumed:

- **Docker Compose** (primary adapter)
- **Dockerfile / Docker Run**
- **systemd services**
- **Language runtimes** (Node.js, Python, Go, Java, PHP)

Kubernetes and other orchestrators are disabled unless a separate profile explicitly enables them.

## Scripts

All scripts are dependency-free and none deploys anything.

### Validate a profile

```bash
python3 scripts/validate-profile.py --profile deployment-profile.yml
python3 scripts/validate-profile.py --profile deployment-profile.yml --operation deploy --json
```

Exit codes: `0` valid · `1` violates safety/requiredness rules · `2` missing/malformed/unparsable.

### Inventory a server

Run locally on the server, or stream it over an already-approved SSH connection:

```bash
bash scripts/inventory-server.sh --root /opt/projects
bash scripts/inventory-server.sh --root /opt/projects --project my-app
ssh deploy@server 'bash -s -- --root /opt/projects' < scripts/inventory-server.sh
```

The report is redacted (credentials stripped) and read-only by design.

### Collect connection settings (local)

Interactive wizard: prompts step-by-step for server address, port, username, and password (input hidden on a real terminal), validates each field, shows a masked review, and saves to a local env file:

```bash
python3 scripts/setup-wizard.py --output .env
```

Load and verify saved settings; secrets are always printed masked:

```bash
python3 scripts/load-config.py --env-file .env
python3 scripts/load-config.py --env-file .env --require SERVER_ADDRESS USER_NAME SERVER_PORT
```

Exit codes (`load-config.py`): `0` ok · `1` missing required keys · `2` file missing/unreadable.

Real `.env` files are git-ignored; only `.env.example` (empty template) is committed. Never commit actual credentials — see [CONFIG_COLLECTION_WORKFLOW.md](CONFIG_COLLECTION_WORKFLOW.md) for the full security trade-offs between interactive entry and file-based storage.

## Getting started

See [HOW_TO_USE.md](HOW_TO_USE.md) for the full step-by-step workflow: copying the profile, filling in values, validating, running your first inventory/bootstrap/deploy, and recording the result.

Additional guides:

- [SERVER_CONNECTION_GUIDE.md](SERVER_CONNECTION_GUIDE.md) — connecting via SSH/SFTP/RDP: tools, key setup, troubleshooting
- [SERVER_ASSESSMENT_PROTOCOL.md](SERVER_ASSESSMENT_PROTOCOL.md) — post-connection diagnostic assessment with pass/fail gates
- [CONFIG_COLLECTION_WORKFLOW.md](CONFIG_COLLECTION_WORKFLOW.md) — CLI vs `.env` config collection approaches with code

## Development

Run the test suite (standard library only, no dependencies to install):

```bash
python -m unittest discover -s tests -v
```

CI (`.github/workflows/ci.yml`) runs the same suite on Ubuntu and Windows and lints shell scripts with shellcheck.
