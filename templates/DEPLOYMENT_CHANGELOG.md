# Deployment Changelog

> Copy this file into the project repository and complete one entry after each
> approved deployment. Replace the profile values when using it for another
> project. Never record passwords, private keys, access tokens, or full secret
> connection strings here.

## Project Deployment Profile

| Field | Current value | Required? | Customize for another project |
|---|---|---:|---|
| Project name | `electrical-activity` | Yes | Change to the project slug/name |
| Environment | `production` | Yes | `staging`, `production`, etc. |
| Server scope | `multi-project` | Yes | Use `single-project` for a dedicated server |
| Projects root | `/opt/projects` | Conditional | Required in multi-project mode |
| Server directory | `/opt/projects/electrical-activity` | Yes | Change per project |
| Repository | `majidkashefy1/electrical-calculator` | Yes | Change per project |
| Production branch | `main` | Yes | Change only with approval |
| Stack adapter | `docker-compose` | Yes | Use the discovered stack |
| Compose project | `electrical-activity` | Conditional | Required for Compose |
| App image | `electrical-activity` | Conditional | Change per project |
| App container | `electrical-activity-app` | Conditional | Change per project |
| Host port | `3001` | Conditional | Must be unique on shared servers |
| Container port | `3000` | Conditional | Change if the app listens elsewhere |
| Public path | `/electrical-activity` | Conditional | Must be unique behind the proxy |
| Domain | `null` | Nullable | Required only for domain/TLS routing |
| Reverse proxy | `nginx` | Conditional | Set `null` for direct-port access |
| Upstream | `127.0.0.1:3001` | Conditional | Match the host port |
| Health path | `/electrical-activity/login` | Yes | Use the project’s verified health path |
| Cloud deployment | Disabled | Yes | This skill is server-only by default |

## Deployment Record

### Summary

- **Deployment timestamp (UTC):** `YYYY-MM-DDTHH:MM:SSZ`
- **Operator / CI run:** `name-or-run-id`
- **Environment:** `production`
- **Deployment status:** `success | failed | rolled-back`
- **Duration:** `e.g. 2m 18s`
- **Deployment target:** `Debian server`
- **Cloud targets used:** `none`

### Commit and Release

- **Repository:** `owner/repository`
- **Branch:** `main`
- **Commit SHA:** `full-commit-sha`
- **Version/tag:** `version-or-tag`
- **Image tag:** `image-tag`
- **Previous known-good release:** `commit-or-image`

### Change Summary

#### Features

- <!-- List new functionality. Use `None` when not applicable. -->

#### Fixes

- <!-- List bug fixes. Use `None` when not applicable. -->

#### Breaking Changes

- <!-- List migrations, API changes, configuration changes, or behavior changes. -->

#### Database and Data Changes

- **Migrations run:** `yes | no`
- **Migration identifiers:** `migration-names-or-none`
- **Backup created before migration:** `yes | no | not-applicable`
- **Seed/data changes:** `summary-or-none`
- **Destructive changes approved:** `yes | no | not-applicable`

#### Configuration Changes

- <!-- List non-secret variables or infrastructure changes. Never paste secret values. -->

## Inventory and Conflict Preflight

- **Inventory performed:** [ ] yes [ ] no [ ] not required
- **Inventory timestamp:** `YYYY-MM-DDTHH:MM:SSZ`
- **Server scope confirmed:** [ ] single-project [ ] multi-project
- **Target directory verified:** [ ]
- **Sibling projects inspected:** [ ] [ ] not applicable
- **Public path is unique:** [ ]
- **Host port is available or project-owned:** [ ]
- **Container names are unique or project-owned:** [ ]
- **Compose project is unique or project-owned:** [ ]
- **Images are unique or project-owned:** [ ]
- **Volumes are unique or project-owned:** [ ]
- **Networks are unique or explicitly shared:** [ ]
- **systemd ownership verified:** [ ] [ ] not applicable
- **Reverse-proxy route is unique:** [ ] [ ] not applicable
- **Nginx configuration validated:** [ ] [ ] not applicable
- **Conflict result:** `passed | blocked | not-applicable`
- **Conflict notes:**

## Verification Checklist

### Application and Container

- [ ] Requested commit is deployed.
- [ ] Image was built or pulled successfully.
- [ ] Expected container/service is running.
- [ ] Restart policy is correct.
- [ ] Container health check passed.
- [ ] No unexpected restart loop exists.
- [ ] CPU and memory usage are within expected limits.

### Networking and Subpath

- [ ] Public path is reachable: `http://<server-ip>/electrical-activity`
- [ ] Path without trailing slash redirects correctly if configured.
- [ ] Login or health endpoint returns an expected status.
- [ ] Static CSS/JavaScript assets load.
- [ ] API endpoints use the correct subpath.
- [ ] WebSockets or streaming endpoints verified if enabled.
- [ ] Reverse-proxy configuration is valid.
- [ ] No domain was required or an approved domain was verified.

### Dependencies and Data

- [ ] Database is reachable.
- [ ] Required migrations completed.
- [ ] Cache/queue is healthy if enabled.
- [ ] Backup exists and is readable when required.
- [ ] No data-loss or migration warnings remain.

### Operations

- [ ] Application logs show no new critical errors.
- [ ] Deployment lock was released.
- [ ] Old-release retention policy was applied.
- [ ] No resources belonging to another project were changed.
- [ ] Deployment status was recorded in CI/server audit logs.

## Incident Notes

- **Incident occurred:** `yes | no`
- **Symptoms:**
- **Root cause:**
- **Affected projects/services:**
- **Mitigation:**
- **Follow-up issue:**

## Rollback Instructions

Use the project profile values and replace placeholders before executing. Do not
perform an automatic database rollback unless a separately approved recovery
procedure exists.

```bash
cd /opt/projects/electrical-activity

# Confirm the target release belongs to this project.
PREVIOUS_RELEASE="<known-good-commit-or-release>"

# Use the project’s approved stack adapter and immutable image/release tag.
git fetch --prune origin main
git checkout --force "$PREVIOUS_RELEASE"

# Example only; use the exact profile-specific Compose project and image tag.
IMAGE_TAG="$PREVIOUS_RELEASE" \
  docker compose -p electrical-activity up -d --no-build --remove-orphans

# Verify the configured health URL before declaring recovery.
# Check database compatibility separately before restoring or reversing schema.
```

### Rollback Result

- **Rollback requested:** `yes | no`
- **Reason:**
- **From release:**
- **To release:**
- **Database action:** `none | forward-fix | restored-backup | manually-reversed`
- **Health after rollback:** `passed | failed`
- **Follow-up required:** `yes | no`
- **Notes:**
