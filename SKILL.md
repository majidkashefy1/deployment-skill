---
name: server-deployment
description: Safely inventory, bootstrap, deploy, verify, and roll back applications on approved servers using a project-specific profile.
---

# Server Deployment Skill

Use this skill when a user asks to inventory a server, prepare a server, deploy an application, check deployment health, show deployment logs, or roll back a release.

This is a **server-only deployment skill**. It does not deploy to Vercel, Cloudflare Workers, GitHub Pages, or any other cloud provider unless a separate, explicit profile changes the target allowlist. The default target is an approved Debian server reached through SSH.

## Core principles

1. **Profile first**: load and validate `deployment-profile.yml` before executing project-specific commands.
2. **Inventory before assumptions**: identify the project’s actual stack; do not assume Docker, Compose, Node.js, Nginx, a domain, or a database exists.
3. **Read-only first**: inventory and conflict checks must run before checkout, build, restart, package installation, or proxy changes.
4. **Fail closed**: any unresolved path, port, image, container, volume, network, systemd, or proxy conflict blocks deployment.
5. **No implicit code push**: deployment consumes an approved branch, tag, or commit. Never run `git push` as part of deployment.
6. **No secret values in Git or logs**: use secret references and redact environment files, URLs with credentials, passwords, tokens, and private keys.
7. **No cross-project interference**: never stop, delete, overwrite, or reuse another project’s resources.
8. **Explicit infrastructure changes**: installing Docker, installing packages, creating directories, changing firewall rules, or changing Nginx requires `operation: bootstrap` and explicit approval.
9. **Health is a gate**: a deployment is not successful until the configured health and smoke checks pass.
10. **Database rollback is manual by default**: application rollback and schema rollback are separate operations.

## Profile loading and precedence

Load configuration in this order, with later values overriding earlier values:

1. Skill defaults.
2. Repository profile: `skills/server-deployment/deployment-profile.yml` or the project’s configured profile path.
3. Environment profile, such as `production`.
4. Explicit user request for the current operation.
5. CI variables and secret references.

Never let a user request override these safety invariants without an explicit, visible policy change:

- `fail_closed_on_conflict: true`
- `strict_host_key_checking: true`
- `server_only: true`
- `no_implicit_git_push: true`
- `no_automatic_database_rollback: true`
- `require_health_gate: true`

The example profile in this folder is intentionally named `deployment-profile.example.yml`. Copy it to a project-specific profile only after reviewing it.

## Required, nullable, and conditional settings

Every profile setting must be classified as one of the following:

- **Required**: deployment cannot start without it.
- **Nullable**: intentionally absent for this project or environment.
- **Defaulted**: omitted values use a documented safe default.
- **Conditional**: required only when a stack, operation, or feature enables it.
- **Secret reference**: points to an external secret; it is never the secret itself.

### Always required for `deploy`

- Project identifier and environment.
- Approved deployment target and server scope.
- Repository and branch/tag/commit selection.
- Server directory.
- SSH host and authentication configuration.
- Stack adapter.
- Conflict policy.
- Build/deploy or release commands for that adapter.
- Health verification policy.
- Rollback reference policy.

### Conditionally required

| Setting | Required when |
|---|---|
| `dockerfile` | The selected adapter builds a Docker image. |
| `compose_file` | The selected adapter is Docker Compose. |
| `systemd_unit` | The selected adapter is systemd. |
| `image_name` | The deployment creates or pulls container images. |
| `host_port` | A service publishes a port on the server. |
| `container_port` | A containerized service listens on a port. |
| `public_path` | The service is exposed through a URL path. |
| `reverse_proxy` | Traffic is routed by Nginx, Caddy, Traefik, or another proxy. |
| `domain` | Domain-based routing or trusted public TLS is enabled. |
| `database_url` | The application uses a database. |
| `migration_command` | The application has managed schema migrations. |
| `backup_command` | Persistent data requires an application/database backup. |
| `worker` or `queue` settings | Background processing is enabled. |
| Docker installation settings | `operation: bootstrap` is explicitly selected. |

### Commonly nullable

