import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "validate-profile.py"
EXAMPLE_PROFILE = REPO_ROOT / "deployment-profile.example.yml"


def run_validator(*cli_args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *cli_args],
        capture_output=True,
        text=True,
    )


class ValidatorCliTests(unittest.TestCase):
    def test_example_profile_is_valid(self):
        result = run_validator("--profile", str(EXAMPLE_PROFILE))
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)

    def test_json_output_parses(self):
        result = run_validator("--profile", str(EXAMPLE_PROFILE), "--json")
        self.assertEqual(result.returncode, 0)
        json.loads(result.stdout)

    def test_operation_override_accepted(self):
        result = run_validator(
            "--profile", str(EXAMPLE_PROFILE), "--operation", "inventory"
        )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)

    def test_missing_profile_exits_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_validator("--profile", str(Path(tmp) / "absent.yml"))
        self.assertEqual(result.returncode, 2)

    def test_malformed_profile_exits_two(self):
        with tempfile.NamedTemporaryFile("w", suffix=".yml", delete=False) as handle:
            handle.write("project:\n\tid: tab-indented\n")
            path = Path(handle.name)
        try:
            result = run_validator("--profile", str(path))
        finally:
            path.unlink()
        self.assertEqual(result.returncode, 2)

    def test_duplicate_keys_rejected(self):
        with tempfile.NamedTemporaryFile("w", suffix=".yml", delete=False) as handle:
            handle.write("project:\n  id: first\n  id: second\n")
            path = Path(handle.name)
        try:
            result = run_validator("--profile", str(path))
        finally:
            path.unlink()
        self.assertIn(result.returncode, (1, 2))
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
