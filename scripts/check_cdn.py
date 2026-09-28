#!/usr/bin/env python3
"""Warm public rules on jsDelivr and verify the exact published snapshot."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "deployment"))
from distribute import verify_cdn


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    args = parser.parse_args()
    manifest = json.loads((args.source / "manifest.json").read_text())
    result = subprocess.run(["gh", "api", "repos/" + args.repository + "/releases/latest"],
                            capture_output=True, text=True, check=True)
    tag = json.loads(result.stdout)["tag_name"]
    config = {"rules_delivery": "jsdelivr", "repository": args.repository, "_rules_tag": tag}
    count = verify_cdn(config, args.source, manifest["content_digest"])
    print("Verified and warmed %d public rule files on jsDelivr at %s" % (count, tag))


if __name__ == "__main__":
    main()
