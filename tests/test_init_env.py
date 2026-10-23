"""Safety checks for local configuration initialization; no external services."""

import importlib.util
import stat
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("init_env", REPO_ROOT / "scripts/init-env.py")
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class InitializeEnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / ".env.example").write_text(
            (REPO_ROOT / ".env.example").read_text(encoding="utf-8"), encoding="utf-8"
        )

    def test_creates_private_configuration_with_generated_password(self):
        MODULE.initialize_env(self.root)
        env = self.root / ".env"
        content = env.read_text(encoding="utf-8")
        self.assertNotIn("replace-with-a-long-random-password", content)
        self.assertRegex(content, r"POSTGRES_PASSWORD=[a-f0-9]{64}\n")
        self.assertEqual(stat.S_IMODE(env.stat().st_mode), 0o600)

    def test_refuses_to_overwrite_existing_configuration(self):
        env = self.root / ".env"
        env.write_text("existing configuration", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            MODULE.initialize_env(self.root)
        self.assertEqual(env.read_text(encoding="utf-8"), "existing configuration")

    def test_refuses_symlink_without_changing_target(self):
        target = self.root / "existing"
        target.write_text("unchanged", encoding="utf-8")
        (self.root / ".env").symlink_to(target)
        with self.assertRaises(FileExistsError):
            MODULE.initialize_env(self.root)
        self.assertEqual(target.read_text(encoding="utf-8"), "unchanged")

    def test_bad_template_does_not_create_configuration(self):
        (self.root / ".env.example").write_text("missing placeholder", encoding="utf-8")
        with self.assertRaises(ValueError):
            MODULE.initialize_env(self.root)
        self.assertFalse((self.root / ".env").exists())


if __name__ == "__main__":
    unittest.main()
