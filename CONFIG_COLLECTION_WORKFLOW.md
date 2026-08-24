# Configuration Data Collection Workflow

Two complementary approaches for collecting connection settings — such as server addresses, usernames, and passwords — plus guidance on when to use each. Both converge on the same **runtime contract**: values end up as named variables (`SERVER_ADDRESS`, `SERVER_PORT`, `USER_NAME`, `SERVER_PASSWORD`) that the application reads from its environment.

```text
                 ┌──────────────────────────────┐
   User ──runs──►│ Approach 1: Interactive CLI  │──validates──┐
                 └──────────────────────────────┘             │
                                                              ▼
                 ┌──────────────────────────────┐     ┌─────────────────┐
   Admin ─edits─►│ Approach 2: .env / YAML file │────►│ Process env vars │
                 └──────────────────────────────┘     └────────┬────────┘
                                                               ▼
                                                    Application consumes config
```

**Field classification** (drives every security decision below):

| Field | Example | Sensitivity | Handling |
|---|---|---|---|
| `SERVER_ADDRESS` | `build.internal` | Public-ish | May be logged/shown |
| `SERVER_PORT` | `22` | Public-ish | May be logged/shown |
| `USER_NAME` | `deploy` | Low | Show freely |
| `SERVER_PASSWORD` | `••••••••` | **Secret** | Hidden input, never echoed/logged/committed |

---

## Approach 1 — Interactive CLI wizard (runtime prompting)

The program asks for each field step-by-step, validates it immediately, hides secret input, shows a masked confirmation, then either uses the values in-process or offers to persist them (writing the same `.env` consumed by Approach 2).

### Pure standard-library Python

```python
#!/usr/bin/env python3
"""setup-wizard.py — collect connection settings interactively."""
import getpass
import os
import re
import sys

REQUIRED = ["SERVER_ADDRESS", "SERVER_PORT", "USER_NAME", "SERVER_PASSWORD"]


def ask(prompt: str, *, default: str | None = None,
        validator=None, secret: bool = False) -> str:
    while True:
        if secret:
            value = getpass.getpass(f"{prompt}: ")
        else:
            hint = f" [{default}]" if default else ""
            value = input(f"{prompt}{hint}: ").strip() or (default or "")
        if not value:
            print("  ! This field is required.")
            continue
        if validator and not validator(value):
            print("  ! Invalid format — try again.")
            continue
        return value


def valid_host(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?", value))


def valid_port(value: str) -> bool:
    return value.isdigit() and 1 <= int(value) <= 65535


def mask(secret_value: str) -> str:
    return "*" * min(len(secret_value), 8)


def main() -> int:
    print("Connection setup — press Ctrl+C to cancel.\n")
    try:
        config = {
            "SERVER_ADDRESS": ask("Server address (hostname or IP)", validator=valid_host),
            "SERVER_PORT": ask("Port", default="22", validator=valid_port),
            "USER_NAME": ask("Username"),
            "SERVER_PASSWORD": ask("Password (input hidden)", secret=True),
        }
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 1

    print("\nReview:")
    for key in REQUIRED:
        shown = mask(config[key]) if key == "SERVER_PASSWORD" else config[key]
        print(f"  {key:<16} {shown}")
    if input("\nSave to .env? [y/N] ").strip().lower() != "y":
        print("Values discarded.")
        return 1

    lines = "".join(f'{k}="{v}"\n' for k, v in config.items())
    with open(".env", "a", encoding="utf-8") as fh:
        fh.write(lines)
    os.chmod(".env", 0o600)
    print("Saved to .env (permissions restricted to owner).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Key techniques: `getpass.getpass()` disables echo so the password never appears on screen; every field is validated *at entry time* so bad data fails fast; the review screen masks the secret.

### Bash equivalent (for shell-first workflows)

```bash
#!/usr/bin/env bash
set -euo pipefail

read -rp "Server address: " SERVER_ADDRESS
read -rp "Port [22]: " SERVER_PORT; SERVER_PORT=${SERVER_PORT:-22}
read -rp "Username: " USER_NAME
read -rsp "Password (input hidden): " SERVER_PASSWORD; echo

umask 177                       # resulting file will be 0600
cat >> .env <<EOF
SERVER_ADDRESS="$SERVER_ADDRESS"
SERVER_PORT="$SERVER_PORT"
USER_NAME="$USER_NAME"
SERVER_PASSWORD="$SERVER_PASSWORD"
EOF
echo "Saved to .env"
```

### Nicer UX option (third-party)

For arrow-key editing, defaults, and confirmation loops, `questionary` wraps the same logic:

```python
import questionary

