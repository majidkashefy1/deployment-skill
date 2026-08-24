# Server Connection & Status Assessment Protocol

A step-by-step, read-first protocol for connecting to a server and producing a complete diagnostic snapshot. Every phase is **read-only unless explicitly stated**, all outputs must be credential-redacted, and each phase ends with a pass/fail gate before continuing. Use this before bootstrap, deploy, rollback, or any remediation decision.

> Pair this protocol with `scripts/inventory-server.sh` (Phase 3–6 automation) and `scripts/validate-profile.py` (profile gate). Neither mutates anything.

---

## Phase overview and gates

| Phase | Name | Mutates server? | Gate to continue |
|---|---|---|---|
| 0 | Pre-flight preparation | No | Target approved + profile valid |
| 1 | Connection establishment | No | Authenticated, non-root, pinned host key |
| 2 | Connectivity baseline | No | Stable latency, working DNS, clock sync |
| 3 | Resource utilization | No | Above profile thresholds |
| 4 | Service availability | No | Critical services healthy |
| 5 | Security configuration | No | No critical findings unresolved |
| 6 | Report & decision | No | Snapshot recorded |

**Fail-closed rule:** if any gate fails, stop and record the finding. Do not "fix forward" during assessment.

---

## Phase 0 — Pre-flight preparation (local workstation)

1. **Confirm authorization.** Verify the target is in the profile's `allowed_deployment_targets` and you hold operator approval for an assessment run.
2. **Load the profile** and resolve secret *references* (never values into files/logs):

   ```bash
   python3 scripts/validate-profile.py --profile deployment-profile.yml --operation inventory
   ```

3. **Verify local tooling:**

   ```bash
   ssh -V                 # OpenSSH >= 8.x
   python3 --version      # for validate-profile.py
   command -v nc curl jq  # optional helpers
   ```

4. **Collect targets** from the secret store: `PRODUCTION_SSH_HOST`, `PRODUCTION_SSH_USER`, `PRODUCTION_SSH_KNOWN_HOSTS`, `PRODUCTION_SSH_PRIVATE_KEY`. Export them into the session environment only; never echo them.

---

## Phase 1 — Connection establishment

### 1.1 Name resolution

```bash
dig +short "$PRODUCTION_SSH_HOST"    # or: getent hosts "$PRODUCTION_SSH_HOST"
```

Pass: resolves to exactly one expected address. Fail: NXDOMAIN, multiple unexpected IPs (possible DNS drift/hijack) → stop.

### 1.2 TCP reachability

```bash
nc -vz -w 5 "$PRODUCTION_SSH_HOST" 22
```

Pass: `succeeded` / `open`. Fail: filtered/timeout → check network, VPN, firewall before anything else.

### 1.3 Host key pinning (never skip)

Use the known-hosts entry from the secret ref; do not accept keys interactively:

```bash
ssh-keyscan -T 5 "$PRODUCTION_SSH_HOST" > /tmp/probe_hostkey 2>/dev/null
ssh-keygen -lf /tmp/probe_hostkey          # fingerprint for human comparison
# Compare against PRODUCTION_SSH_KNOWN_HOSTS, then use it for the session:
export SSH_KNOWN_HOSTS=/tmp/pinned_known_hosts
```

Pass: fingerprint matches pinned value. Mismatch = possible MITM → **hard stop**.

### 1.4 Authenticated session with strict settings

```bash
ssh -o StrictHostKeyChecking=yes \
    -o UserKnownHostsFile="$SSH_KNOWN_HOSTS" \
    -o ConnectTimeout=20 \
    -o ServerAliveInterval=30 \
    -o ServerAliveCountMax=3 \
    -o BatchMode=yes \
    "$PRODUCTION_SSH_USER@$PRODUCTION_SSH_HOST" 'echo CONNECTED; id'
```

Checks performed here:
- Key-based auth works without prompts (`BatchMode=yes` forbids password fallback).
- Session identity: confirm `uid` is the intended **non-root** deploy account (`require_non_root: true`).

### 1.5 Privilege model

```bash
sudo -n true 2>&1 && echo SUDO_PASSWORDLESS || echo SUDO_LIMITED_OR_PROMPT
id; groups
```

Record whether passwordless sudo exists — needed later for `bootstrap`, irrelevant for assessment. Never disable sudo protections to "make checks work".

**Gate:** authenticated + correct user + pinned key → continue. Otherwise stop.

---

## Phase 2 — Connectivity baseline (run over the SSH session)

Define a helper once per session to keep commands short:

```bash
SSH="ssh -o StrictHostKeyChecking=yes -o UserKnownHostsFile=$SSH_KNOWN_HOSTS \
     -o ServerAliveInterval=30 $PRODUCTION_SSH_USER@$PRODUCTION_SSH_HOST"
```

