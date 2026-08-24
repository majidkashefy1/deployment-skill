# Server Connection Guide

A practical, step-by-step guide for connecting to servers over **SSH**, **SFTP/SCP**, **RDP**, and related protocols — covering what you need before connecting, which tools to use on each platform, how to establish the connection, and how to troubleshoot failures.

> For what to do *after* connecting (diagnostics, resource checks, service health, security audit), see [SERVER_ASSESSMENT_PROTOCOL.md](SERVER_ASSESSMENT_PROTOCOL.md).

---

## 1. Information you need before connecting

Collect all of these first — a failed connection is usually missing information, not a broken server:

| Item | Example | Notes |
|---|---|---|
| Host address | `203.0.113.10` or `server.example.com` | Public IP or DNS name of the server |
| Protocol | SSH, SFTP, RDP | Must match the server's role (see §2) |
| Port | `22`, `3389`, `21`, `5900` | Default unless changed; confirm with admin |
| Username | `deploy`, `root`, `Administrator` | Prefer a dedicated non-root account |
| Credential | Private key (recommended) or password | Keys are stronger; see §4 |
| Key passphrase | — | If your private key is protected |
| Host key fingerprint | `SHA256:AbCd…` | To verify identity on first connect |

For this repository's deployment skill, these come from secret references (`PRODUCTION_SSH_HOST`, `PRODUCTION_SSH_USER`, `PRODUCTION_SSH_KNOWN_HOSTS`) in your CI/secret store — never from committed files.

---

## 2. Which protocol to use

| Protocol | Port (default) | Use for | Transport security |
|---|---|---|---|
| **SSH** | 22 | Shell access & administration of Linux/macOS servers | Encrypted ✅ |
| **SFTP** | 22 | File transfer over SSH | Encrypted ✅ |
| **SCP** | 22 | Simple one-shot file copies over SSH | Encrypted ✅ |
| **RDP** | 3389 | Graphical desktop of Windows Servers | Encrypted (NLA/TLS) ✅ |
| **FTPS** | 21 (+ passive range) | Legacy FTP with explicit TLS | Encrypted if configured ⚠️ |
| **FTP** | 21 | Legacy file transfer | Plaintext ❌ avoid |
| **VNC** | 5900+ | Remote graphical console (usually tunneled) | None by itself ❌ — tunnel via SSH |
| **HTTP/HTTPS** | 80/443 | Web applications served *by* the server | HTTPS only |

Rules of thumb:

- Linux server administration → **SSH**.
- Moving files to/from a Linux server → **SFTP or SCP** (never plain FTP).
- Windows Server desktop → **RDP**.
- Plain FTP transmits credentials in cleartext — use it only when there is truly no alternative, and change those credentials afterward.

---

## 3. Required software by platform

### Connecting *from* Windows

| Purpose | Tool |
|---|---|
| SSH shell | Built-in OpenSSH client (`ssh` in PowerShell/CMD) or **Windows Terminal** |
| GUI alternative | **PuTTY** + **Pageant** (agent) |
| File transfer (SFTP) | **WinSCP** or built-in `scp`/`sftp` commands |
| RDP client | Built-in **Remote Desktop Connection** (`mstsc.exe`) or **Windows App** |

Check/install the built-in client if missing:

```powershell
ssh -V                                  # prints version if installed
Add-WindowsCapability -Online -Name OpenSSH.Client~~~~0.0.1.0   # install via PowerShell (admin)
```

### Connecting *from* macOS / Linux

Everything is typically preinstalled:

```bash
ssh -V        # OpenSSH client
scp           # secure copy
sftp          # interactive SFTP session
```

Optional GUI tools: Termius, FileZilla (SFTP mode), Remmina (RDP/VNC), Microsoft Remote Desktop (macOS).

---

## 4. Prepare authentication (SSH keys recommended)

Password logins work but are weaker and often disabled on hardened servers. Set up a key once:

```bash
# On your local machine:
ssh-keygen -t ed25519 -a 100 -C "you@laptop"
# Creates:
#   ~/.ssh/id_ed25519      (private key — NEVER share or commit this)
#   ~/.ssh/id_ed25519.pub  (public key — safe to place on servers)
```

Copy the public key to the server:

```bash
ssh-copy-id deploy@203.0.113.10            # Linux/macOS
```

On Windows (no `ssh-copy-id`):

```powershell
type $env:USERPROFILE\.ssh\id_ed25519.pub | ssh deploy@203.0.113.10 "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys"
```

If password login is your only option right now, connect once with the password and add your public key manually as shown above.

---

## 5. Step-by-step: SSH connection

1. **Open a terminal** (PowerShell, CMD, or Windows Terminal on Windows; any terminal on macOS/Linux).
2. **Run the basic command:**

   ```bash
   ssh username@host
   # e.g. ssh deploy@203.0.113.10
   ```

3. **Non-default port?** Add `-p`:

   ```bash
   ssh -p 2222 deploy@203.0.113.10
   ```

