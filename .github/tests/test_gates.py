"""Exercise Muvyo signed-package and explicit plugin-withdrawal gates."""
import copy
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".github/scripts"))
from check_plugins import check, load, validate_catalog, validate_package, validate_transition, verify_index
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
RETIRED = {ROXY["id"]: {"withdrawn_sequence": 7}}


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
        validate_transition(self.after, self.after, set(), False, RETIRED)

    def test_same_version_repack_fails(self):
        current = index(7, [KURISU, ROXY])
        with self.assertRaisesRegex(ValueError, "increment its version"):
            validate_transition(current, self.before, {KURISU["id"]}, True, RETIRED)

    def test_rollback_sequence_fails(self):
        with self.assertRaisesRegex(ValueError, "never decrease"):
            validate_transition(self.before, self.after, set(), True, RETIRED)

    def test_new_signed_version_passes(self):
        current = index(8, [dict(KURISU, version="1.0.5")])
        validate_transition(current, self.after, {KURISU["id"]}, True, RETIRED)

    def test_new_version_without_sequence_increase_fails(self):
        current = index(7, [dict(KURISU, version="1.0.5")])
        with self.assertRaisesRegex(ValueError, "newer signed sequence"):
            validate_transition(current, self.after, {KURISU["id"]}, True, RETIRED)

    def test_metadata_only_rewrite_fails(self):
        current = index(8, [dict(KURISU, name="altered")])
        with self.assertRaisesRegex(ValueError, "without a new signed package"):
            validate_transition(current, self.after, set(), True, RETIRED)

    def test_withdrawal_requires_matching_record_and_sequence(self):
        validate_transition(self.after, self.before, {ROXY["id"]}, True, RETIRED)
        with self.assertRaisesRegex(ValueError, "reviewed retirement record"):
            validate_transition(self.after, self.before, {ROXY["id"]}, True, {})
        stale = {ROXY["id"]: {"withdrawn_sequence": 6}}
        with self.assertRaisesRegex(ValueError, "withdrawal must advance"):
            validate_transition(self.after, self.before, {ROXY["id"]}, True, stale)


class CatalogTests(unittest.TestCase):
    def test_active_list_and_retirement_records_need_no_branch_mapping(self):
        validate_catalog(INDEX, [ENTRY["id"]], RETIRED)

    def test_catalog_must_match_signed_index_without_duplicates(self):
        for catalog in ([], [ENTRY["id"], ENTRY["id"]], [ENTRY["id"], ROXY["id"]]):
            with self.subTest(catalog=catalog), self.assertRaisesRegex(ValueError, "unmapped plugin IDs"):
                validate_catalog(INDEX, catalog, RETIRED)

    def test_active_plugin_cannot_also_be_withdrawn(self):
        with self.assertRaisesRegex(ValueError, "both active and withdrawn"):
            validate_catalog(INDEX, [ENTRY["id"]], {ENTRY["id"]: {"withdrawn_sequence": 7}})

    def test_invalid_retirement_sequences_fail(self):
        for sequence in (0, -1, True, "7", INDEX["sequence"] + 1):
            with self.subTest(sequence=sequence), self.assertRaisesRegex(ValueError, "Invalid withdrawal sequence"):
                validate_catalog(INDEX, [ENTRY["id"]], {ROXY["id"]: {"withdrawn_sequence": sequence}})


class PullRequestGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="muvyo-pr-gate-")
        self.root = Path(self.temp.name).resolve()
        assert self.root.is_relative_to(Path(tempfile.gettempdir()).resolve())
        self.addCleanup(self.temp.cleanup)
        self.git("init", "-q", "-b", "main")
        self.git("config", "core.autocrlf", "false")
        self.git("config", "core.hooksPath", str(self.root / "disabled-hooks"))
        self.git("config", "user.name", "Muvyo Gate Test")
        self.git("config", "user.email", "gate@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        shutil.copytree(ROOT / "plugins", self.root / "plugins")
        for name in ("index.json", "index.json.sig", ".github/plugin-catalog.json", ".github/retired-plugins.json"):
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)
        self.commit("Published baseline")
        self.base = self.git("rev-parse", "HEAD")
        self.branch = "release/kurisu-1.0.5"
        self.git("switch", "-q", "-c", self.branch)

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.root), *args],
                                       stderr=subprocess.PIPE, text=True, encoding="utf-8").strip()

    def commit(self, message):
        self.git("add", ".")
        self.git("commit", "-q", "-m", message)

    def update_fixture_package(self, version_value):
        # These fixtures exercise layout/version gates; cryptographic verification is tested separately.
        manifest_path = self.root / ENTRY["path"] / "manifest.json"
        manifest = load(manifest_path)
        manifest.update(version=version_value, description="PR gate fixture")
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        signature_path = manifest_path.with_name("signature.json")
        signature = load(signature_path)
        signature["payload"]["version"] = version_value
        signature["payload"]["files"]["manifest.json"] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        signature_path.write_text(json.dumps(signature), encoding="utf-8")
        current = load(self.root / "index.json")
        current["sequence"] += 1
        current["plugins"][0].update(version=version_value, description="PR gate fixture")
        (self.root / "index.json").write_text(json.dumps(current), encoding="utf-8")
        self.commit("Update test package")

    def test_temporary_release_branch_accepts_new_version(self):
        self.update_fixture_package("1.0.5")
        current, _ = check(self.root, base=self.base, branch=self.branch)
        self.assertEqual(current["plugins"][0]["version"], "1.0.5")

    def test_temporary_branch_still_rejects_same_version_repack(self):
        self.update_fixture_package(ENTRY["version"])
        with self.assertRaisesRegex(ValueError, "increment its version"):
            check(self.root, base=self.base, branch=self.branch)

    def test_maintenance_branch_accepts_docs_without_touching_index(self):
        branch = "chore/update-local-debug-guide"
        self.git("switch", "-q", "-c", branch)
        (self.root / "README.md").write_text("Workflow documentation\n", encoding="utf-8")
        self.commit("Document workflow")
        current, _ = check(self.root, base=self.base, branch=branch)
        self.assertEqual(current, INDEX)

    def test_main_or_missing_pr_source_is_rejected(self):
        for branch in ("main", "", " ", None):
            with self.subTest(branch=branch), self.assertRaisesRegex(ValueError, "PR branch distinct from main"):
                check(self.root, base=self.base, branch=branch)


class SignatureTests(unittest.TestCase):
    def test_signed_index_passes_and_byte_change_fails(self):
        data = (ROOT / "index.json").read_bytes()
        signature = (ROOT / "index.json.sig").read_bytes()
        verify_index(data, signature)
        with self.assertRaises(InvalidSignature):
            verify_index(data + b" ", signature)


if __name__ == "__main__":
    unittest.main()
