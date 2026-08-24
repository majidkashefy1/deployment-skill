#!/usr/bin/env bash
# Read-only server and project inventory for the server-deployment skill.
#
# The default output is stdout. Use --output only when deliberately saving a
# redacted report. This script never installs packages, reads environment-file
# contents, fetches source, builds images, edits configuration, or restarts
# services.

set -Eeuo pipefail

ROOT="/opt/projects"
PROJECT_FILTER=""
OUTPUT=""

usage() {
  cat <<'USAGE'
Usage: inventory-server.sh [options]

Read-only inventory of a server and projects below a root directory.

Options:
  --root PATH       Project root (default: /opt/projects)
  --project NAME    Inspect one direct child project by directory name
  --output PATH     Write the redacted report to PATH instead of stdout
  --help            Show this help

Examples:
  bash scripts/inventory-server.sh --root /opt/projects
  bash scripts/inventory-server.sh --root /opt/projects --project electrical-activity
  ssh deploy@server 'bash -s -- --root /opt/projects' < scripts/inventory-server.sh
USAGE
}

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 2
}

has_command() {
  command -v "$1" >/dev/null 2>&1
}

redact_remote() {
  # Redact credentials in HTTP(S), ssh://, and scp-like URLs before output.
  sed -E \
    -e 's#(https?://)[^/@[:space:]]+@#\1<credentials>@#g' \
    -e 's#(https?://)[^/@[:space:]]+:[^/@[:space:]]+@#\1<credentials>@#g' \
    -e 's#(ssh://)[^/@[:space:]]+@#\1<credentials>@#g' \
    -e 's#(ssh://)[^/@[:space:]]+:[^/@[:space:]]+@#\1<credentials>@#g'
}

while (($# > 0)); do
  case "$1" in
    --root)
      (($# >= 2)) || fail "--root requires a value"
      ROOT=$2
      shift 2
      ;;
    --project)
      (($# >= 2)) || fail "--project requires a value"
      PROJECT_FILTER=$2
      shift 2
      ;;
    --output)
      (($# >= 2)) || fail "--output requires a value"
      OUTPUT=$2
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      fail "unknown option: $1"
      ;;
  esac
done

if [[ -n "$OUTPUT" ]]; then
  output_parent=$(dirname -- "$OUTPUT")
  [[ -d "$output_parent" ]] || fail "output directory does not exist: $output_parent"
  umask 077
  exec >"$OUTPUT"
fi

printf '%s\n' '# Server Stack Inventory'
printf '%s\n' "- Generated at (UTC): $(date -u '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || printf 'unknown')"
printf '%s\n' "- Projects root: \`$ROOT\`"
printf '%s\n\n' '- Mode: read-only; environment-file contents and credentials are excluded.'

printf '%s\n' '## Host'
printf '%s\n' "- Hostname: $(hostname 2>/dev/null || printf 'unknown')"
printf '%s\n' "- Kernel: $(uname -srm 2>/dev/null || printf 'unknown')"
if [[ -r /etc/os-release ]]; then
  os_name=$(awk -F= '$1 == "PRETTY_NAME" {gsub(/^"|"$/, "", $2); print $2; exit}' /etc/os-release)
  printf '%s\n' "- Operating system: ${os_name:-unknown}"
else
  printf '%s\n' '- Operating system: unavailable'
fi
if has_command nproc; then printf '%s\n' "- CPU cores: $(nproc 2>/dev/null || printf 'unknown')"; fi
if has_command free; then printf '%s\n' "- Memory: $(free -h 2>/dev/null | awk '/^Mem:/ {print $2 " total, " $7 " available"}' || printf 'unknown')"; fi
if has_command df; then printf '%s\n' "- Root disk: $(df -h / 2>/dev/null | awk 'NR == 2 {print $2 " total, " $4 " available"}' || printf 'unknown')"; fi
printf '\n'

printf '%s\n' '## Installed Tools'
for tool in git docker podman docker-compose systemctl nginx caddy ss lsof; do
  if has_command "$tool"; then
    version='available'
    case "$tool" in
      docker)
        docker_server_version=$(docker version --format '{{.Server.Version}}' 2>/dev/null || true)
        version=${docker_server_version:-installed; daemon unavailable}
        ;;
      docker-compose) version=$(docker-compose version --short 2>/dev/null || printf 'available') ;;
      podman) version=$(podman --version 2>/dev/null || printf 'available') ;;
      nginx) version=$(nginx -v 2>&1 | sed 's/^nginx version: //' || printf 'available') ;;
      caddy) version=$(caddy version 2>/dev/null | head -n 1 || printf 'available') ;;
    esac
    printf '%s\n' "- \`$tool\`: $version"
  else
    printf '%s\n' "- \`$tool\`: missing"
  fi
