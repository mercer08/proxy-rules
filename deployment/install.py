#!/usr/bin/env python3
"""Install a localhost backend, then publish validated profile download routes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile
import time

from distribute import atomic_write, fetch

NODE_VERSION = "24.15.0"
SUBSTORE_VERSION = "2.42.2"
BASE = Path("/opt/proxy-distribution")
CONFIG = Path("/etc/proxy-distribution/config.json")
NGINX_INCLUDE = "/etc/proxy-distribution/nginx.conf"


def run(*command):
    subprocess.run(command, check=True)


def insert_https_include(text):
    """Find the HTTPS server without counting braces inside comments/strings."""
    if "include " + NGINX_INCLUDE + ";" in text:
        return text
    blocks = []
    depth = 0
    start = None
    quote = None
    comment = False
    escaped = False
    for index, char in enumerate(text):
        if comment:
            if char == "\n":
                comment = False
            continue
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if quote:
            if char == quote:
                quote = None
            continue
        if char in ('"', "'"):
            quote = char
        elif char == "#":
            comment = True
        elif char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}":
            depth -= 1
            if depth < 0:
                raise ValueError("Unbalanced Nginx configuration")
            if depth == 0:
                blocks.append((start, index))
    if depth or quote:
        raise ValueError("Unbalanced Nginx configuration")
    matches = [(start, end) for start, end in blocks
               if re.search(r'\blisten\s+443\s+ssl\b', text[start:end])]
    if len(matches) != 1:
        raise ValueError("Expected exactly one existing HTTPS server")
    end = matches[0][1]
    return text[:end] + "    include " + NGINX_INCLUDE + ";\n" + text[end:]


def prepare(source):
    BASE.mkdir(parents=True, exist_ok=True)
    CONFIG.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    for name in ["distribute.py", "install.py", "nginx.conf", "config.example.json"]:
        if (source / name).resolve() != (BASE / name).resolve():
            shutil.copy2(source / name, BASE / name)
    for name in ["templates", "systemd"]:
        if (source / name).resolve() != (BASE / name).resolve():
            shutil.copytree(source / name, BASE / name, dirs_exist_ok=True)
    if not CONFIG.exists():
        atomic_write(CONFIG, (source / "config.example.json").read_bytes())
    config = json.loads(CONFIG.read_text())
    for path in [config["state_dir"], config["public_dir"], "/var/lib/sub-store"]:
        Path(path).mkdir(parents=True, exist_ok=True)
    os.chmod(config["state_dir"], 0o700)
    os.chmod(config["public_dir"], 0o755)
    node_dir = BASE / ("node-v" + NODE_VERSION + "-linux-x64")
    if not node_dir.exists():
        filename = node_dir.name + ".tar.xz"
        origin = "https://nodejs.org/dist/v" + NODE_VERSION + "/"
        hashes = fetch(origin + "SHASUMS256.txt", limit=64 * 1024).decode()
        expected = next(line.split()[0] for line in hashes.splitlines() if line.split()[-1] == filename)
        content = fetch(origin + filename, limit=64 * 1024 * 1024)
        if hashlib.sha256(content).hexdigest() != expected:
            raise ValueError("Node archive checksum mismatch")
        with tempfile.NamedTemporaryFile() as archive:
            archive.write(content)
            archive.flush()
            with tarfile.open(archive.name, mode="r:xz") as package:
                package.extractall(BASE, filter="data")
    metadata = json.loads(fetch("https://api.github.com/repos/sub-store-org/Sub-Store/releases/tags/" + SUBSTORE_VERSION))
    asset = next(item for item in metadata["assets"] if item["name"] == "sub-store.bundle.js")
    bundle = BASE / "sub-store.bundle.js"
    expected = asset.get("digest")
    if not expected or not expected.startswith("sha256:"):
        raise ValueError("Official Sub-Store asset is missing its checksum")
    if not bundle.exists() or "sha256:" + hashlib.sha256(bundle.read_bytes()).hexdigest() != expected:
        content = fetch(asset["browser_download_url"])
        if "sha256:" + hashlib.sha256(content).hexdigest() != expected:
            raise ValueError("Sub-Store bundle checksum mismatch")
        atomic_write(bundle, content, mode=0o644)
    if subprocess.run(["id", "proxy-substore"], capture_output=True).returncode:
        run("useradd", "--system", "--home-dir", "/var/lib/sub-store", "--shell", "/usr/sbin/nologin", "proxy-substore")
    shutil.chown("/var/lib/sub-store", user="proxy-substore")
    os.chmod("/var/lib/sub-store", 0o700)
    shutil.copy2(BASE / "systemd/sub-store.service", "/etc/systemd/system/sub-store.service")
    run("systemctl", "daemon-reload")
    run("systemctl", "enable", "--now", "sub-store.service")
    for _ in range(20):
        try:
            result = json.loads(fetch(config["substore_url"] + "/api/subs", limit=1024 * 1024))
            if result.get("status") == "success":
                return
        except OSError:
            pass
        time.sleep(.25)
    raise ValueError("Sub-Store is not ready")


def publish(nginx_site):
    config = json.loads(CONFIG.read_text())
    run("python3", str(BASE / "distribute.py"), "rules")
    run("python3", str(BASE / "distribute.py"), "profiles")
    original = nginx_site.read_text()
    candidate = insert_https_include(original)
    backup = CONFIG.parent / "backups"
    backup.mkdir(mode=0o700, exist_ok=True)
    atomic_write(backup / ("nginx-" + str(time.time_ns()) + ".conf"), original)
    atomic_write(Path(NGINX_INCLUDE), (BASE / "nginx.conf").read_bytes(), mode=0o644)
    atomic_write(nginx_site, candidate, mode=0o644)
    try:
        run("nginx", "-t")
        run("systemctl", "reload", "nginx")
    except subprocess.CalledProcessError:
        atomic_write(nginx_site, original, mode=0o644)
        raise
    for name in ["proxy-rules-sync.service", "proxy-rules-sync.timer", "proxy-profiles-sync.service", "proxy-profiles-sync.timer"]:
        shutil.copy2(BASE / "systemd" / name, Path("/etc/systemd/system") / name)
    run("systemctl", "daemon-reload")
    run("systemctl", "enable", "--now", "proxy-rules-sync.timer", "proxy-profiles-sync.timer")
    print("Download routes published; localhost Sub-Store API remains private")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "publish"])
    parser.add_argument("--nginx-site", type=Path, default=Path("/www/server/panel/vhost/nginx/179.253.248.30.conf"))
    arguments = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("Run on the VPS as root")
    if arguments.action == "prepare":
        prepare(Path(__file__).resolve().parent)
    else:
        publish(arguments.nginx_site)
