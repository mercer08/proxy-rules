#!/usr/bin/env python3
"""Publish a validated snapshot without force-pushing or exposing credentials."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from build import check_counts


def run(*args, cwd=None, check=True):
    return subprocess.run(args, cwd=cwd, check=check, text=True, capture_output=True)


def release(repo, tag, checkout, archive_dir):
    existing = run("gh", "api", "repos/%s/releases/tags/%s" % (repo, tag), check=False)
    if existing.returncode == 0:
        print("Release already exists: " + tag)
        return
    if "404" not in existing.stderr:
        raise RuntimeError("Cannot check release: " + existing.stderr)
    bundle = archive_dir / "rules.tar.gz"
    run("git", "archive", "--format=tar.gz", "--output=" + str(bundle), "HEAD", cwd=checkout)
    checksum = archive_dir / "rules.tar.gz.sha256"
    checksum.write_text(hashlib.sha256(bundle.read_bytes()).hexdigest() + "  rules.tar.gz\n")
    manifest = json.loads((checkout / "manifest.json").read_text())
    notes = archive_dir / "release-notes.md"
    notes.write_text("Validated Surge, Mihomo and Shadowrocket rules.\n\n"
                     "Upstream commit: `" + manifest["upstream"]["commit"] + "`\n\n"
                     "Community ad blocking is disabled in default fragments.\n\n"
                     "Counts:\n```json\n" + json.dumps(manifest["counts"], indent=2) + "\n```\n")
    run("gh", "release", "create", tag, str(bundle), str(checksum),
        str(checkout / "manifest.json"), str(checkout / "checksums.sha256"),
        "--repo", repo, "--verify-tag", "--title", tag, "--notes-file", str(notes))
    print("Published release: https://github.com/%s/releases/tag/%s" % (repo, tag))


def publish(source, repo, limits):
    manifest = json.loads((source / "manifest.json").read_text())
    url = "https://github.com/" + repo + ".git"
    with tempfile.TemporaryDirectory(prefix="proxy-rules-publish-") as temporary:
        directory = Path(temporary)
        checkout = directory / "checkout"
        checkout.mkdir()
        run("git", "init", "--initial-branch=release", cwd=checkout)
        run("git", "config", "user.name", "github-actions[bot]", cwd=checkout)
        run("git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com", cwd=checkout)
        run("git", "config", "credential.helper", "", cwd=checkout)
        run("git", "config", "--add", "credential.helper", "!gh auth git-credential", cwd=checkout)
        run("git", "remote", "add", "origin", url, cwd=checkout)
        found = run("git", "ls-remote", "--exit-code", "--heads", "origin", "release", cwd=checkout, check=False)
        if found.returncode not in (0, 2):
            raise RuntimeError("Cannot check release branch: " + found.stderr)
        if found.returncode == 0:
            run("git", "fetch", "--depth=1", "origin", "release", cwd=checkout)
            run("git", "checkout", "-B", "release", "FETCH_HEAD", cwd=checkout)
            previous = json.loads((checkout / "manifest.json").read_text())
            check_counts(manifest["counts"], previous, limits)
            if previous["content_digest"] == manifest["content_digest"]:
                head = run("git", "rev-parse", "HEAD", cwd=checkout).stdout.strip()
                refs = run("git", "ls-remote", "--tags", "--refs", "origin", cwd=checkout).stdout.splitlines()
                tags = sorted(line.split()[1].removeprefix("refs/tags/") for line in refs
                              if line.split()[0] == head and "/rules-" in line)
                if not tags:
                    raise RuntimeError("Release branch is missing its immutable version tag")
                # Recover a release upload that failed after the atomic Git push.
                release(repo, tags[-1], checkout, directory)
                print("No content changes; stable branch retained")
                return
            # This is an isolated generated-output checkout, never the main source tree.
            run("git", "rm", "-r", "--ignore-unmatch", ".", cwd=checkout)
        for path in source.iterdir():
            if path.is_dir():
                shutil.copytree(path, checkout / path.name)
            else:
                shutil.copy2(path, checkout / path.name)
        run("git", "add", ".", cwd=checkout)
        now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        tag = "rules-" + now + "-" + manifest["content_digest"][:10]
        run("git", "commit", "-m", "Publish " + tag, cwd=checkout)
        run("git", "tag", tag, cwd=checkout)
        # Branch and tag are updated together; existing history is preserved.
        run("git", "push", "--atomic", "origin", "HEAD:refs/heads/release", "refs/tags/" + tag, cwd=checkout)
        release(repo, tag, checkout, directory)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    args = parser.parse_args()
    config = json.loads((Path(__file__).resolve().parents[1] / "sources.json").read_text())
    if args.repository != config["publish_repository"]:
        parser.error("Repository does not match sources.json")
    publish(args.source, args.repository, config["count_change_limits"])
