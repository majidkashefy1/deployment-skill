import shutil
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "inventory-server.sh"

def _find_bash() -> str | None:
    for candidate in (
        Path("C:/Program Files/Git/bin/bash.exe"),
        Path("C:/Program Files/Git/usr/bin/bash.exe"),
    ):
        if candidate.exists():
            return str(candidate)
    found = shutil.which("bash")
    if found and "system32" not in found.lower():
        return found
    return None


BASH = _find_bash()


@unittest.skipIf(BASH is None, "bash not available on this machine")
class InventoryCliSmokeTests(unittest.TestCase):
    def run_script(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [BASH, str(SCRIPT), *args],
            capture_output=True,
            text=True,
        )

    def test_help_exits_zero_and_prints_usage(self):
        result = self.run_script("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("Usage:", result.stdout)
        self.assertIn("--root PATH", result.stdout)

    def test_unknown_option_exits_two(self):
        result = self.run_script("--definitely-not-an-option")
        self.assertEqual(result.returncode, 2)
        self.assertTrue(result.stderr.startswith("ERROR:"))

    def test_flag_without_value_exits_two(self):
        result = self.run_script("--root")
        self.assertEqual(result.returncode, 2)
        self.assertIn("--root requires a value", result.stderr)


if __name__ == "__main__":
    unittest.main()
