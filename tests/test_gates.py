"""Exercise failures that would otherwise publish altered or unsigned packages."""
import copy
import hashlib
import json
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".github/scripts"))
from check_plugins import load, validate_package, validate_transition, verify_index
from release_plugins import archive, validate_asset
from cryptography.exceptions import InvalidSignature

INDEX = load(ROOT / "index.json")
ENTRY = next(entry for entry in INDEX["plugins"] if entry["id"] == "z2561221.roxy-mascot")


class PackageGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name) / ENTRY["id"]
        shutil.copytree(ROOT / ENTRY["path"], self.folder)

    def test_published_package_passes(self):
        validate_package(ENTRY, self.folder)

    def test_changed_image_fails(self):
        path = self.folder / "mascot-idle.webp"
        path.write_bytes(path.read_bytes() + b"altered")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            validate_package(ENTRY, self.folder)

    def test_unlisted_plaintext_fails(self):
        (self.folder / "main.js").write_text("plaintext", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Unlisted"):
            validate_package(ENTRY, self.folder)

    def test_index_version_mismatch_fails(self):
        entry = dict(ENTRY, version="9.0.0")
        with self.assertRaisesRegex(ValueError, "Index/manifest mismatch"):
            validate_package(entry, self.folder)

    def test_service_permission_is_rejected_even_with_updated_hash(self):
        path = self.folder / "manifest.json"
        manifest = load(path)
        manifest["permissions"]["domains"] = ["example.com"]
        path.write_text(json.dumps(manifest), encoding="utf-8")
        signature_path = self.folder / "signature.json"
        signature = load(signature_path)
        signature["payload"]["files"]["manifest.json"] = hashlib.sha256(path.read_bytes()).hexdigest()
        signature_path.write_text(json.dumps(signature), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "service/network permissions"):
            validate_package(ENTRY, self.folder)

    def test_archive_is_deterministic_and_contains_exact_package_bytes(self):
        first, second = Path(self.temp.name) / "first.zip", Path(self.temp.name) / "second.zip"
        self.assertEqual(archive(self.folder, first), archive(self.folder, second))
        with zipfile.ZipFile(first) as output:
            self.assertEqual(set(output.namelist()), {f"{self.folder.name}/{p.name}" for p in self.folder.iterdir()})
            for path in self.folder.iterdir():
                self.assertEqual(output.read(f"{self.folder.name}/{path.name}"), path.read_bytes())


class TransitionTests(unittest.TestCase):
    def test_unchanged_infrastructure_passes(self):
        validate_transition(INDEX, INDEX, set(), False)

    def test_same_version_repack_fails(self):
        current = copy.deepcopy(INDEX)
        current["sequence"] += 1
        with self.assertRaisesRegex(ValueError, "increment its version"):
            validate_transition(current, INDEX, {ENTRY["id"]}, True)

    def test_rollback_sequence_fails(self):
        current = copy.deepcopy(INDEX)
        current["sequence"] -= 1
        with self.assertRaisesRegex(ValueError, "never decrease"):
            validate_transition(current, INDEX, set(), True)

    def test_new_signed_version_passes(self):
        current = copy.deepcopy(INDEX)
        current["sequence"] += 1
        next(p for p in current["plugins"] if p["id"] == ENTRY["id"])["version"] = "1.0.1"
        validate_transition(current, INDEX, {ENTRY["id"]}, True)

    def test_metadata_only_rewrite_fails(self):
        current = copy.deepcopy(INDEX)
        current["sequence"] += 1
        current["plugins"][0]["name"] = "altered"
        with self.assertRaisesRegex(ValueError, "without a new signed package"):
            validate_transition(current, INDEX, set(), True)


class SignatureAndReleaseTests(unittest.TestCase):
    def test_signed_index_passes_and_byte_change_fails(self):
        data = (ROOT / "index.json").read_bytes()
        signature = (ROOT / "index.json.sig").read_bytes()
        verify_index(data, signature)
        with self.assertRaises(InvalidSignature):
            verify_index(data + b" ", signature)

    def release(self):
        return {"draft": False, "prerelease": False, "assets": [
            {"name": "roxy.zip", "size": 123, "state": "uploaded", "digest": "sha256:abc"}]}

    def test_complete_archive_is_accepted(self):
        validate_asset(self.release(), "roxy.zip", 123, "abc")

    def test_incomplete_release_is_rejected(self):
        release = self.release()
        release["assets"] = []
        with self.assertRaisesRegex(ValueError, "exactly one"):
            validate_asset(release, "roxy.zip", 123, "abc")

    def test_existing_asset_digest_cannot_be_rewritten(self):
        with self.assertRaisesRegex(ValueError, "never overwrite"):
            validate_asset(self.release(), "roxy.zip", 123, "different")


if __name__ == "__main__":
    unittest.main()
