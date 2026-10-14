"""Repository gates for encrypted Muvyo mascot packages; never loads private keys."""
import argparse
import base64
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPO_KEY = "OrE/bKpRWyYs0JBSjCz1WVZp8YCt3KQuxqd6K2GPfK4="
OFFICIAL_SHA256 = "ae0187203f68fb2e97b9ebbaf3d7f19f4e879a5a9ef5841ef953aa52f7fbb4de"
FRAMES = {"idle", "idle_blink", "idle_talk", "look_left", "look_upleft", "look_right",
          "waveA", "waveB", "point_left", "popcorn", "thumbs", "jump", "crouch", "sitsmile"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def version(value):
    require(isinstance(value, str) and re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", value),
            f"Invalid numeric release version: {value!r}")
    return tuple(map(int, value.split(".")))


def package_files(folder):
    require(folder.is_dir() and not folder.is_symlink(), f"Not a package directory: {folder}")
    result = {}
    for path in folder.iterdir():
        require(path.is_file() and not path.is_symlink(), f"Not a regular package file: {path}")
        require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", path.name), f"Unsafe filename: {path.name}")
        result[path.name] = path.read_bytes()
    return result


def validate_package(entry, folder):
    return validate_package_files(entry, package_files(folder))


def validate_package_files(entry, files):
    require(entry["path"] == f"plugins/{entry['id']}", f"Unexpected package path: {entry['path']}")
    manifest = json.loads(files["manifest.json"])
    signature = json.loads(files["signature.json"])
    version(manifest["version"])
    for key in ("id", "name", "version", "description", "author", "api"):
        require(entry[key] == manifest[key], f"Index/manifest mismatch: {entry['id']} {key}")
    payload = signature["payload"]
    require(payload["plugin_id"] == manifest["id"] and payload["version"] == manifest["version"],
            "Signature identity/version mismatch")
    require(set(files) == set(payload["files"]) | {"signature.json"}, "Unlisted or missing package files")
    for name, digest in payload["files"].items():
        require(hashlib.sha256(files[name]).hexdigest() == digest, f"Package hash mismatch: {name}")
    require("encrypted.json" in payload["files"] and manifest["entry"] not in files,
            "Only encrypted plugin entry points may be published")
    encrypted = json.loads(files["encrypted.json"])
    require(encrypted["version"] == 1 and encrypted["alg"] == "x25519-hkdf-sha256-aes256gcm",
            "Unsupported encrypted package format")
    permissions = manifest.get("permissions", {})
    require(set(permissions) <= {"domains", "muvyo"} and not permissions.get("domains")
            and not permissions.get("muvyo"), "Mascot packages must not request service/network permissions")
    capabilities = manifest["capabilities"]
    require(set(capabilities) == {"mascot"}, "Only mascot capability is permitted in this repository")
    require(set(capabilities["mascot"]["frames"]) == FRAMES, "Repository standard requires all 14 actions")
    return manifest


def validate_distribution_file(name, data):
    require(not re.search(r"(^|/)(private|src|sources|artifacts|deployment|__pycache__)(/|$)", name)
            and not re.search(r"(?i)(^|/)(mv_addon\.py|[^/]*signing[^/]*\.json)$", name)
            and not re.search(r"(?i)\.(pem|key|mp4|pyc|zip|js)$", name),
            f"Non-distribution/private file is tracked: {name}")
    require(not re.search(rb"-----BEGIN (?:[A-Z0-9]+ )?PRIVATE KEY-----", data),
            f"Private key content is tracked: {name}")


def validate_catalog(index, catalog, retired):
    require(isinstance(catalog, list) and all(isinstance(pid, str) for pid in catalog),
            "Plugin catalog must be a list of plugin IDs")
    ids = [entry["id"] for entry in index["plugins"]]
    require(len(catalog) == len(set(catalog)) and len(ids) == len(set(ids))
            and set(ids) == set(catalog), "Duplicate or unmapped plugin IDs")
    for plugin_id in catalog:
        require(re.fullmatch(r"z2561221\.[a-z0-9]+(?:-[a-z0-9]+)*", plugin_id), "Unsafe plugin ID")
    require(isinstance(retired, dict), "Retirement records must be keyed by plugin ID")
    require(not (set(retired) & set(catalog)), "A plugin cannot be both active and withdrawn")
    for plugin_id, policy in retired.items():
        require(re.fullmatch(r"z2561221\.[a-z0-9]+(?:-[a-z0-9]+)*", plugin_id), "Unsafe retired plugin ID")
        require(isinstance(policy, dict) and type(policy.get("withdrawn_sequence")) is int
                and 0 < policy["withdrawn_sequence"] <= index["sequence"], "Invalid withdrawal sequence")


def validate_transition(current, previous, changed_ids, index_changed, retired):
    require(current["public_key"] == previous["public_key"] == REPO_KEY, "Repository signing identity changed")
    require(current["sequence"] >= previous["sequence"], "Index sequence must never decrease")
    if index_changed or changed_ids:
        require(current["sequence"] > previous["sequence"], "Changed index/packages require a newer signed sequence")
    old = {p["id"]: p for p in previous["plugins"]}
    new = {p["id"]: p for p in current["plugins"]}
    removed = set(old) - set(new)
    require(removed <= set(retired), "Removing an existing plugin requires a reviewed retirement record")
    for plugin_id in removed:
        policy = retired[plugin_id]
        require(policy["withdrawn_sequence"] == current["sequence"],
                f"Plugin withdrawal must advance the signed index sequence: {plugin_id}")
    for plugin_id in changed_ids & set(old) & set(new):
        require(version(new[plugin_id]["version"]) > version(old[plugin_id]["version"]),
                f"Changed package must increment its version: {plugin_id}")
    for plugin_id in set(old) & set(new) - changed_ids:
        require(new[plugin_id] == old[plugin_id], f"Index metadata changed without a new signed package: {plugin_id}")


def git(*args, root=ROOT):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True, encoding="utf-8").strip()


