"""Publish one immutable archive per signed plugin version, using the Actions token."""
import argparse
import hashlib
import json
import os
import subprocess
import tempfile
import zipfile
from pathlib import Path

from check_plugins import ROOT, check, git, package_files, require


def archive(folder, destination):
    # Stable bytes allow repeat runs to compare the published asset digest without replacing it.
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_STORED) as output:
        for name, data in sorted(package_files(folder).items()):
            info = zipfile.ZipInfo(f"{folder.name}/{name}", date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_STORED
            output.writestr(info, data)
    return hashlib.sha256(destination.read_bytes()).hexdigest()


def validate_asset(release, name, size, digest):
    require(not release["draft"] and not release["prerelease"], "Existing release is not a stable publication")
    assets = release["assets"]
    require(len(assets) == 1, "Release must contain exactly one archive; inspect incomplete releases manually")
    asset = assets[0]
    require(asset["name"] == name and asset["size"] == size and size > 0, "Release asset name/size mismatch")
    require(asset.get("state") == "uploaded" and asset.get("digest") == f"sha256:{digest}",
            "Published archive digest does not match the signed package; never overwrite it")


def api(endpoint, optional=False):
    result = subprocess.run(["gh", "api", endpoint], text=True, encoding="utf-8", capture_output=True)
    if optional and result.returncode and "(HTTP 404)" in result.stderr:
        return None
    require(result.returncode == 0, result.stderr.strip())
    return json.loads(result.stdout)


def verify_target(repo, tag, expected_sha=None):
    ref = api(f"repos/{repo}/git/ref/tags/{tag}")["object"]
    while ref["type"] == "tag":
        ref = api(f"repos/{repo}/git/tags/{ref['sha']}")["object"]
    require(ref["type"] == "commit", "Release tag must resolve to a commit")
    if expected_sha:
        require(ref["sha"] == expected_sha, "New release tag does not target the main merge commit")
    return ref["sha"]


def publish(dry_run=False):
    index, catalog = check(verify=True)
    sha = git("rev-parse", "HEAD")
    if not dry_run:
        require(os.environ.get("GITHUB_REF") == "refs/heads/main", "Publishing is only allowed from main")
        require(os.environ.get("GITHUB_SHA") == sha, "Checkout does not match the release event commit")
        repo = os.environ["GITHUB_REPOSITORY"]
        require(repo == "z2561221/Muvyo-Plugins", "Unexpected publication repository")
    with tempfile.TemporaryDirectory() as temp:
        for entry in index["plugins"]:
            release_name = catalog[entry["id"]]["release_name"]
            tag = f"{release_name}_v{entry['version']}"
            asset_name = f"{release_name.lower()}_v{entry['version']}.zip"
            asset_path = Path(temp) / asset_name
            digest = archive(ROOT / entry["path"], asset_path)
            size = asset_path.stat().st_size
            if dry_run:
                print(f"Would release {tag}: {asset_name}, {size} bytes, sha256:{digest}")
                continue
            existing = api(f"repos/{repo}/releases/tags/{tag}", optional=True)
            if existing is not None:
                validate_asset(existing, asset_name, size, digest)
                old_sha = verify_target(repo, tag)
                git("fetch", "origin", old_sha)
                require(not git("diff", "--name-only", old_sha, sha, "--", entry["path"]),
                        f"Existing tag has different package bytes: {tag}")
                print(f"Keep complete existing release unchanged: {tag}")
                continue
            require(api(f"repos/{repo}/git/ref/tags/{tag}", optional=True) is None,
                    f"Tag {tag} exists without a Release; recover it manually before retrying")
            notes = Path(temp) / f"{tag}.md"
            notes.write_text(
                f"{entry['name']} {entry['version']}\n\n{entry['description']}\n\n"
                "此 ZIP 归档保留 Muvyo 官方加密签名安装产物。安装请使用仓库的 main 索引。\n\n"
                f"插件 ID：{entry['id']}\n\nmain commit：{sha}\n\nSHA-256：{digest}\n", encoding="utf-8")
            subprocess.run(["gh", "release", "create", tag, str(asset_path), "--repo", repo,
                            "--title", tag, "--notes-file", str(notes), "--target", sha], check=True)
            validate_asset(api(f"repos/{repo}/releases/tags/{tag}"), asset_name, size, digest)
            verify_target(repo, tag, sha)
            print(f"Published and verified {tag}: {asset_name}, sha256:{digest}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    publish(parser.parse_args().dry_run)
