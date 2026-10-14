"""Check the Git index, including signed mascot images, before a local commit."""
import json
import subprocess
import sys
from pathlib import Path

from check_plugins import (REPO_KEY, require, validate_distribution_file,
                           validate_package_files, verify_index)


def staged_files(root):
    raw = subprocess.check_output(["git", "-C", str(root), "ls-files", "--stage", "-z"])
    entries = []
    for record in raw.split(b"\0"):
        if not record:
            continue
        metadata, path = record.split(b"\t", 1)
        mode, oid, stage = metadata.split()
        name = path.decode("utf-8")
        require(stage == b"0", f"Unresolved merge in staging area: {name}")
        require(mode in (b"100644", b"100755"), f"Not a regular staged file: {name}")
        entries.append((name, oid))
    result = subprocess.run(["git", "-C", str(root), "cat-file", "--batch"],
                            input=b"".join(oid + b"\n" for _, oid in entries),
                            capture_output=True, check=True)
    files, offset = {}, 0
    for name, oid in entries:
        end = result.stdout.index(b"\n", offset)
        found_oid, kind, size = result.stdout[offset:end].split()
        require(found_oid == oid and kind == b"blob", f"Invalid staged object: {name}")
        offset = end + 1
        files[name] = result.stdout[offset:offset + int(size)]
        offset += int(size) + 1
    return files


def check(root):
    files = staged_files(root)
    for name, data in files.items():
        validate_distribution_file(name, data)
    require({"index.json", "index.json.sig"} <= set(files), "Stage both index.json and index.json.sig")
    index = json.loads(files["index.json"])
    require(index["public_key"] == REPO_KEY, "Unexpected staged repository public key")
    verify_index(files["index.json"], files["index.json.sig"])
    ids = [entry["id"] for entry in index["plugins"]]
    require(len(ids) == len(set(ids)), "Duplicate staged plugin IDs")
    actual = {name.split("/")[1] for name in files if name.startswith("plugins/")}
    require(actual == set(ids), "Staged packages and index entries differ")
    for entry in index["plugins"]:
        prefix = f"plugins/{entry['id']}/"
        package = {name[len(prefix):]: data for name, data in files.items() if name.startswith(prefix)}
        require(all("/" not in name for name in package), "Nested files in staged package")
        validate_package_files(entry, package)
    return len(ids)


if __name__ == "__main__":
    try:
        count = check(Path(__file__).resolve().parents[2])
    except Exception as exc:
        # Never echo file contents, credential values or subprocess buffers.
        message = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        print(f"Staged distribution check failed: {message}", file=sys.stderr)
        raise SystemExit(1)
    print(f"Staged distribution check passed: {count} signed mascot package(s)")
