import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"


def _load_module(module_name: str, filename: str):
    spec = importlib.util.spec_from_file_location(module_name, SCRIPTS_DIR / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


lc = _load_module("load_config_under_test", "load-config.py")


def run_cli(*cli_args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-u", str(SCRIPTS_DIR / "load-config.py"), *cli_args],
        capture_output=True,
        text=True,
    )


class ParseEnvTests(unittest.TestCase):
    def test_parses_quotes_comments_and_blanks(self):
        with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as handle:
            handle.write(
                '# comment\n'
                '\n'
                'SERVER_ADDRESS="srv.internal"\n'
                "SERVER_PORT='2222'\n"
                'USER_NAME = deploy \n'
            )
            path = Path(handle.name)
        try:
            config = lc.parse_env(path)
        finally:
            path.unlink()
        self.assertEqual(
            config,
            {
                "SERVER_ADDRESS": "srv.internal",
                "SERVER_PORT": "2222",
                "USER_NAME": "deploy",
            },
        )

    def test_ignores_lines_without_equals(self):
        with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as handle:
            handle.write("not a pair\nKEY=1\n")
            path = Path(handle.name)
        try:
            config = lc.parse_env(path)
        finally:
            path.unlink()
        self.assertEqual(config, {"KEY": "1"})


class MaskTests(unittest.TestCase):
    def test_long_secret(self):
        self.assertEqual(lc.mask("0123456789"), "*" * 8)

    def test_none_like_empty(self):
        self.assertEqual(lc.mask(""), "")


class CliTests(unittest.TestCase):
    def test_missing_file_exits_two(self):
        result = run_cli("--env-file", "no-such-file.env")
        self.assertEqual(result.returncode, 2)

    def test_missing_required_keys_exits_one(self):
        with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as handle:
            handle.write('SERVER_PORT="22"\n')
            path = Path(handle.name)
        try:
            result = run_cli("--env-file", str(path))
        finally:
            path.unlink()
        self.assertEqual(result.returncode, 1)
        self.assertIn("SERVER_ADDRESS", result.stderr)

    def test_valid_file_exits_zero_and_masks_password(self):
        with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as handle:
            handle.write('SERVER_ADDRESS="h"\nUSER_NAME="u"\nSERVER_PASSWORD="topsecret"\n')
            path = Path(handle.name)
        try:
            result = run_cli("--env-file", str(path))
        finally:
            path.unlink()
        self.assertEqual(result.returncode, 0)
        self.assertIn("*" * 8, result.stdout)
        self.assertNotIn("topsecret", result.stdout + result.stderr)

    def test_custom_require_adds_key(self):
        with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as handle:
            handle.write('SERVER_ADDRESS="h"\nUSER_NAME="u"\n')
            path = Path(handle.name)
        try:
            result = run_cli("--env-file", str(path), "--require", "SERVER_PORT")
        finally:
            path.unlink()
        self.assertEqual(result.returncode, 1)


if __name__ == "__main__":
    unittest.main()