- Domain name for IP-only deployments.
- TLS certificate when the server is not serving HTTPS.
- Dockerfile for systemd or language-runtime deployments.
- Compose file for Docker Run or systemd deployments.
- Cache, queue, worker, and scheduler settings when unused.
- Seed command after initial data setup.
- Autoscaling settings on a single-server deployment.
- External monitoring and chat notifications.
- `install_docker_if_missing` when Docker is already managed outside this skill.

A nullable value must be represented explicitly as `null` or `enabled: false`; do not silently guess.

## Operations

The profile selects one operation at a time:

```yaml
operation: inventory # inventory | bootstrap | deploy | rollback
```

### `inventory`

Read-only operation. It may inspect:

- Operating system, version, kernel, architecture, CPU, memory, disk, and timezone.
- SSH connectivity and available administrative permissions.
- Docker, Podman, Compose, systemd, Nginx, Caddy, and other installed tools.
- Direct project directories under `projects_root`.
- Git remotes, branches, and revisions with credentials redacted.
- Docker containers, images, volumes, networks, and Compose ownership labels.
- Listening ports and proxy routes.

It must not install packages, fetch application code, build images, create directories, edit proxy files, restart services, or modify data.

The report must contain project names, detected stack markers, resource ownership, and recommended profile fields. It must not contain `.env` contents, secret values, private keys, or credential-bearing URLs.

### `bootstrap`

Infrastructure preparation is a separate, explicitly approved operation.

Before mutating the server:

1. Confirm the operating system and architecture.
2. Confirm the requested project scope: dedicated or shared.
3. Display the package, directory, permission, firewall, and proxy changes.
4. Require explicit approval.
5. Install Docker/Compose only when the profile requests it and the tools are missing.
6. Create only the configured directories.
7. Apply least-privilege ownership and permissions.
8. Re-run inventory and conflict checks.
9. Record all changes in the deployment changelog.

Do not use an unreviewed `curl | sh` installer. Prefer the operating system’s supported package source or a pinned, documented installation method.

### `deploy`

Run this sequence:

1. Validate the profile and requiredness conditions.
2. Inspect the local repository and identify the selected stack.
3. Run local tests/build checks required by the profile.
4. Establish the SSH connection using pinned host keys.
5. Acquire a per-project deployment lock on the server.
6. Run the read-only server inventory and fail-closed conflict preflight.
7. Fetch the approved revision on the server or transfer an approved artifact.
8. Verify the checked-out revision matches the requested commit/tag.
9. Build or pull the new release before stopping the current service whenever possible.
10. Create a backup before migrations when required.
11. Run migrations according to the profile’s migration policy.
12. Start or switch traffic to the new release.
13. Wait for the configured readiness and health checks.
14. Verify the public path, static assets, API, database, and smoke checks.
15. Record the release ID, commit, result, duration, and rollback reference.
16. Clean up only resources owned by this project and only after retention rules are satisfied.

Never use `docker compose down -v` during ordinary deployment.

### `rollback`

1. Identify the requested previous commit, release, or image tag.
2. Confirm that the target belongs to this project.
3. Check whether database migrations changed the schema.
4. Require manual approval before restoring data or reversing a schema.
5. Roll back the application artifact or service.
6. Run the health and smoke checks.
7. Record the rollback reason, operator, source release, target release, and verification result.

Do not use `git revert` as an operational rollback unless the user explicitly requests a source-code change. Prefer redeploying a known-good immutable image or release.

## Server scope

Profiles must choose one mode:

```yaml
server_scope: single-project # single-project | multi-project
```

### `single-project`

Use when the server is dedicated to one project. Check the target path, required ports, services, images, volumes, and proxy routes. Sibling-project discovery may be disabled, but the skill must still prevent local resource collisions.

### `multi-project`

Use when several applications share a server, for example:

```text
/opt/projects/
├── electrical-activity/
├── moneyguard/
└── bale-water-bill-bot/
```

Require:

- `projects_root`.
- A project allowlist or discovery pattern.
- Unique project directory.
- Unique public path.
- Unique published ports.
- Unique image/container/Compose names.
- Unique volume and network names unless an explicitly shared resource is documented.
- Resource ownership labels.
- Nginx/systemd route ownership.

The default conflict policy is `fail-closed`. Do not automatically stop or rename an existing project to resolve a collision.

