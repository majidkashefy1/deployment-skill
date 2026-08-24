#!/usr/bin/env python3
"""Collect connection settings interactively and persist them to a local env file.

Secrets are entered without echo, validated fields fail fast, and the review
screen masks the password. Dependency-free; standard library only.
"""

from __future__ import annotations

import argparse
import getpass
import os
import re
import stat
import subprocess
import sys


def ask(
    prompt: str,
    *,
    default: str | None = None,
    validator=None,
    secret: bool = False,
) -> str:
    while True:
        if secret:
            if sys.stdin.isatty():
                value = getpass.getpass(f"{prompt}: ")
            else:
                print("WARNING: stdin is not a terminal; secret will be echoed.", file=sys.stderr)
                value = input(f"{prompt}: ")
            if value.endswith("\r"):
                value = value[:-1]
        else:
            hint = f" [{default}]" if default else ""
            value = input(f"{prompt}{hint}: ").strip() or (default or "")
        if not value:
            print("  ! This field is required.")
            continue
        if validator and not validator(value):
            print("  ! Invalid format, try again.")
            continue
        return value


def valid_host(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?", value))


def valid_port(value: str) -> bool:
    return value.isdigit() and 1 <= int(value) <= 65535


def mask(secret_value: str) -> str:
    return "*" * min(len(secret_value), 8)


def restrict_permissions(path: str) -> None:
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError as error:
        print(f"WARNING: could not restrict permissions on {path}: {error}", file=sys.stderr)
        return
    if os.name == "nt":
        user = os.environ.get("USERNAME")
        if not user:
            return
        result = subprocess.run(
            ["icacls", path, "/inheritance:r", "/grant:r", f"{user}:F"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            print(f"WARNING: icacls restriction failed on {path}: {detail}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description="Interactive connection-setup wizard")
    parser.add_argument("--output", default=".env", help="target env file (default: .env)")
    args = parser.parse_args()

    if os.path.exists(args.output):
        answer = input(f"{args.output} exists. Append to it? [y/N] ").strip().lower()
        if answer != "y":
            print("Aborted.")
            return 1

    print("Connection setup, press Ctrl+C to cancel.\n")
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
    for key, value in config.items():
        shown = mask(value) if key == "SERVER_PASSWORD" else value
        print(f"  {key:<16} {shown}")

    if input("\nSave these values? [y/N] ").strip().lower() != "y":
        print("Values discarded.")
        return 1

    with open(args.output, "a", encoding="utf-8") as handle:
        handle.write("\n".join(f'{key}="{value}"' for key, value in config.items()) + "\n")
    restrict_permissions(args.output)
    print(f"Saved to {args.output}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