| # | Check | Command | Pass criteria |
|---|---|---|---|
| 2.1 | Round-trip latency | `$SSH 'ping -c 4 -q 1.1.1.1'` or measure ssh time: `time $SSH true` | < 100 ms typical; no packet loss |
| 2.2 | Outbound DNS | `$SSH 'getent hosts debian.org'` | Resolves |
| 2.3 | Outbound HTTPS | `$SSH 'curl -fsSI -m 8 https://deb.debian.org >/dev/null && echo OK'` | HTTP 200/301 |
| 2.4 | Clock sync | `$SSH 'timedatectl show-timesync -p NTPSynchronized 2>/dev/null; timedatectl'` | `NTPSynchronized=yes`; skew < 60 s |
| 2.5 | Session stability | Run 2.1 three times | Variance acceptable, no disconnects |

Failures here indicate network/NTP problems that will break package installs, TLS validation, and health checks later — remediate before proceeding.

---

## Phase 3 — Resource utilization

All read-only. Capture values against profile thresholds (`minimum_free_disk_gb`, `minimum_free_memory_mb`).

### 3.1 Identity & uptime

```bash
$SSH 'cat /etc/os-release; uname -mr; uptime'
```

Record: distro/version (expect Debian per profile), kernel/arch, load average relative to core count.

### 3.2 CPU

```bash
$SSH 'nproc; lscpu | grep -E "Model name|CPU\(s\)|Virtualization"'
$SSH 'mpstat 1 3 2>/dev/null || top -bn2 -d1 | grep "%Cpu"'   # sample over ~3 s
```

Flag sustained CPU > 80 % at idle.

### 3.3 Memory & swap

```bash
$SSH 'free -m; swapon --show'
```

Flag: available memory < profile minimum, swap in active use while idle.

### 3.4 Disk space & inodes

```bash
$SSH 'df -h; df -i'
```

Flag: any mounted filesystem > 85 % full or > 80 % inodes. Pay special attention to `/var/lib/docker`.

### 3.5 Disk I/O pressure (quick sanity)

```bash
$SSH 'vmstat 1 3'
```

Flag: sustained high `wa` (I/O wait > 30 %).

### 3.6 Top consumers

```bash
$SSH 'ps aux --sort=-%mem | head -8; ps aux --sort=-%cpu | head -8'
```

Note whether top consumers belong to this project, siblings, or system services — informs conflict decisions later.

---

## Phase 4 — Service availability

### 4.1 Failed systemd units

```bash
$SSH 'systemctl --failed --no-pager; systemctl list-units --state=running --no-pager | head -40'
```

Pass: no failed units relevant to the project scope.

### 4.2 Container runtime

```bash
$SSH 'docker info --format "{{.ServerVersion}} {{.OperatingSystem}}" 2>&1'
$SSH 'docker compose version 2>&1'
$SSH 'docker ps -a --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"; docker volume ls; docker network ls'
```

Check: daemon reachable, Compose v2 present, containers `Up (healthy)` where healthchecks are defined, restart-looping containers noted (`Restarting (1)`), orphaned volumes flagged.

### 4.3 Listening ports & ownership

```bash
$SSH 'ss -tulpn'
```

Cross-check every listening port against the profile (`host_port`) and sibling projects. An unowned listener = potential conflict → record, do not kill.

### 4.4 Reverse proxy

```bash
$SSH 'systemctl is-active nginx 2>/dev/null; nginx -t 2>&1'
# Route uniqueness:
$SSH 'grep -REh "server_name|location|proxy_pass|listen" /etc/nginx/sites-enabled/ /etc/nginx/conf.d/ 2>/dev/null | sort | uniq -c | sort -rn | head'
```

Pass: config syntax valid, target `public_path` not claimed elsewhere.

### 4.5 Application health probes

For each configured endpoint (internal first, then public path):

```bash
$SSH 'curl -s -o /dev/null -w "%{http_code} %{time_total}s\n" http://127.0.0.1:3000/electrical-activity/login'
curl -s -o /dev/null -w "%{http_code}\n" http://"$SERVER_ADDR"/electrical-activity/login
```