## First-time project inventory

For a new project, inventory the server and the repository before writing deployment commands.

### Repository markers

Look for, without executing arbitrary project scripts:

- `Dockerfile*`, `compose.yml`, `docker-compose.yml`.
- `package.json`, `package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`, `bun.lockb`.
- `pyproject.toml`, `requirements.txt`, `Pipfile`.
- `go.mod`, `Cargo.toml`, `pom.xml`, `build.gradle`.
- `*.service`, `Procfile`, `Makefile`, `Taskfile.yml`.
- Kubernetes manifests or Helm charts.
- Existing health endpoints and deployment documentation.

### Server resources

Inspect ownership before selecting names:

- `ss`/`lsof` listening ports.
- Docker container names and published ports.
- Docker Compose project labels.
- Images and image tags.
- Volumes and their consumers.
- Networks and connected containers.
- systemd units.
- Nginx or Caddy routes.
- Existing lock files and release directories.

Redact credentials from Git remotes and never read environment-file values into the report.

## Conflict preflight

The preflight is read-only and must happen before any deployment mutation.

Check the following against the selected profile:

- `deployment_directory` is the intended repository.
- `public_path` is not used by another proxy route.
- `host_port` is not bound by another project.
- `container_name` is unused or owned by this project.
- `compose_project_name` is unused or owned by this project.
- `image_name` is project-specific or explicitly owned.
- `volume_name` is unused or owned by this project.
- `network_name` is unused or explicitly shared.
- `systemd_unit` belongs to this project.
- Nginx configuration is syntactically valid and has no duplicate route.
- Required server tools are installed.
- Free disk and memory exceed profile thresholds.

If ownership cannot be established, treat the resource as conflicting and stop.

## Stack adapters

The adapter must be selected from the inventory and profile. Do not mix commands from unrelated stacks.

### Docker Compose

Required or conditional fields:

- Compose file.
- Compose project name.
- Services to build/start.
- Image names and tag strategy.
- Environment/secrets mapping.
- Volumes and networks.
- Health check.
- Migration service or command.
- Rollback command.

Build before replacing the current application service. Keep persistent services and volumes unless the profile explicitly defines a reviewed migration.

### Dockerfile / Docker Run

Define the build context, Dockerfile, image, container name, bind address, ports, volumes, networks, environment, restart policy, health check, and replacement command.

### systemd

Define the unit name, `ExecStart`, working directory, user, environment source, restart policy, health check, and `systemctl` permissions. Never restart a unit based only on a guessed service name.

### Language runtime

For Node.js, Python, Go, Java, PHP, or another runtime, define the runtime version, package manager, lockfile, build command, service manager, process user, working directory, port, environment source, health check, and rollback method.

### Kubernetes or other orchestrators

These are not enabled by the current server-only profile. A separate profile must explicitly allow them, define the cluster target, namespace, resource ownership, approval policy, and rollback behavior.

## Networking without a domain

A project may use IP-based routing:

```yaml
networking:
  domain: null
  ip_access_enabled: true
  public_path: /electrical-activity
  reverse_proxy: nginx
  upstream: 127.0.0.1:3001
  tls_enabled: false
```

For Nginx, use a default server such as `server_name _` and preserve the path prefix when proxying. The application must be configured with the same base path. For example:

```nginx
location = /electrical-activity {
    return 301 /electrical-activity/;
}

location /electrical-activity/ {
    proxy_pass http://127.0.0.1:3001;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Prefix /electrical-activity;
    proxy_read_timeout 60s;
}
```

Do not add a trailing slash to `proxy_pass` when the upstream application expects the prefix. A raw IP with plain HTTP is not appropriate for sensitive production traffic; use trusted HTTPS with a domain or a separately managed certificate.

## Secrets and access

Use external references:

```yaml
ssh:
  host_secret_ref: PRODUCTION_SSH_HOST
  user: null
  user_secret_ref: PRODUCTION_SSH_USER
  authentication_method: ssh-key
  private_key_secret_ref: PRODUCTION_SSH_PRIVATE_KEY
  password_secret_ref: null
  known_hosts_secret_ref: PRODUCTION_SSH_KNOWN_HOSTS
  strict_host_key_checking: true
```