def verify_index(data, signature):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    key = Ed25519PublicKey.from_public_bytes(base64.b64decode(REPO_KEY, validate=True))
    key.verify(base64.b64decode(signature.strip(), validate=True), data)


def verify_official_packages(root, index):
    verifier = Path(os.environ.get("MV_ADDON_VERIFIER", ""))
    require(verifier.is_file(), "Fetch the pinned official mv_addon.py into a temporary CI path")
    require(hashlib.sha256(verifier.read_bytes()).hexdigest() == OFFICIAL_SHA256,
            "Official verifier is not the pinned Muvyo version")
    spec = importlib.util.spec_from_file_location("muvyo_official_verifier", verifier)
    require(spec is not None and spec.loader is not None, "Cannot load the official Muvyo verifier")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for entry in index["plugins"]:
        module.verify(type("Package", (), {"folder": str(root / entry["path"])})())


def check(root=ROOT, base=None, branch=None, verify=False):
    index = load(root / "index.json")
    require(index["public_key"] == REPO_KEY, "Unexpected repository public key")
    require(type(index["sequence"]) is int and index["sequence"] > 0, "Invalid index sequence")
    catalog = load(root / ".github/plugin-catalog.json")
    retired = load(root / ".github/retired-plugins.json")
    validate_catalog(index, catalog, retired)
    ids = [entry["id"] for entry in index["plugins"]]
    require({p.name for p in (root / "plugins").iterdir()} == set(ids), "Unindexed package directory")
    for entry in index["plugins"]:
        validate_package(entry, root / entry["path"])
    # No local author credentials, source material or generated build files in this distribution repository.
    tracked = git("ls-files", root=root).splitlines()
    for name in tracked:
        validate_distribution_file(name, (root / name).read_bytes())
    if base:
        previous = json.loads(git("show", f"{base}:index.json", root=root))
        paths = git("diff", "--name-only", base, "HEAD", root=root).splitlines()
        changed = {p.split("/")[1] for p in paths if p.startswith("plugins/")}
        require(isinstance(branch, str) and bool(branch.strip()) and branch != "main",
                "Use a PR branch distinct from main")
        validate_transition(index, previous, changed, "index.json" in paths, retired)
    if verify:
        verify_index((root / "index.json").read_bytes(), (root / "index.json.sig").read_bytes())
        verify_official_packages(root, index)
    print(f"Repository gate passed: {len(ids)} plugins, sequence {index['sequence']}")
    return index, catalog


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base")
    parser.add_argument("--branch")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    check(base=args.base, branch=args.branch, verify=args.verify)