4. **Verify the host key on first connection.** You will see:

   ```text
   The authenticity of host '203.0.113.10' can't be established.
   ED25519 key fingerprint is SHA256:xxxxxxxxxxxxxxxxxxxxxxx.
   Are you sure you want to continue connecting (yes/no/[fingerprint])?
   ```

   Compare the fingerprint against the value from your server admin or secret store (`PRODUCTION_SSH_KNOWN_HOSTS`). Type `yes` only if it matches. This pins the server's identity and protects against man-in-the-middle attacks.

5. **Authenticate:** enter the account password or the private-key passphrase when prompted. Input is invisible while typing — that is normal.

6. **Confirm success:** you get a remote prompt. Sanity-check where you are:

   ```bash
   hostname; whoami; uname -a
   ```

7. **Disconnect cleanly:** run `exit` or press `Ctrl+D`.

### Useful one-line variants

```bash
ssh -i ~/.ssh/custom_key deploy@203.0.113.10     # specific private key
ssh -v deploy@203.0.113.10                       # verbose output for debugging (-vvv = max)
ssh deploy@203.0.113.10 'uptime'                 # run one command, then exit
```

### Save settings in an SSH config (recommended)

Create/edit `~/.ssh/config` (on Windows: `%USERPROFILE%\.ssh\config`):

```text
Host prod
    HostName 203.0.113.10
    User deploy
    Port 22
    IdentityFile ~/.ssh/id_ed25519
    IdentitiesOnly yes
    ServerAliveInterval 30
```

Then simply: `ssh prod`.

---

## 6. Step-by-step: file transfer (SFTP / SCP)

**SCP — quick single copy:**

```bash
scp ./release.tar.gz deploy@203.0.113.10:/opt/projects/my-app/    # push
scp deploy@203.0.113.10:/var/log/app.log ./app.log                # pull
scp -P 2222 file deploy@203.0.113.10:~/                           # non-default port uses capital -P
```

**SFTP — interactive browsing:**

```bash
sftp deploy@203.0.113.10
sftp> ls / put file.gz / get app.log / mkdir backup / bye
```

**WinSCP (GUI):** New Session → File protocol `SFTP` → host, port, username → select your private key under *Advanced → SSH → Authentication* → Login.

---

## 7. Step-by-step: RDP (Windows Server desktop)

1. Gather host address, port (default `3389`), username (`Administrator` or your account), and password.
2. Launch **Remote Desktop Connection** (`Win+R` → `mstsc`).
3. Enter `host[:port]` (use `203.0.113.10:13389` if non-default).
4. Enter credentials; accept the certificate warning only after verifying the certificate's fingerprint with the server owner.
5. Once at the desktop, disconnect via Start → Disconnect rather than closing the window abruptly if sessions should persist.

From macOS, install **Windows App** (formerly Microsoft Remote Desktop); from Linux, use **Remmina** (RDP plugin). For better security, restrict RDP to a VPN or tunnel it through SSH (`ssh -L 3389:localhost:3389 …`).

---

## 8. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `Connection timed out` | Wrong IP, firewall blocking, server down | Ping/test port: `nc -vz host 22`; check cloud firewall/security group |
| `Connection refused` | Service not listening or wrong port | Verify the daemon runs on the server; confirm the actual port |
| `Permission denied (publickey)` | Server requires keys and yours isn't installed | Re-run §4 key copy steps; check `~/.ssh` permissions are 700/600 |
| `Permission denied (password)` | Wrong password or password auth disabled | Reset credential or switch to key auth |
| `REMOTE HOST IDENTIFICATION HAS CHANGED!` | Server reinstalled **or** MITM attempt | Do NOT blindly proceed; verify new fingerprint out-of-band, then remove the stale line from `known_hosts` |
| `Too many authentication failures` | Agent offers too many keys | Add `IdentitiesOnly yes` + explicit `IdentityFile` |
| Session drops while idle | NAT/firewall timeout | Add `ServerAliveInterval 30` to `~/.ssh/config` |
| RDP: "client cannot connect" | NLA/port/firewall | Confirm port, enable Network Level Authentication, test with `nc -vz host 3389` |
| Works locally, fails remotely | Local ISP/corporate network blocks outbound ports | Try a hotspot or VPN to isolate |

Verbose SSH output is the fastest diagnostic: `ssh -vvv user@host`.

---

## 9. Security checklist

- [ ] Key-based auth enabled; password auth disabled where possible
- [ ] Root direct login disabled (`PermitRootLogin no`); use a named sudo account
- [ ] Host keys pinned/verified on first connection — never skipped
- [ ] Private keys protected by a passphrase and never committed to Git
- [ ] Non-standard management ports and VPN/tunnel access considered for internet-exposed servers
- [ ] Plain FTP and untunneled VNC avoided entirely
- [ ] Credentials stored in a secret manager, not in chat logs, scripts, or dotfiles

These match the deployment skill's invariants (`strict_host_key_checking`, `require_non_root`, secrets-by-reference-only).
