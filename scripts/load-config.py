#!/usr/bin/env python3
"""Load connection settings from a local env file and verify them.

Reads KEY=VALUE pairs, checks file permissions, validates required keys, and
prints only masked secrets. Dependency-free; standard library only.
"""

from __future__ import annotations

import argparse
import os
import stat
import sys
from pathlib import Path

DEFAULT_REQUIRED = ("SERVER_ADDRESS", "USER_NAME")
SECRET_KEYS = ("SERVER_PASSWORD",)


def parse_env(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def check_permissions(path: Path) -> None:
    if os.name == "nt":
        return
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        print(
            f"WARNING: {path} is readable by group/others (mode {mode:o}); run: chmod 600 {path}",
            file=sys.stderr,
        )


def mask(value: str) -> str:
    return "*" * min(len(value), 8)


def main() -> int:
    parser = argparse.ArgumentParser(description="Load and verify connection settings")
    parser.add_argument("--env-file", default=".env", help="env file path (default: .env)")
    parser.add_argument(
        "--require",
        action="append",
        default=list(DEFAULT_REQUIRED),
        help="required key; repeatable (defaults: SERVER_ADDRESS, USER_NAME)",
    )
    args = parser.parse_args()

    path = Path(args.env_file)
    if not path.is_file():
        print(f"ERROR: env file not found: {path}", file=sys.stderr)
        return 2

    try:
        config = parse_env(path)
    except OSError as error:
        print(f"ERROR: cannot read {path}: {error}", file=sys.stderr)
        return 2

    check_permissions(path)

    missing = [key for key in args.require if not config.get(key)]
    if missing:
        print(f"ERROR: missing required keys: {', '.join(missing)}", file=sys.stderr)
        return 1

    address = config["SERVER_ADDRESS"]
    port = config.get("SERVER_PORT", "22")
    user = config["USER_NAME"]
    password_display = (
        mask(config["SERVER_PASSWORD"]) if config.get("SERVER_PASSWORD") else "(none)"
    )
    print(f'Connecting to {user}@{address}:{port} password={password_display}')
    return 0


if __name__ == "__main__":
    sys.exit(main())
