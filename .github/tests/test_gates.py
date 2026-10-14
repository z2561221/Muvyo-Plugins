"""Exercise Muvyo signed-package and explicit plugin-withdrawal gates."""
import copy
import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".github/scripts"))
from check_plugins import load, validate_package, validate_transition, verify_index
from cryptography.exceptions import InvalidSignature

INDEX = load(ROOT / "index.json")
ENTRY = INDEX["plugins"][0]
REPO_KEY = INDEX["public_key"]
KURISU = {
    "id": "z2561221.kurisu-mascot",
    "name": "克里斯蒂娜",
    "version": "1.0.4",
    "description": "牧濑红莉栖，天才神经科学少女，未来道具研究所成员。理性敏锐、嘴硬心软，陪你探索世界线。",
    "author": "Kurisu",
    "path": "plugins/z2561221.kurisu-mascot",
    "api": 1,
}
ROXY = {
    "id": "z2561221.roxy-mascot",
    "name": "洛琪希",
    "version": "1.0.0",
    "description": "洛琪希，蓝发双辫的米格路德族魔法师。温柔认真、博学可靠，陪你学习与探索。",
    "author": "Kurisu",
    "path": "plugins/z2561221.roxy-mascot",
    "api": 1,
}
RETIRED = {ROXY["id"]: {"branch": "worldlinefix/roxy", "withdrawn_sequence": 7}}


def index(sequence, plugins):
    return {"name": "未来道具研究所 · Muvyo", "sequence": sequence,
            "plugins": copy.deepcopy(plugins), "public_key": REPO_KEY}


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


class TransitionTests(unittest.TestCase):
    def setUp(self):
        self.before = index(6, [KURISU, ROXY])
        self.after = index(7, [KURISU])

    def test_unchanged_index_passes(self):
        validate_transition(self.after, self.after, set(), False, "worldlinefix/kurisu", RETIRED)

    def test_same_version_repack_fails(self):
        current = index(7, [KURISU, ROXY])
        with self.assertRaisesRegex(ValueError, "increment its version"):
            validate_transition(current, self.before, {KURISU["id"]}, True, "worldlinefix/kurisu", RETIRED)

    def test_rollback_sequence_fails(self):
        with self.assertRaisesRegex(ValueError, "never decrease"):
            validate_transition(self.before, self.after, set(), True, "worldlinefix/kurisu", RETIRED)

    def test_new_signed_version_passes(self):
        current = index(8, [dict(KURISU, version="1.0.5"), ROXY])
        validate_transition(current, self.after, {KURISU["id"]}, True, "worldlinefix/kurisu", RETIRED)

    def test_metadata_only_rewrite_fails(self):
        current = index(8, [dict(KURISU, name="altered"), ROXY])
        with self.assertRaisesRegex(ValueError, "without a new signed package"):
            validate_transition(current, self.after, set(), True, "worldlinefix/kurisu", RETIRED)

    def test_withdrawal_passes_only_on_assigned_branch_and_sequence(self):
        validate_transition(self.after, self.before, {ROXY["id"]}, True,
                            "worldlinefix/roxy", RETIRED)
        with self.assertRaisesRegex(ValueError, "must use"):
            validate_transition(self.after, self.before, {ROXY["id"]}, True,
                                "worldlinefix/kurisu", RETIRED)
        stale = {ROXY["id"]: {"branch": "worldlinefix/roxy", "withdrawn_sequence": 6}}
        with self.assertRaisesRegex(ValueError, "withdrawal must advance"):
            validate_transition(self.after, self.before, {ROXY["id"]}, True,
                                "worldlinefix/roxy", stale)


class SignatureTests(unittest.TestCase):
    def test_signed_index_passes_and_byte_change_fails(self):
        data = (ROOT / "index.json").read_bytes()
        signature = (ROOT / "index.json.sig").read_bytes()
        verify_index(data, signature)
        with self.assertRaises(InvalidSignature):
            verify_index(data + b" ", signature)


if __name__ == "__main__":
    unittest.main()