done
printf '\n'

printf '%s\n' '## Listening Ports'
if has_command ss; then
  if ! ss -ltn 2>/dev/null | sed -n '1p'; then
    printf '%s\n' '- Unable to inspect listening ports.'
  else
    printf '%s\n' '```text'
    ss -ltn 2>/dev/null || printf '%s\n' 'unavailable'
    printf '%s\n' '```'
  fi
elif has_command netstat; then
  printf '%s\n' '```text'
  netstat -lnt 2>/dev/null || printf '%s\n' 'unavailable'
  printf '%s\n' '```'
else
  # Backticks are report wording, not command substitutions.
  # shellcheck disable=SC2016
  printf '%s\n' '- `ss` and `netstat` are not available.'
fi
printf '\n'

printf '%s\n' '## Projects'
if [[ ! -d "$ROOT" ]]; then
  printf '%s\n\n' "- Root does not exist yet: \`$ROOT\` (inventory remains read-only)."
else
  found_project=0
  while IFS= read -r -d '' project_dir; do
    project_name=$(basename -- "$project_dir")
    [[ -z "$PROJECT_FILTER" || "$PROJECT_FILTER" == "$project_name" ]] || continue
    found_project=1
    printf '%s\n' "### \`$project_name\`"
    project_real=$(cd -- "$project_dir" && pwd -P)
    printf '%s\n' "- Directory: $project_real"

    git_root=$(git -C "$project_dir" rev-parse --show-toplevel 2>/dev/null || true)
    git_root_real=""
    if [[ -n "$git_root" ]]; then
      git_root_real=$(cd -- "$git_root" 2>/dev/null && pwd -P) || true
    fi
    if [[ -n "$git_root_real" && "$git_root_real" == "$project_real" ]]; then
      branch=$(git -C "$project_dir" symbolic-ref --short -q HEAD 2>/dev/null || printf 'detached')
      revision=$(git -C "$project_dir" rev-parse --short HEAD 2>/dev/null || printf 'unknown')
      remote=$(git -C "$project_dir" config --get remote.origin.url 2>/dev/null | head -n 1 | redact_remote || true)
      printf '%s\n' "- Git: branch \`$branch\`, revision \`$revision\`"
      printf '%s\n' "- Git origin: ${remote:-not configured}"
      if [[ -n "$(git -C "$project_dir" status --porcelain 2>/dev/null || true)" ]]; then
        printf '%s\n' '- Git working tree: modified/uncommitted files detected (names intentionally omitted).'
      else
        printf '%s\n' '- Git working tree: clean'
      fi
    else
      printf '%s\n' '- Git: no direct repository at this project root'
    fi

    stack='custom/unknown'
    markers=()
    if compgen -G "$project_dir/compose.yml" >/dev/null || compgen -G "$project_dir/compose.yaml" >/dev/null || compgen -G "$project_dir/docker-compose.yml" >/dev/null || compgen -G "$project_dir/docker-compose.yaml" >/dev/null; then
      stack='docker-compose'
      markers+=(compose-file)
    fi
    if compgen -G "$project_dir/Dockerfile" >/dev/null || compgen -G "$project_dir/Dockerfile.*" >/dev/null; then
      [[ "$stack" == 'docker-compose' ]] || stack='dockerfile'
      markers+=(dockerfile)
    fi
    [[ -f "$project_dir/package.json" ]] && markers+=(package.json) && [[ "$stack" == 'custom/unknown' ]] && stack='node'
    [[ -f "$project_dir/pyproject.toml" || -f "$project_dir/requirements.txt" ]] && markers+=(python-manifest) && [[ "$stack" == 'custom/unknown' ]] && stack='python'
    [[ -f "$project_dir/go.mod" ]] && markers+=(go.mod) && [[ "$stack" == 'custom/unknown' ]] && stack='go'
    [[ -f "$project_dir/pom.xml" || -f "$project_dir/build.gradle" || -f "$project_dir/build.gradle.kts" ]] && markers+=(java-manifest) && [[ "$stack" == 'custom/unknown' ]] && stack='java'
    if find "$project_dir" -maxdepth 1 -type f -name '*.service' -print -quit 2>/dev/null | grep -q .; then
      markers+=(systemd-unit)
      [[ "$stack" == 'custom/unknown' ]] && stack='systemd'
    fi
    if find "$project_dir" -maxdepth 2 -type f \( -name '*.yaml' -o -name '*.yml' \) -print -quit 2>/dev/null | grep -Eq '/(k8s|kubernetes|helm)/|/(deployment|service)\.ya?ml$'; then
      markers+=(orchestration-manifest)
      [[ "$stack" == 'custom/unknown' ]] && stack='kubernetes'
    fi
    printf '%s\n' "- Detected stack: \`$stack\`"
    printf '%s\n' "- Stack markers: ${markers[*]:-none}"

    if [[ -f "$project_dir/.env" || -f "$project_dir/.env.production" || -f "$project_dir/.env.local" ]]; then
      printf '%s\n' '- Environment files: present (contents intentionally not inspected)'
    else
      printf '%s\n' '- Environment files: none detected'
    fi
    printf '\n'
  done < <(find "$ROOT" -mindepth 1 -maxdepth 1 -type d -print0 2>/dev/null | sort -z)
  if ((found_project == 0)); then
    if [[ -n "$PROJECT_FILTER" ]]; then
      printf '%s\n\n' "- Project not found: \`$PROJECT_FILTER\`"
    else
      printf '%s\n\n' '- No direct child project directories found.'
    fi
  fi