Compare codes against `verification.expected_status_codes`. Also probe database reachability from the app side when configured (e.g., `docker compose exec app pg_isready` equivalents are stack-specific — use the adapter's documented check, never raw credentials on the CLI).

### 4.6 Time-dependent jobs

```bash
$SSH 'systemctl list-timers --no-pager | head -15'
```

Note backup/maintenance timers and whether they recently succeeded (`systemctl status <timer>`).

---

## Phase 5 — Security configuration

Read-only audit; findings feed the decision matrix.

### 5.1 SSH hardening

```bash
$SSH 'sshd -T 2>/dev/null | grep -Ei "permitrootlogin|passwordauthentication|pubkeyauthentication|maxauthtries|x11forwarding"'
```

Expected: `permitrootlogin no`, `passwordauthentication no` (or justified exception), pubkey enabled.

### 5.2 Firewall

```bash
$SSH 'sudo -n ufw status verbose 2>/dev/null; sudo -n nft list ruleset 2>/dev/null | head -50; sudo -n iptables -L -n 2>/dev/null | head -30'
```

Record: default-deny posture, only required inbound ports (22, 80/443, published app ports). A publicly bound port that should be loopback-only (compare `ss -tulpn` bind addresses) is a **critical finding**.

### 5.3 Brute-force protection & auth history

```bash
$SSH 'systemctl is-active fail2ban 2>/dev/null; sudo -n fail2ban-client status 2>/dev/null'
$SSH 'last -a -n 10; sudo -n grep -c "Failed password" /var/log/auth.log 2>/dev/null || journalctl -u ssh --since "-24h" | grep -c Failed'
```

Elevated failure counts are informational; correlate with firewall rules.

### 5.4 Patch level

```bash
$SSH 'apt list --upgradable 2>/dev/null | wc -l'
$SSH 'systemctl is-active unattended-upgrades 2>/dev/null'
$SSH 'cat /var/run/reboot-required 2>/dev/null && echo REBOOT_REQUIRED'
```

Flag: reboot required (kernel security update), unattended-upgrades inactive.

### 5.5 Accounts & privileges

```bash
$SSH 'awk -F: '\''$7 !~ /(nologin|false)$/ {print $1, $7}'\'' /etc/passwd'
$SSH 'getent group sudo docker'
```

Verify no unexpected shell accounts; `docker` group members effectively have root — membership should be deliberate.

### 5.6 Secrets hygiene (surface scan only)

```bash
$SSH 'find /opt/projects -maxdepth 3 -name ".env" -perm /o+r 2>/dev/null'   # world-readable env files?
$SSH 'stat -c "%a %U %n" /opt/projects/*/.deployment 2>/dev/null'
```

Flag world-readable `.env`, overly open directory modes vs profile `directory_mode: "0750"`.

### 5.7 TLS (when applicable)

```bash
$SSH 'echo | openssl s_client -servername DOMAIN -connect DOMAIN:443 2>/dev/null | openssl x509 -noout -enddate'
```

Flag expiry < 14 days.

---

## Phase 6 — Report and decision

### 6.1 Redact everything

Before persisting or sharing output apply the same redaction as `inventory-server.sh`: strip credentials from URLs, never include `.env` contents, private keys, tokens, or credentialed remotes. Prefer saving via `--output` of the inventory script for machine-readable sections.

```bash
bash scripts/inventory-server.sh --root /opt/projects --output /tmp/assessment-inventory.txt
```

### 6.2 Standard snapshot format

```text
Assessment: <date/time UTC>
Target: <host-as-resolved> | scope=<single-project|multi-project> | operator=<name-or-ci-run>

Connectivity:  dns=<pass/fail> tcp22=<pass/fail> hostkey=<pinned/ok> auth=key<user> latency=<ms>
Resources:     disk-root=<%> disk-docker=<%> mem-avail=<MB> swap-used=<MB> load=<x.xx>/<cores>
Services:      failed-units=<n> docker=<ver> unhealthy-containers=[...] proxy=<nginx ok/conflict>
Ports:         listeners=<list> conflicts=[...]
Health:        internal=<codes/times> public-path=<codes> db=<reachable/unverified>
Security:      ssh-root-login=no pw-auth=no firewall=<active/ruleset> patches-pending=<n> reboot=<req/no>
Findings:      [CRITICAL] ... / [WARN] ... / [INFO] ...
Decision:      proceed-bootstrap | proceed-deploy | remediate-first | escalate
```

### 6.3 Decision matrix

| Condition | Decision |
|---|---|
| All gates pass, thresholds met, no critical findings | Proceed with requested operation |
| Docker/Compose missing or directories absent | `bootstrap` with explicit approval |
| Port/path/name conflicts detected | Remediate plan first — never auto-stop another project |
| Disk/memory below threshold, reboot required, failed units | Remediate before deploy |
| Critical security finding (root SSH, public secrets, unpinned host key mismatch) | Escalate; block deployment |
| Health probes failing on an already-deployed app | Consider `rollback` after diagnosis |

### 6.4 Record

Append the snapshot summary and decision to the project's `DEPLOYMENT_CHANGELOG.md` (assessment note) so subsequent operations inherit the evidence base.

---

## Quick-reference: full one-shot collection

For a fast repeatable sweep after the initial manual walkthrough (read-only):

```bash
$SSH '
set -eu
echo "== SYSTEM =="; cat /etc/os-release | head -2; uname -mr; uptime
echo "== RESOURCES =="; df -h / /var/lib/docker 2>/dev/null; free -m
echo "== SERVICES =="; systemctl --failed --no-pager | tail -n +2
echo "== DOCKER =="; docker ps -a --format "{{.Names}} {{.Status}} {{.Ports}}" 2>/dev/null
echo "== PORTS =="; ss -tulpn | tail -n +2
echo "== SECURITY =="; sshd -T 2>/dev/null | grep -Ei "^permitrootlogin|^passwordauthentication"
echo "== PATCHES =="; apt list --upgradable 2>/dev/null | tail -n +2 | wc -l; cat /var/run/reboot-required 2>/dev/null
' 2>&1 | sed -E 's#(https?|ssh)://[^/@[:space:]]+@#\1://<credentials>@#g'
```

The final `sed` mirrors the repo's redaction rule so pasted output stays safe.