answers = questionary.form(
    server_address=questionary.text("Server address:"),
    port=questionary.text("Port:", default="22"),
    username=questionary.text("Username:"),
    password=questionary.password("Password:"),
).ask()
```

---

## Approach 2 — Persistent configuration file (`.env` or YAML)

Values are written once by an admin (or by the wizard above) and loaded silently on every run. This is what CI and scheduled jobs require.

### Template committed, real file ignored

Commit `.env.example`; never commit `.env`:

```bash
# .env.example  (safe to commit — no real values)
SERVER_ADDRESS=
SERVER_PORT=22
USER_NAME=
SERVER_PASSWORD=
```

```gitignore
# .gitignore
.env
.env.*
!.env.example
```

### Loading without dependencies (stdlib)

```python
#!/usr/bin/env python3
"""load-config.py — read .env into a dict and expose masked display."""
import os
import stat
import sys
from pathlib import Path


def parse_env(path: str = ".env") -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def check_permissions(path: str = ".env") -> None:
    mode = stat.S_IMODE(Path(path).stat().st_mode)
    if mode & 0o077:
        print(f"WARNING: {path} is readable by group/others ({mode:o}); "
              f'run: chmod 600 {path}', file=sys.stderr)


def mask(secret_value: str) -> str:
    return "*" * min(len(secret_value), 8)


config = parse_env()
missing = [k for k in ("SERVER_ADDRESS", "USER_NAME") if not config.get(k)]
if missing:
    sys.exit(f"Missing required keys: {', '.join(missing)}")
check_permissions()

print(f'Connecting to {config["USER_NAME"]}@{config["SERVER_ADDRESS"]}'
      f':{config.get("SERVER_PORT", "22")} password={mask(config["SERVER_PASSWORD"])}')
```

With `pip install python-dotenv`, loading collapses to two lines:

```python
from dotenv import load_dotenv
import os
load_dotenv()
print(os.environ["SERVER_ADDRESS"])
```

### YAML alternative (matches this repository's profile style)

Keep literals out entirely — store a *reference* and resolve it from a secret store:

```yaml
# connection.yml
connection:
  server_address: build.internal
  port: 22
  username: deploy
  password_secret_ref: BUILD_SERVER_PASSWORD
```

```python
import os
cfg = yaml.safe_load(open("connection.yml"))["connection"]
password = os.environ[cfg.pop("password_secret_ref")]   # resolved at runtime
```

This mirrors the deployment skill's invariant: profiles hold `*_secret_ref` names; actual values live only in a secret store or protected CI environment.

### Hardening checklist for file-based secrets

- [ ] Real file listed in `.gitignore`; only `*.example` committed
- [ ] Permissions `0600` (owner-only); on Windows restrict via `icacls .env /inheritance:r /grant:r "%USERNAME%:F"`
- [ ] Values validated on load; failures fail loudly instead of defaulting silently
- [ ] Secrets never printed — always through `mask()`
- [ ] Rotation plan exists (the file is a snapshot; passwords expire)
- [ ] For production, prefer OS keyring or vault: `keyring.set_password("build-server", "deploy", pw)` and store only the lookup name in the file

---

## Pros and cons

| Criterion | Approach 1: Interactive CLI | Approach 2: Config file / .env |
|---|---|---|
| **Security — exposure** | Best: secrets live only in memory during the session; nothing touches disk unless the user opts in | Risk: secrets sit on disk — protected only by filesystem permissions and discipline |
| **Security — leakage paths** | Terminal scrollback of *non-secret* answers; shoulder-surfing while typing (mitigated by hidden input) | Accidental commits, loose permissions, backup/archive inclusion, other local processes reading the file |
| **UX — first run** | Excellent: guided, validated, self-documenting | Poor: user must know which keys are required and invent the file themselves |
| **UX — repeat runs** | Poor: re-typing everything each time | Excellent: zero interaction after setup |
| **Automation / CI** | Not usable (no human to answer prompts) | Required — the only viable option |
| **Reproducibility & audit** | Weak: nothing persisted to review later | Strong: the file is an inspectable record (keep real values out of Git, keep `.example` in) |
| **Error handling** | Immediate feedback per field | Fails at startup; needs clear "missing key" messages |

### Decision guide

- **One-off local tool, personal machine** → interactive wizard (optionally saving to `.env` at the end, as the sample does).
- **Repeated runs, cron jobs, CI pipelines** → `.env`/YAML file; use the wizard once to generate it.
- **Production servers** → neither plaintext passwords nor ad-hoc files: secret manager (vault/keyring/CI variables) referenced by name, exactly like this repository's `PRODUCTION_SSH_HOST` / `PRODUCTION_DATABASE_URL` pattern.

The strongest workflow combines all three layers: **wizard** for guided initial entry → **`.env.example`-templated file** for non-secret settings → **secret-store references** for anything sensitive.
