#!/usr/bin/env python3
"""Validate a server-deployment profile without third-party dependencies.

The project profile intentionally uses a conservative YAML subset: mappings,
sequences, scalar values, inline lists, comments, and nested indentation. The
validator rejects unsupported or malformed input instead of silently guessing.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any


class ProfileError(Exception):
    """Raised when the supported profile YAML cannot be parsed."""


MISSING = object()


def strip_comment(text: str) -> str:
    quote: str | None = None
    escaped = False
    for index, char in enumerate(text):
        if quote:
            if escaped:
                escaped = False
            elif char == "\\" and quote == '"':
                escaped = True
            elif char == quote:
                quote = None
        elif char in ("'", '"'):
            quote = char
        elif char == "#" and (index == 0 or text[index - 1].isspace()):
            return text[:index].rstrip()
    return text.rstrip()


def split_inline(value: str) -> list[str]:
    parts: list[str] = []
    start = 0
    quote: str | None = None
    escaped = False
    depth = 0
    for index, char in enumerate(value):
        if quote:
            if escaped:
                escaped = False
            elif char == "\\" and quote == '"':
                escaped = True
            elif char == quote:
                quote = None
        elif char in ("'", '"'):
            quote = char
        elif char in "[({":
            depth += 1
        elif char in "])}`" and depth:
            depth -= 1
        elif char == "," and depth == 0:
            parts.append(value[start:index].strip())
            start = index + 1
    if quote:
        raise ProfileError("unterminated quote in inline value")
    parts.append(value[start:].strip())
    return [part for part in parts if part]


def parse_scalar(value: str) -> Any:
    value = value.strip()
    if not value:
        return None
    if value in {"null", "Null", "NULL", "~"}:
        return None
    if value in {"true", "True", "TRUE"}:
        return True
    if value in {"false", "False", "FALSE"}:
        return False
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        return [] if not inner else [parse_scalar(item) for item in split_inline(inner)]
    if value.startswith("{") or value.endswith("}"):
        raise ProfileError(f"inline maps are not supported: {value}")
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        try:
            return ast.literal_eval(value)
        except (SyntaxError, ValueError) as error:
            raise ProfileError(f"invalid quoted scalar: {value}") from error
    if re.fullmatch(r"[-+]?\d+", value):
        return int(value)
    if re.fullmatch(r"[-+]?(?:\d+\.\d*|\d*\.\d+)", value):
        return float(value)
    return value


def split_mapping(text: str) -> tuple[str, str] | None:
    quote: str | None = None
    escaped = False
    for index, char in enumerate(text):
        if quote:
            if escaped:
                escaped = False
            elif char == "\\" and quote == '"':
                escaped = True
            elif char == quote:
                quote = None
        elif char in ("'", '"'):
            quote = char
        elif char == ":":
            key = text[:index].strip()
            rest = text[index + 1 :].strip()
            if not key:
                return None
            return key, rest
    return None


class MiniYaml:
    """Small, strict parser for the profile format used by this skill."""

    def __init__(self, text: str):
        self.lines: list[tuple[int, int, str]] = []
        for line_number, raw in enumerate(text.splitlines(), start=1):
            if "\t" in raw[: len(raw) - len(raw.lstrip())]:
                raise ProfileError(f"line {line_number}: tabs are not allowed for indentation")
            content = strip_comment(raw).strip()
            if not content:
                continue
            indent = len(raw) - len(raw.lstrip(" "))
            self.lines.append((line_number, indent, content))

    def parse(self) -> Any:
        if not self.lines:
            raise ProfileError("profile is empty")
        value, index = self.parse_block(0, self.lines[0][1])
        if index != len(self.lines):
            line_number = self.lines[index][0]
            raise ProfileError(f"line {line_number}: unexpected content")
        return value

    def parse_block(self, index: int, indent: int) -> tuple[Any, int]:
        if index >= len(self.lines):
            return None, index
        _, actual_indent, content = self.lines[index]
        if actual_indent != indent:
            raise ProfileError(f"line {self.lines[index][0]}: invalid indentation")
        if content == "-" or content.startswith("- "):
            return self.parse_list(index, indent)
        return self.parse_mapping(index, indent)

    def parse_mapping(self, index: int, indent: int) -> tuple[dict[str, Any], int]:
        result: dict[str, Any] = {}
        while index < len(self.lines):
            line_number, actual_indent, content = self.lines[index]
            if actual_indent < indent:
                break
            if actual_indent > indent:
                raise ProfileError(f"line {line_number}: unexpected indentation")
            if content == "-" or content.startswith("- "):
                break
            pair = split_mapping(content)
            if pair is None:
                raise ProfileError(f"line {line_number}: expected 'key: value'")
            key, raw_value = pair
            if key in result:
                raise ProfileError(f"line {line_number}: duplicate key '{key}'")
            index += 1
            if raw_value:
                result[key] = parse_scalar(raw_value)
                continue
            if index < len(self.lines) and self.lines[index][1] > indent:
                child_indent = self.lines[index][1]
                result[key], index = self.parse_block(index, child_indent)
            else:
                result[key] = None
        return result, index

    def parse_list(self, index: int, indent: int) -> tuple[list[Any], int]:
        result: list[Any] = []
        while index < len(self.lines):
            line_number, actual_indent, content = self.lines[index]
            if actual_indent < indent:
                break
            if actual_indent != indent or not (content == "-" or content.startswith("- ")):
                if actual_indent > indent:
                    raise ProfileError(f"line {line_number}: invalid list indentation")
                break
            rest = content[1:].strip()
            index += 1
            if not rest:
                if index < len(self.lines) and self.lines[index][1] > indent:
                    child_indent = self.lines[index][1]
                    item, index = self.parse_block(index, child_indent)
                else:
                    item = None
                result.append(item)
                continue

            pair = split_mapping(rest)
            if pair is None:
                result.append(parse_scalar(rest))
                continue

            key, raw_value = pair
            item: dict[str, Any] = {}
            if raw_value:
                item[key] = parse_scalar(raw_value)
            elif index < len(self.lines) and self.lines[index][1] > indent:
                child_indent = self.lines[index][1]
                item[key], index = self.parse_block(index, child_indent)
            else:
                item[key] = None

            if index < len(self.lines) and self.lines[index][1] > indent:
                child_indent = self.lines[index][1]
                extra, index = self.parse_block(index, child_indent)
                if not isinstance(extra, dict):
                    raise ProfileError(f"line {line_number}: list item continuation must be a mapping")
                for extra_key, extra_value in extra.items():
                    if extra_key in item:
                        raise ProfileError(f"line {line_number}: duplicate list-item key '{extra_key}'")
                    item[extra_key] = extra_value
            result.append(item)
        return result, index


def get_path(data: Any, path: str, default: Any = MISSING) -> Any:
    current = data
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def is_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate(profile: Any, operation_override: str | None) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    def require(path: str, expected: type | tuple[type, ...] | None = None) -> Any:
        value = get_path(profile, path)
        if value is MISSING or value is None:
            errors.append(f"missing required value: {path}")
            return None
        if expected is not None and not isinstance(value, expected):
            errors.append(f"{path} must be {expected}, got {type(value).__name__}")
        return value

    if not isinstance(profile, dict):
        return ["profile root must be a mapping"], []

    schema_version = require("schema_version", int)
    if isinstance(schema_version, int) and schema_version < 1:
        errors.append("schema_version must be at least 1")

    operation = operation_override or require("operation", str)
    if operation not in {"inventory", "bootstrap", "deploy", "rollback"}:
        errors.append("operation must be inventory, bootstrap, deploy, or rollback")

    project = require("project", dict) or {}
    for key in ("id", "slug", "repository", "production_branch", "environment"):
        if not is_nonempty_string(project.get(key)):
            errors.append(f"project.{key} is required and must be a non-empty string")
    if project.get("server_only") is not True:
        errors.append("project.server_only must be true")
    if project.get("cloud_deployment_enabled") is not False:
        errors.append("project.cloud_deployment_enabled must be false for this server-only skill")
    targets = project.get("allowed_deployment_targets")
    if not isinstance(targets, list) or "debian-server" not in targets:
        errors.append("project.allowed_deployment_targets must include debian-server")

    server = require("server", dict) or {}
    server_scope = profile.get("server_scope", server.get("scope"))
    if server_scope not in {"single-project", "multi-project"}:
        errors.append("server_scope must be single-project or multi-project")
    if profile.get("server_scope") and server.get("scope") and profile["server_scope"] != server["scope"]:
        errors.append("server_scope and server.scope must not disagree")
    deployment_directory = server.get("deployment_directory")
    if not is_nonempty_string(deployment_directory) or not deployment_directory.startswith("/"):
        errors.append("server.deployment_directory must be an absolute path")
    if server_scope == "multi-project" and not is_nonempty_string(server.get("projects_root")):
        errors.append("server.projects_root is required in multi-project mode")
    if server.get("operating_system") not in {None, "debian"}:
        warnings.append("server.operating_system is not debian; verify the selected server adapter")

    ssh = require("ssh", dict) or {}
    if not is_nonempty_string(ssh.get("host_secret_ref")):
        errors.append("ssh.host_secret_ref is required")
    if not (is_nonempty_string(ssh.get("user")) or is_nonempty_string(ssh.get("user_secret_ref"))):
        errors.append("ssh.user or ssh.user_secret_ref is required")
    auth_method = ssh.get("authentication_method")
    if auth_method not in {"ssh-key", "password", "agent"}:
        errors.append("ssh.authentication_method must be ssh-key, password, or agent")
    if ssh.get("strict_host_key_checking") is not True:
        errors.append("ssh.strict_host_key_checking must be true")
    if not is_nonempty_string(ssh.get("known_hosts_secret_ref")):
        errors.append("ssh.known_hosts_secret_ref is required")
    if auth_method == "ssh-key" and not is_nonempty_string(ssh.get("private_key_secret_ref")):
        errors.append("ssh.private_key_secret_ref is required for ssh-key authentication")
    if auth_method == "password" and not is_nonempty_string(ssh.get("password_secret_ref")):
        errors.append("ssh.password_secret_ref is required for password authentication")
    if ssh.get("require_non_root") is not True:
        warnings.append("ssh.require_non_root is not true; a dedicated non-root deploy user is recommended")

    stack = require("stack", dict) or {}
    supported_stacks = {"docker-compose", "docker-run", "systemd", "node", "python", "go", "java", "kubernetes", "static-site", "custom"}
    stack_type = stack.get("type")
    if stack_type not in supported_stacks:
        errors.append(f"stack.type must be one of: {', '.join(sorted(supported_stacks))}")
    if stack_type == "docker-compose":
        for key in ("compose_file", "compose_project_name", "app_service"):
            if not is_nonempty_string(stack.get(key)):
                errors.append(f"stack.{key} is required for docker-compose")
        if operation in {"deploy", "rollback"} and not is_nonempty_string(stack.get("build_command")):
            errors.append("stack.build_command is required for docker-compose deployment")

    containers = profile.get("containers", {})
    if not isinstance(containers, dict):
        errors.append("containers must be a mapping")
        containers = {}
    app = containers.get("app", {})
    if stack_type in {"docker-compose", "docker-run"}:
        if not isinstance(app, dict):
            errors.append("containers.app must be a mapping for container stacks")
            app = {}
        for key in ("image_name", "container_name", "service_name"):
            if not is_nonempty_string(app.get(key)):
                errors.append(f"containers.app.{key} is required for container stacks")
        for key in ("host_port", "container_port"):
            value = app.get(key)
            if not isinstance(value, int) or not 1 <= value <= 65535:
                errors.append(f"containers.app.{key} must be an integer from 1 to 65535")
        if isinstance(stack.get("app_service"), str) and app.get("service_name") != stack.get("app_service"):
            errors.append("stack.app_service must match containers.app.service_name")

    networking = profile.get("networking", {})
    if not isinstance(networking, dict):
        errors.append("networking must be a mapping")
        networking = {}
    public_path = networking.get("public_path")
    if public_path is not None and (not isinstance(public_path, str) or not public_path.startswith("/")):
        errors.append("networking.public_path must be null or start with '/'")
    if isinstance(public_path, str) and public_path != "/" and public_path.endswith("/"):
        warnings.append("networking.public_path has a trailing slash; normalize it before routing")
    proxy = networking.get("reverse_proxy")
    if proxy not in {None, "nginx", "caddy", "traefik", "haproxy"}:
        warnings.append(f"networking.reverse_proxy '{proxy}' is custom; provide an adapter")
    if proxy is not None and not is_nonempty_string(networking.get("upstream_address")):
        errors.append("networking.upstream_address is required when a reverse proxy is configured")
    if networking.get("domain") is None and networking.get("tls_enabled") is True:
        warnings.append("TLS is enabled without a domain; verify certificate provisioning for IP access")

    bootstrap = profile.get("bootstrap", {})
    if not isinstance(bootstrap, dict):
        errors.append("bootstrap must be a mapping")
        bootstrap = {}
    if operation == "bootstrap":
        if bootstrap.get("enabled") is not True:
            errors.append("bootstrap.enabled must be true for operation bootstrap")
        if bootstrap.get("require_confirmation") is not True:
            errors.append("bootstrap.require_confirmation must be true")
    elif bootstrap.get("enabled") is True:
        warnings.append("bootstrap.enabled is true but bootstrap settings are ignored outside operation bootstrap")

    storage = profile.get("storage", {})
    if not isinstance(storage, dict):
        errors.append("storage must be a mapping")
        storage = {}
    if storage.get("database_enabled") is True:
        if not is_nonempty_string(storage.get("database_type")):
            errors.append("storage.database_type is required when database_enabled is true")
        if not is_nonempty_string(storage.get("database_url_secret_ref")):
            errors.append("storage.database_url_secret_ref is required when database_enabled is true")
        if operation in {"deploy", "rollback"} and not is_nonempty_string(storage.get("migration_policy")):
            errors.append("storage.migration_policy is required for database-backed deployment")
    if storage.get("backup_enabled") is True and not isinstance(storage.get("backup_retention_days"), int):
        errors.append("storage.backup_retention_days is required when backup_enabled is true")

    conflict = require("conflict_detection", dict) or {}
    if conflict.get("enabled") is not True:
        errors.append("conflict_detection.enabled must be true")
    if conflict.get("policy") != "fail-closed":
        errors.append("conflict_detection.policy must be fail-closed")
    if conflict.get("fail_before_mutation") is not True:
        errors.append("conflict_detection.fail_before_mutation must be true")
    if conflict.get("unknown_owner_is_conflict") is not True:
        errors.append("conflict_detection.unknown_owner_is_conflict must be true")

    verification = require("verification", dict) or {}
    if verification.get("required") is not True:
        errors.append("verification.required must be true")
    if not is_nonempty_string(verification.get("health_url")):
        errors.append("verification.health_url is required")
    if not isinstance(verification.get("expected_status_codes"), list) or not verification["expected_status_codes"]:
        errors.append("verification.expected_status_codes must be a non-empty list")
    if not isinstance(verification.get("retry_count"), int) or verification["retry_count"] < 1:
        errors.append("verification.retry_count must be a positive integer")
    if verification.get("rollback_database_automatically") is True:
        errors.append("verification.rollback_database_automatically must be false")

    release = require("release", dict) or {}
    if release.get("automatic_database_rollback") is True:
        errors.append("release.automatic_database_rollback must be false")
    if not isinstance(release.get("keep_previous_releases"), int) or release["keep_previous_releases"] < 1:
        errors.append("release.keep_previous_releases must be a positive integer")

    def inspect_secrets(value: Any, path: str = "") -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                child_path = f"{path}.{key}" if path else key
                key_lower = key.lower()
                is_secret_key = any(token in key_lower for token in ("password", "private_key", "token", "api_key"))
                if is_secret_key and not key_lower.endswith("secret_ref") and child not in (None, {}) and not isinstance(child, dict):
                    errors.append(f"{child_path} must be null or a secret_ref, not a literal value")
                inspect_secrets(child, child_path)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                inspect_secrets(child, f"{path}[{index}]")

    inspect_secrets(profile)

    # Resource names must be unique within the profile unless explicitly null.
    named_resources: dict[str, list[str]] = {}
    for service_name, service in containers.items():
        if not isinstance(service, dict):
            continue
        for field in ("container_name", "image_name", "volume_name"):
            value = service.get(field)
            if isinstance(value, str) and value:
                named_resources.setdefault(f"{field}:{value}", []).append(service_name)
    for resource, owners in named_resources.items():
        if len(owners) > 1:
            warnings.append(f"resource {resource} appears in multiple services: {', '.join(owners)}")

    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a server-deployment YAML profile")
    parser.add_argument("--profile", default="deployment-profile.yml", help="profile path (default: deployment-profile.yml)")
    parser.add_argument("--operation", choices=["inventory", "bootstrap", "deploy", "rollback"], help="override profile operation")
    parser.add_argument("--json", action="store_true", help="emit machine-readable validation output")
    args = parser.parse_args()

    profile_path = Path(args.profile)
    if not profile_path.is_file():
        message = f"profile not found: {profile_path}"
        if args.json:
            print(json.dumps({"valid": False, "errors": [message], "warnings": []}))
        else:
            print(f"ERROR: {message}", file=sys.stderr)
        return 2

    try:
        profile = MiniYaml(profile_path.read_text(encoding="utf-8")).parse()
        errors, warnings = validate(profile, args.operation)
    except (OSError, UnicodeError, ProfileError) as error:
        if args.json:
            print(json.dumps({"valid": False, "errors": [str(error)], "warnings": []}))
        else:
            print(f"ERROR: {error}", file=sys.stderr)
        return 2

    result = {"valid": not errors, "errors": errors, "warnings": warnings, "profile": str(profile_path)}
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        if errors:
            print(f"Profile validation failed: {profile_path}")
            for error in errors:
                print(f"  ERROR: {error}")
        else:
            print(f"Profile validation passed: {profile_path}")
        for warning in warnings:
            print(f"  WARNING: {warning}")

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
