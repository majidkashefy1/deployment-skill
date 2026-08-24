import importlib.util
import io
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"


def _load_module(module_name: str, filename: str):
    spec = importlib.util.spec_from_file_location(module_name, SCRIPTS_DIR / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sw = _load_module("setup_wizard_under_test", "setup-wizard.py")


class ValidHostTests(unittest.TestCase):
    def test_accepts_hostname(self):
        self.assertTrue(sw.valid_host("srv.internal"))

    def test_accepts_ipv4(self):
        self.assertTrue(sw.valid_host("192.168.1.10"))

    def test_accepts_single_label(self):
        self.assertTrue(sw.valid_host("buildserver"))

    def test_rejects_empty(self):
        self.assertFalse(sw.valid_host(""))

    def test_rejects_leading_dash_or_dot(self):
        self.assertFalse(sw.valid_host("-bad"))
        self.assertFalse(sw.valid_host(".bad"))

    def test_rejects_trailing_dot(self):
        self.assertFalse(sw.valid_host("host."))

    def test_rejects_spaces_and_at(self):
        self.assertFalse(sw.valid_host("a b"))
        self.assertFalse(sw.valid_host("user@host"))


class ValidPortTests(unittest.TestCase):
    def test_accepts_normal_port(self):
        self.assertTrue(sw.valid_port("22"))

    def test_accepts_boundaries(self):
        self.assertTrue(sw.valid_port("1"))
        self.assertTrue(sw.valid_port("65535"))

    def test_rejects_out_of_range(self):
        self.assertFalse(sw.valid_port("0"))
        self.assertFalse(sw.valid_port("65536"))

    def test_rejects_non_numeric(self):
        self.assertFalse(sw.valid_port("abc"))
        self.assertFalse(sw.valid_port("22 "))


class MaskTests(unittest.TestCase):
    def test_masks_long_secret_to_eight_stars(self):
        self.assertEqual(sw.mask("very-long-password"), "*" * 8)

    def test_masks_short_secret_to_its_length(self):
        self.assertEqual(sw.mask("abc"), "***")

    def test_masks_empty_secret(self):
        self.assertEqual(sw.mask(""), "")


class AskTests(unittest.TestCase):
    def test_reads_plain_value_with_default(self):
        with mock.patch("sys.stdin", new=io.StringIO("\n")):
            value = sw.ask("Port", default="22", validator=sw.valid_port)
        self.assertEqual(value, "22")

    def test_retries_until_validator_passes(self):
        with mock.patch("sys.stdin", new=io.StringIO("bad host\nsrv.internal\n")):
            value = sw.ask("Server address (hostname or IP)", validator=sw.valid_host)
        self.assertEqual(value, "srv.internal")

    def test_non_tty_secret_read_via_fallback(self):
        fake_stdin = mock.MagicMock(wraps=io.StringIO("s3cret\n"))
        fake_stdin.isatty = lambda: False
        with mock.patch("sys.stdin", new=fake_stdin):
            value = sw.ask("Password (input hidden)", secret=True)
        self.assertEqual(value, "s3cret")


if __name__ == "__main__":
    unittest.main()