Password authentication may be used only when required by the server, but it must remain a CI secret and should be replaced with a dedicated non-root SSH key account. Never print secret values, pass them in command-line arguments, or write them to deployment logs.

## Health and rollback policy

Every network service needs at least one of:

- Internal process/container health check.
- Internal readiness command.
- HTTP health endpoint.
- Stack-specific smoke test.

Configure status codes, timeout, interval, retry count, expected response, and whether the check uses the public subpath or an internal route.

Keep immutable release identifiers and previous images long enough to roll back. Database backups must be verified before migrations. Application rollback may be automatic only when the profile explicitly enables it; database rollback is manual by default.

## Audit and response format

Record every operation with:

- Operation and environment.
- Project and server scope.
- Operator or CI run ID.
- Commit/tag/image/release ID.
- Start time, end time, and duration.
- Inventory/preflight result.
- Resources changed.
- Health result.
- Rollback reference.
- Failure reason and remediation.

Use concise status output:

```text
Deployment: success
Project: electrical-activity
Target: Debian server
Scope: multi-project
Revision: <commit-sha>
Path: /electrical-activity
Health: passed
Conflict preflight: passed
Cloud deployment: disabled
```

## Included commands

The `scripts/` directory contains dependency-free commands for profile validation, server inventory, and local connection-settings management. Run them with the project’s selected profile; none of these commands deploys anything.

### Validate a profile

```bash
python3 scripts/validate-profile.py --profile deployment-profile.yml
python3 scripts/validate-profile.py --profile deployment-profile.yml --operation deploy --json
```

Exit codes:

- `0`: profile is valid (warnings may still be printed).
- `1`: profile is readable but violates a safety or requiredness rule.
- `2`: profile is missing, malformed, or cannot be parsed.

The validator supports the conservative YAML subset used by the example profile and rejects duplicate keys, invalid indentation, unsupported inline maps, unsafe literal credential fields, missing conditional settings, non-unique resources, and unsafe rollback policies.

### Inventory a server

Run the inventory script locally on the server or stream it over an already-approved SSH connection:

```bash
bash scripts/inventory-server.sh --root /opt/projects
bash scripts/inventory-server.sh --root /opt/projects --project electrical-activity
ssh deploy@server 'bash -s -- --root /opt/projects' < scripts/inventory-server.sh
```

The inventory command is read-only by design. It reports host capabilities, sibling project markers, Git metadata, Docker resources, listening ports, systemd services, and reverse-proxy routes. It never installs packages, reads environment-file contents, fetches source, builds images, changes configuration, or restarts services. Use `--output` only when deliberately saving the redacted report.

For the full connection-establishment and diagnostic procedure, including pass/fail gates between phases, follow `SERVER_ASSESSMENT_PROTOCOL.md`.

### Collect connection settings (local)

Interactive collection of server address, port, username, and password for local tooling. Secrets are hidden on real terminals, every field is validated at entry, the review screen masks the password, and the saved file is restricted to owner-only access:

```bash
python3 scripts/setup-wizard.py --output .env
python3 scripts/load-config.py --env-file .env
python3 scripts/load-config.py --env-file .env --require SERVER_ADDRESS USER_NAME SERVER_PORT
```

Exit codes for `load-config.py`: `0` valid · `1` missing required keys · `2` file missing or unreadable.

Real `.env` files are git-ignored; only `.env.example` is committed. Values collected this way feed secret stores as references — never paste secret values into profiles, logs, or changelogs. See `CONFIG_COLLECTION_WORKFLOW.md` for the security trade-offs.

## Current-project dry-run profile

When testing this skill against the current repository without server access:

1. Detect `Dockerfile`, `docker-compose.yml`, `package.json`, `package-lock.json`, and the Next.js configuration.
2. Select the Docker Compose adapter.
3. Validate the example `electrical-activity` profile.
4. Confirm the profile’s port, image, container, path, and service names are internally consistent.
5. Run local typecheck, lint, tests, build, and Compose configuration validation when tools are available.
6. Do not connect to SSH, install server packages, create server directories, deploy, restart containers, or invoke a cloud provider.
7. Report the result as a dry run rather than claiming production success.
