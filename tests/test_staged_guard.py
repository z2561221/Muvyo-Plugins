"""Verify the commit guard against real staged blobs, including image assets."""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".github/scripts"))
from check_staged import check
from cryptography.exceptions import InvalidSignature


class StagedGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="muvyo-staged-guard-")
        self.root = Path(self.temp.name).resolve()
        assert self.root.is_relative_to(Path(tempfile.gettempdir()).resolve())
        self.addCleanup(self.temp.cleanup)
        self.git("init", "-q")
        self.git("config", "core.autocrlf", "false")
        self.git("config", "core.safecrlf", "false")
        shutil.copytree(ROOT / "plugins", self.root / "plugins")
        for name in ("index.json", "index.json.sig"):
            shutil.copyfile(ROOT / name, self.root / name)
        self.git("add", "--", "index.json", "index.json.sig", "plugins")
        self.image = next((self.root / "plugins").glob("*/mascot-idle.webp"))

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.root), *args], stderr=subprocess.PIPE)

    def stage(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        self.git("add", "--", name)

    def test_signed_images_pass(self):
        self.assertEqual(check(self.root), 1)

    def test_unstaged_image_change_does_not_override_staged_bytes(self):
        self.image.write_bytes(b"unstaged change")
        self.assertEqual(check(self.root), 1)

    def test_staged_tampered_image_fails_even_if_worktree_restored(self):
        original = self.image.read_bytes()
        self.image.write_bytes(original + b"changed")
        self.git("add", "--", str(self.image.relative_to(self.root)))
        self.image.write_bytes(original)
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            check(self.root)

    def test_staged_index_change_requires_matching_signature(self):
        path = self.root / "index.json"
        original = path.read_bytes()
        self.stage("index.json", original + b" ")
        path.write_bytes(original)
        with self.assertRaises(InvalidSignature):
            check(self.root)

    def test_forbidden_files_fail_when_forced_into_index(self):
        for name in ("src/main.js", "muvyo-signing.json", "backup-signing.json",
                     "mv_addon.py", "bundle.zip", "secret.pem"):
            with self.subTest(name=name):
                self.stage(name, b"test fixture")
                with self.assertRaisesRegex(ValueError, "Non-distribution/private"):
                    check(self.root)
                self.git("rm", "--cached", "--", name)

    def test_private_key_header_in_unexpected_file_fails(self):
        self.stage("notes.txt", b"-----BEGIN " + b"PRIVATE KEY-----\nfixture only")
        with self.assertRaisesRegex(ValueError, "Private key content"):
            check(self.root)

    def test_nested_package_files_fail(self):
        name = str(self.image.parent.relative_to(self.root)).replace("\\", "/") + "/nested/image.webp"
        self.stage(name, b"image")
        with self.assertRaisesRegex(ValueError, "Nested files"):
            check(self.root)

    def test_missing_index_signature_fails(self):
        self.git("rm", "--cached", "--", "index.json.sig")
        with self.assertRaisesRegex(ValueError, "Stage both"):
            check(self.root)


if __name__ == "__main__":
    unittest.main()