fi

printf '%s\n' '## Docker Resources'
if has_command docker && docker info >/dev/null 2>&1; then
  printf '%s\n' '### Containers'
printf '%s\n' '```text'
  docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Ports}}\t{{.Status}}' 2>/dev/null || printf '%s\n' 'unavailable'
  printf '%s\n' '```'
  printf '%s\n' '### Compose ownership'
  printf '%s\n' '```text'
  container_ids=$(docker ps -aq 2>/dev/null || true)
  if [[ -n "$container_ids" ]]; then
    # Labels identify ownership without exposing environment variables.
    mapfile -t container_id_list <<< "$container_ids"
    docker inspect --format '{{.Name}}\t{{index .Config.Labels "com.docker.compose.project"}}\t{{index .Config.Labels "com.docker.compose.service"}}' "${container_id_list[@]}" 2>/dev/null | sed 's#^/##' || true
  else
    printf '%s\n' 'no containers'
  fi
  printf '%s\n' '```'
  printf '%s\n' '### Images'
  printf '%s\n' '```text'
  docker image ls --format 'table {{.Repository}}\t{{.Tag}}\t{{.ID}}\t{{.CreatedSince}}\t{{.Size}}' 2>/dev/null || printf '%s\n' 'unavailable'
  printf '%s\n' '```'
  printf '%s\n' '### Volumes'
  printf '%s\n' '```text'
  docker volume ls --format 'table {{.Name}}\t{{.Driver}}' 2>/dev/null || printf '%s\n' 'unavailable'
  printf '%s\n' '```'
  printf '%s\n' '### Networks'
  printf '%s\n' '```text'
  docker network ls --format 'table {{.Name}}\t{{.Driver}}\t{{.Scope}}' 2>/dev/null || printf '%s\n' 'unavailable'
  printf '%s\n' '```'
else
  printf '%s\n' '- Docker daemon unavailable or Docker is not installed.'
fi
printf '\n'

printf '%s\n' '## Service Manager'
if has_command systemctl; then
  printf '%s\n' '```text'
  systemctl list-units --type=service --all --no-legend 2>/dev/null | sed -E 's/[[:space:]]+/ /g' | head -n 200 || printf '%s\n' 'unavailable or permission denied'
  printf '%s\n' '```'
else
  printf '%s\n' '- systemd is not available.'
fi
printf '\n'

printf '%s\n' '## Reverse Proxy'
if has_command nginx; then
  if nginx -t >/dev/null 2>&1; then
    printf '%s\n' '- Nginx syntax: valid'
  else
    printf '%s\n' '- Nginx syntax: invalid or permission denied'
  fi

  nginx_routes=$(nginx -T 2>/dev/null || true)
  if [[ -n "$nginx_routes" ]]; then
    printf '%s\n' '### Discovered route directives'
    printf '%s\n' '```text'
    printf '%s\n' "$nginx_routes" | grep -E '^[[:space:]]*(server_name|location|proxy_pass)[[:space:]]' \
      | redact_remote \
      | sed -E 's/[[:space:]]+/ /g' \
      | head -n 300 || true
    printf '%s\n' '```'
  else
    printf '%s\n' '- Nginx configuration dump unavailable or permission denied.'
  fi

elif has_command caddy; then
  printf '%s\n' '- Caddy detected; inspect its configured routes with the server operator.'
else
  printf '%s\n' '- No supported reverse proxy detected.'
fi

printf '\n%s\n' '> Review this report and create a project-specific deployment profile before bootstrap or deployment.'
