# How to Use the Server Deployment Skill

This guide walks through using the skill end to end: from copying the example profile to a verified production deploy.

Companion guides:

- [SERVER_CONNECTION_GUIDE.md](SERVER_CONNECTION_GUIDE.md) — connecting to the server (SSH/SFTP/RDP): tools, key setup, first connection, troubleshooting
- [SERVER_ASSESSMENT_PROTOCOL.md](SERVER_ASSESSMENT_PROTOCOL.md) — post-connection diagnostic assessment with pass/fail gates
- [CONFIG_COLLECTION_WORKFLOW.md](CONFIG_COLLECTION_WORKFLOW.md) — interactive CLI vs `.env` approaches for collecting connection settings

## Prerequisites

- A Debian server reachable over SSH with a non-root account that has the required permissions.
- SSH access configured via key authentication (recommended) and pinned host keys (`known_hosts`). See the [connection guide](SERVER_CONNECTION_GUIDE.md#5-step-by-step-ssh-connection).
- Secrets stored in your CI secret store or server secret store — **never in this repository**.
- Python 3 (for profile validation and config tooling) and Bash 4+ (for inventory) where you run the scripts.

## Step 1: Install the skill

Place this folder in your agent's skills directory, e.g.:

```
skills/server-deployment/
├── SKILL.md
├── deployment-profile.example.yml
├── scripts/
└── templates/
```

The agent loads `SKILL.md` automatically when you ask it to inventory, bootstrap, deploy, check health, view logs, or roll back.

## Step 2: Create your project profile

Copy the example profile into your application repository and edit it:

```bash
cp deployment-profile.example.yml /path/to/your-app/deployment-profile.yml
```

Then review **every value**. Minimum changes for a typical Docker Compose project:

```yaml
operation: deploy              # start with inventory first
server_scope: multi-project    # or single-project for a dedicated server

project:
  id: my-app                   # unique slug
  repository: owner/my-repo
  production_branch: main

server:
  projects_root: /opt/projects
  deployment_directory: /opt/projects/my-app

ssh:
  host_secret_ref: PRODUCTION_SSH_HOST      # references only — never values
  user_secret_ref: PRODUCTION_SSH_USER
  private_key_secret_ref: PRODUCTION_SSH_PRIVATE_KEY

stack:
  compose_file: docker-compose.yml
  compose_project_name: my-app

containers:
  app:
    container_name: my-app-app   # must be unique on a shared server
    host_port: 3001              # must be unused on the server
    container_port: 3000

networking:
  public_path: /my-app           # must be unique behind the proxy
  upstream_address: 127.0.0.1:3001
```

Rules of thumb:

- Values marked `null` are intentional; fill them only when your stack requires them.
- Every secret stays as a `secret_ref` pointing at an external store (e.g., `PRODUCTION_DATABASE_URL`).
- Names (container, image, volume, network, path, port) must be unique per project on a shared server.

To collect the underlying connection values (server address, username, password) locally, use the guided wizard and verify what it saved — secrets stay masked and out of Git:

```bash
python3 scripts/setup-wizard.py --output .env
python3 scripts/load-config.py --env-file .env
```

See [CONFIG_COLLECTION_WORKFLOW.md](CONFIG_COLLECTION_WORKFLOW.md) for when to prefer interactive entry vs file-based storage.

## Step 3: Validate the profile

```bash
python3 scripts/validate-profile.py --profile deployment-profile.yml --operation deploy
```

Fix any reported errors (exit code `1`) before continuing. Warnings do not block, but read them. Add `--json` for machine-readable output in CI:

```bash
python3 scripts/validate-profile.py --profile deployment-profile.yml --operation deploy --json
```

## Step 4: Inventory the server (read-only)

Run once before any mutation to learn what actually exists on the server:

```bash
# From the server itself
bash scripts/inventory-server.sh --root /opt/projects

# Or over an already-approved SSH connection
ssh deploy@server 'bash -s -- --root /opt/projects' < scripts/inventory-server.sh
```

Check the report for:

- Conflicts with your planned port, path, container/image/volume/network names.
- Whether Docker and Compose are already installed (if not, see bootstrap below).
- Free disk/memory versus your profile thresholds.

For a deeper diagnostic sweep — connectivity baseline, resource thresholds, service health, and a security audit with pass/fail gates — follow [SERVER_ASSESSMENT_PROTOCOL.md](SERVER_ASSESSMENT_PROTOCOL.md).

## Step 5: Bootstrap infrastructure (only if needed)

If the server is missing prerequisites (Docker, directories), set `operation: bootstrap` in the profile and enable what you need:

```yaml
operation: bootstrap
bootstrap:
  enabled: true
  install_docker_if_missing: true
  create_projects_root: true
  require_confirmation: true   # always kept on — approval is mandatory
```

The agent will show you the exact package/directory/proxy changes and **require explicit approval before touching anything**. After bootstrap, re-run inventory and switch the operation back to `deploy`.

Prefer OS-supported package sources over `curl | sh` installers.

## Step 6: Deploy

Set the operation back to deploy and run it through your agent:

```yaml
operation: deploy
```

Ask the agent: *"Deploy my-app using deployment-profile.yml."*

The agent follows this sequence automatically:

1. Validate profile → 2. Identify stack → 3. Local tests/build checks → 4. SSH with pinned host keys → 5. Acquire per-project lock → 6. Read-only conflict preflight (**fails closed** on any conflict) → 7. Fetch approved revision → 8. Verify revision matches → 9. Build new release **before** stopping the old one → 10. Backup before migrations → 11. Run migrations → 12. Switch traffic → 13. Wait for health checks → 14. Smoke-test public path/assets/API/database → 15. Record release + rollback reference → 16. Clean up only its own resources.

You will get a concise status summary:

```text
Deployment: success
Project: my-app
Target: Debian server
Scope: multi-project
Revision: <commit-sha>
Path: /my-app
Health: passed
Conflict preflight: passed
Cloud deployment: disabled
```

Note: deployment never runs `git push`. It consumes whatever commit/tag/branch you have already approved.

## Step 7: Record the deployment

Copy `templates/DEPLOYMENT_CHANGELOG.md` into your app repository and complete one entry per deployment. Fill in the checklist (inventory result, conflicts, verification, rollback reference). Never paste secrets, tokens, keys, or credentialed URLs into the changelog.

## Step 8: Roll back (when needed)

Set the operation and ask the agent to roll back to a previous release:

```yaml
operation: rollback
```

Behavior:

- Application rollback redeploys a known-good immutable image/release (not `git revert`).
- If migrations changed the schema, database restoration is **manual and requires explicit approval**.
- The rollback is recorded with reason, operator, source/target releases, and verification result.

## Common scenarios

### IP-only server without a domain

Keep `networking.domain: null`, enable IP access, and serve under a path prefix:

```yaml
networking:
  domain: null
  ip_access_enabled: true
  public_path: /my-app
  reverse_proxy: nginx
  upstream_address: 127.0.0.1:3001
  tls_enabled: false
```

Your application must be configured with the same base path (e.g., `NEXT_PUBLIC_BASE_PATH: /my-app`). Avoid plain HTTP over raw IPs for sensitive traffic.

### First-time setup on a new server

1. Run `inventory` — nothing exists yet, so confirm the plan is safe.
2. Run `bootstrap` with approval to install Docker/create directories.
3. Re-run `inventory` to confirm state.
4. Run `deploy`.

### Adding another project to a shared server

Repeat Steps 2–7 with a new profile, ensuring every name, port, and public path is unique. The conflict preflight will fail closed if anything collides with an existing project — it will never stop or rename another project's resources automatically.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Validator exits `1` | Missing conditional field or unsafe policy | Read the reported rule; fill or correct the profile |
| Validator exits `2` | File missing or unsupported YAML syntax | Check path; keep to the conservative YAML subset (no anchors/inline maps beyond lists) |
| Preflight blocked: port/path/name conflict | Another project owns the resource | Pick different values; never disable fail-closed |
| Health gate fails | App not listening or wrong base path | Check `internal_url`, ports, and base-path configuration |
| Deploy hangs waiting for lock | Previous deployment still running | Wait, or verify no stale lock on the server |

## Safety reminders

- Never commit real secrets; only `*_secret_ref` names belong in profiles.
- Never let a request override safety invariants (`fail_closed_on_conflict`, `strict_host_key_checking`, `server_only`, `no_implicit_git_push`, `no_automatic_database_rollback`, `require_health_gate`) without an explicit policy change.
- Never use `docker compose down -v` during ordinary deploys — it destroys data volumes.
