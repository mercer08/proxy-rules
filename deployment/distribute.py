#!/usr/bin/env python3
"""Mirror validated rule releases and privately render 3x-ui subscriptions."""
import argparse
import base64
import contextlib
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import string
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request


MAX_BUNDLE = 32 * 1024 * 1024
MAX_EXPANDED = 96 * 1024 * 1024
BUSINESS_RULE_SETS = {"lan-com", "wan-com", "futu-broker"}
PROFILE_FILES = ("surge.conf", "mihomo.yaml", "shadowrocket.conf", "shadowrocket.txt", "node.txt")


def profile_overrides(state):
    """Only recognized private account folders and filenames can override output."""
    root = Path(state) / "profile-overrides"
    result = {}
    if not root.exists():
        return result
    if root.is_symlink():
        raise ValueError("Unsafe override directory")
    for folder in root.iterdir():
        if not re.fullmatch(r"[a-f0-9]{24}", folder.name):
            continue
        if folder.is_symlink() or not folder.is_dir():
            raise ValueError("Unsafe account override directory")
        for name in PROFILE_FILES:
            path = folder / name
            if path.exists():
                if path.is_symlink() or not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
                    raise ValueError("Unsafe profile override")
                result[folder.name + "/" + name] = path.read_text()
    return result


def fetch(url, limit=MAX_BUNDLE, method=None, data=None):
    body = json.dumps(data).encode() if data is not None else None
    headers = {"User-Agent": "proxy-rules-distribution/1", "Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=60) as response:
        result = response.read(limit + 1)
    if len(result) > limit:
        raise ValueError("Download exceeds size limit")
    return result


def atomic_write(path, content, mode=0o600):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".write-")
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(content.encode() if isinstance(content, str) else content)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def switch_link(path, target):
    temporary = path.with_name(path.name + ".next")
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(target)
    os.replace(temporary, path)


def unpack_verified(bundle, archive_checksum, destination):
    """Reject traversal, links, omitted checksums and inconsistent manifests."""
    if hashlib.sha256(bundle).hexdigest() != archive_checksum:
        raise ValueError("Archive checksum mismatch")
    with tarfile.open(fileobj=io.BytesIO(bundle), mode="r:gz") as archive:
        total = 0
        names = set()
        for member in archive.getmembers():
            name = PurePosixPath(member.name)
            if name.is_absolute() or ".." in name.parts or not member.isfile() and not member.isdir():
                raise ValueError("Unsafe archive member")
            if str(name) in names:
                raise ValueError("Duplicate archive member")
            names.add(str(name))
            total += member.size
            if total > MAX_EXPANDED:
                raise ValueError("Expanded archive exceeds limit")
            path = destination.joinpath(*name.parts)
            if member.isdir():
                path.mkdir(parents=True, exist_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as source:
                    path.write_bytes(source.read())
    checksum_lines = (destination / "checksums.sha256").read_text().splitlines()
    checksums = {}
    for line in checksum_lines:
        digest, name = line.split("  ", 1)
        path = PurePosixPath(name)
        if not re.fullmatch(r"[a-f0-9]{64}", digest) or path.is_absolute() or ".." in path.parts or name in checksums:
            raise ValueError("Invalid checksum entry")
        checksums[name] = digest
    files = {str(p.relative_to(destination)) for p in destination.rglob("*") if p.is_file()}
    if files != set(checksums) | {"checksums.sha256"}:
        raise ValueError("Archive contains unchecked or missing files")
    for name, digest in checksums.items():
        if hashlib.sha256((destination / name).read_bytes()).hexdigest() != digest:
            raise ValueError("File checksum mismatch: " + name)
    manifest = json.loads((destination / "manifest.json").read_text())
    if manifest.get("schema_version") != 1:
        raise ValueError("Unsupported rule manifest")
    hashes = manifest["sha256"]
    if hashes != {k: v for k, v in checksums.items() if k != "manifest.json"}:
        raise ValueError("Manifest checksum list mismatch")
    content_digest = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    if manifest["content_digest"] != content_digest:
        raise ValueError("Rule content digest mismatch")
    for client, filename in [("surge", "rules.conf"), ("mihomo", "rules.yaml"), ("shadowrocket", "rules.conf")]:
        if not (destination / client / filename).is_file():
            raise ValueError("Missing client rule fragment")
    return manifest


def mirror(config):
    repository = config["repository"]
    metadata = json.loads(fetch("https://api.github.com/repos/" + repository + "/releases/latest"))
    tag = metadata["tag_name"]
    if not re.fullmatch(r"rules-[A-Za-z0-9-]+", tag):
        raise ValueError("Invalid rule release tag")
    state = Path(config["state_dir"])
    latest = state / "rules.json"
    if latest.exists() and json.loads(latest.read_text()).get("tag") == tag:
        return
    prefix = "https://github.com/" + repository + "/releases/download/" + tag + "/"
    urls = {asset["name"]: asset["browser_download_url"] for asset in metadata["assets"]}
    for name in ["rules.tar.gz", "rules.tar.gz.sha256"]:
        if urls.get(name) != prefix + name:
            raise ValueError("Unexpected rule asset URL")
    checksum = fetch(urls["rules.tar.gz.sha256"], limit=1024).decode().split()[0]
    if not re.fullmatch(r"[a-f0-9]{64}", checksum):
        raise ValueError("Invalid archive checksum")
    (state / "rules").mkdir(mode=0o700, exist_ok=True)
    releases = state / "rules/releases"
    releases.mkdir(mode=0o700, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".staging-", dir=releases) as temporary:
        staging = Path(temporary)
        manifest = unpack_verified(fetch(urls["rules.tar.gz"]), checksum, staging)
        version = manifest["content_digest"]
        destination = releases / version
        if not destination.exists():
            for path in staging.rglob("*"):
                os.chmod(path, 0o700 if path.is_dir() else 0o600)
            os.chmod(staging, 0o700)
            os.rename(staging, destination)
            # TemporaryDirectory must still find its original path on exit.
            staging.mkdir()
    atomic_write(latest, json.dumps({"tag": tag, "digest": version}) + "\n")
    print("Rules mirrored: " + tag)


def load_accounts(config, now=None):
    now = time.time() if now is None else now
    business_accounts = config.get("business_rule_accounts", [])
    if not isinstance(business_accounts, list) or any(not isinstance(email, str) or not email for email in business_accounts):
        raise ValueError("Business rule accounts must be a list of account identifiers")
    database = Path(config["database"]).resolve()
    connection = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
    connection.execute("BEGIN")
    try:
        accounts = {}
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        canonical = None
        membership = set()
        if {"clients", "client_inbounds"} <= tables:
            connection.row_factory = sqlite3.Row
            canonical = {row["sub_id"]: dict(row) for row in connection.execute("SELECT * FROM clients")}
            membership = {(row[0], row[1]) for row in connection.execute("SELECT client_id,inbound_id FROM client_inbounds")}
        rows = connection.execute("SELECT id,tag,enable,protocol,settings,stream_settings FROM inbounds").fetchall()
        for inbound_id, tag, enabled, protocol, settings_raw, stream_raw in rows:
            mapping = config["inbounds"].get(tag)
            if mapping is None or not enabled:
                continue
            stream = json.loads(stream_raw)
            if protocol != "vmess" or stream.get("network") != "ws":
                raise ValueError("Mapped inbound is no longer VMess/WebSocket")
            settings = json.loads(settings_raw)
            ws = stream.get("wsSettings") or {}
            for client in settings.get("clients", []):
                if canonical is not None:
                    primary = canonical.get(client.get("subId"))
                    if primary is None or (primary["id"], inbound_id) not in membership:
                        continue
                    client = {**client, "enable": bool(primary["enable"]), "id": primary["uuid"],
                              "email": primary["email"], "expiryTime": primary["expiry_time"]}
                if not client.get("enable", True):
                    continue
                expiry = client.get("expiryTime", 0)
                if expiry < 0:
                    # A pending first-use account is published only after 3x-ui activates it.
                    continue
                if expiry and expiry <= now * 1000:
                    continue
                # The original subId identifies an account, but is never a public download token.
                account_id = client.get("subId")
                if not account_id or not client.get("id"):
                    raise ValueError("Client is missing subscription identity")
                email = client.get("email", "account")
                label = config.get("account_labels", {}).get(email, email)
                account = accounts.setdefault(account_id, {
                    "label": label, "nodes": [], "expiry": expiry,
                    "business_rules": email in business_accounts})
                node = {"name": mapping["name"], "type": "vmess", "server": config["server"],
                        "port": config["port"], "uuid": client["id"], "alterId": 0,
                        "cipher": "aes-128-gcm", "tls": True, "skip-cert-verify": False,
                        "network": "ws", "udp": bool(mapping.get("udp", False)),
                        "ws-opts": {"path": ws["path"], "headers": {"Host": config["server"]}}}
                account["nodes"].append(node)
        for account in accounts.values():
            order = {mapping["name"]: index for index, mapping in enumerate(config["inbounds"].values())}
            account["nodes"].sort(key=lambda node: order[node["name"]])
            names = [n["name"] for n in account["nodes"]]
            if len(names) != len(set(names)):
                raise ValueError("Duplicate node names in an account")
        return accounts
    finally:
        connection.close()


def substore(config, account_key, nodes):
    base = config["substore_url"].rstrip("/")
    # Stable, non-secret internal names; raw subIds never appear in Sub-Store logs.
    name = "dmit-" + hashlib.sha256(account_key.encode()).hexdigest()[:16]
    path = base + "/api/sub/" + name
    subscription = {"name": name, "source": "local", "content": json.dumps({"proxies": nodes}), "process": []}
    # Some releases return 500 for GET /api/sub/:name when the item is absent.
    # Inventory avoids that buggy missing-item route.
    inventory = json.loads(fetch(base + "/api/subs", limit=1024 * 1024))
    if inventory.get("status") != "success" or not isinstance(inventory.get("data"), list):
        raise ValueError("Sub-Store inventory is unavailable")
    existing = next((item for item in inventory["data"] if item.get("name") == name), None)
    if existing is None:
        result = json.loads(fetch(base + "/api/subs", method="POST", data=subscription))
    else:
        result = json.loads(fetch(path, method="PATCH", data=subscription))
    if result.get("status") != "success":
        raise ValueError("Sub-Store failed to store subscription")
    result = {}
    for target in ["Surge", "ClashMeta", "URI"]:
        query = urllib.parse.urlencode({"target": target, "noCache": "true", **({"produceType": "internal"} if target == "ClashMeta" else {})})
        result[target] = fetch(base + "/download/" + name + "?" + query, limit=1024 * 1024).decode()
    proxies = json.loads(result["ClashMeta"])
    if not isinstance(proxies, list) or len(proxies) != len(nodes):
        raise ValueError("Sub-Store changed the node count")
    for produced, node in zip(proxies, nodes):
        for key in ["name", "type", "server", "port", "uuid", "tls", "network", "udp", "ws-opts"]:
            if produced.get(key) != node[key]:
                raise ValueError("Sub-Store changed a required node property")
        if produced.get("skip-cert-verify") is True:
            raise ValueError("Sub-Store disabled certificate verification")
    result["proxies"] = proxies
    return result


def rewrite_rules(fragment, config, digest):
    original = "https://raw.githubusercontent.com/" + config["repository"] + "/release/"
    replacement = rule_origin(config, digest)
    return fragment.replace(original, replacement)


def rule_origin(config, digest):
    mode = config.get("rules_delivery", "mirror")
    if mode == "mirror":
        return config["public_url"].rstrip("/") + "/proxy-rules/" + digest + "/"
    if mode != "jsdelivr":
        raise ValueError("Unknown rule delivery mode")
    tag = config.get("_rules_tag", "")
    repository = config["repository"]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("Invalid CDN repository")
    if not re.fullmatch(r"rules-[A-Za-z0-9-]+", tag) or not tag.endswith("-" + digest[:10]):
        raise ValueError("CDN tag must identify the validated snapshot")
    return "https://cdn.jsdelivr.net/gh/" + repository + "@" + tag + "/"


def verify_cdn(config, rules_dir, digest):
    """Warm only public rule files, checking each against the validated bundle."""
    origin = rule_origin(config, digest)
    files = set()
    raw = "https://raw.githubusercontent.com/" + config["repository"] + "/release/"
    for client, filename in (("surge", "rules.conf"), ("mihomo", "rules.yaml"), ("shadowrocket", "rules.conf")):
        fragment = select_rules((rules_dir / client / filename).read_text(), client)
        files.update(re.findall(re.escape(raw) + r"([a-z0-9-]+/[a-z0-9-]+\.(?:list|domainset|yaml))", fragment))
    if not files:
        raise ValueError("No public CDN rule files found")
    hashes = json.loads((rules_dir / "manifest.json").read_text())["sha256"]

    def check(filename):
        if hashlib.sha256(fetch(origin + filename)).hexdigest() != hashes[filename]:
            raise ValueError("CDN rule checksum mismatch")

    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(check, sorted(files)))
    return len(files)


def inline_business_rules(fragment, client, rules_dir):
    """Keep account-only rules in the private profile, preserving their order."""
    names = "(?:" + "|".join(sorted(BUSINESS_RULE_SETS)) + ")"
    if client == "mihomo":
        def provider(match):
            name = match.group(1)
            # The generated business providers have classical, JSON-quoted payloads.
            payload = (rules_dir / "mihomo" / (name + ".yaml")).read_text()
            if not payload.startswith("payload:\n"):
                raise ValueError("Unexpected business rule payload")
            return "  " + name + ":\n    type: inline\n    behavior: classical\n    payload:\n" + "".join(
                "    " + line + "\n" for line in payload.splitlines()[1:])
        return re.sub(r"(?ms)^  (" + names + r"):.*?(?=^  [a-z0-9-]+:\n|^rules:\n|\Z)", provider, fragment)

    def rules(match):
        name, policy = match.group(1), match.group(2)
        lines = ["# Account business rule set: " + name]
        for line in (rules_dir / client / (name + ".list")).read_text().splitlines():
            if not line or line.startswith("#"):
                continue
            parts = line.split(",")
            parts.insert(2, policy)
            lines.append(",".join(parts))
        return "\n".join(lines) + "\n"
    return re.sub(r"(?m)^RULE-SET,[^\n,]*/(" + names + r")\.list,([^,\n]+)\n?", rules, fragment)


def prepare_rules(fragment, client, config, rules_dir, digest, business_rules=False):
    fragment = select_rules(fragment, client, business_rules)
    if config.get("rules_delivery") == "jsdelivr" and business_rules:
        fragment = inline_business_rules(fragment, client, rules_dir)
    return rewrite_rules(fragment, config, digest)


def select_rules(fragment, client, business_rules=False):
    """Omit business routing and providers unless this account opts in."""
    if business_rules:
        return fragment
    names = "(?:" + "|".join(sorted(BUSINESS_RULE_SETS)) + ")"
    if client == "mihomo":
        fragment = re.sub(r"(?ms)^  " + names + r":\n.*?(?=^  [a-z0-9-]+:\n|^rules:\n|\Z)", "", fragment)
        return re.sub(r'(?m)^  - "RULE-SET,' + names + r',[^"\n]*"\n?', "", fragment)
    return re.sub(r"(?m)^RULE-SET,[^\n,]*/" + names + r"\.list,[^\n]*\n?", "", fragment)


def render_shadowrocket(config, rules_dir, digest, managed_url, business_rules=False):
    template = Path(config["templates_dir"]) / "shadowrocket.conf"
    text = string.Template(template.read_text()).substitute(MANAGED_URL="")
    text = re.sub(r"(?m)^update-url\s*=.*\n?", "", text)
    fragment = prepare_rules((rules_dir / "shadowrocket/rules.conf").read_text(), "shadowrocket", config, rules_dir, digest, business_rules)
    return text + fragment


def render_profiles(config, account, converted, token, rules_dir, digest):
    templates = Path(config["templates_dir"])
    origin = config["public_url"].rstrip("/")
    proxies = converted["proxies"]
    names = [p["name"] for p in proxies]
    surge_lines = [line for line in converted["Surge"].splitlines() if line.strip() and not line.startswith("#")]
    if len(surge_lines) != len(proxies) or any(not line.startswith(name + " =") and not line.startswith(name + "=") for name, line in zip(names, surge_lines)):
        raise ValueError("Unexpected Surge proxy export")
    # Policy options are distinct from VMess UDP capability.
    # Sub-Store 2.42.2 double-quotes a quoted Host value in its Surge exporter.
    # We only generate a single IP Host header, whose unquoted form is valid.
    surge_lines = [re.sub(r',ws-headers=.*?(?=,vmess-aead=|,tls=|$)',
                         ',ws-headers=Host:' + config["server"], line) + ", block-quic=on"
                   for line in surge_lines]
    common = {"PROXY_NAMES": ", ".join(names), "ORIGIN": origin}
    surge = string.Template((templates / "surge.conf").read_text()).substitute(
        common, MANAGED_URL="", PROXIES="\n".join(surge_lines))
    surge = re.sub(r"(?m)^#!MANAGED-CONFIG.*\n?", "", surge)
    business_rules = bool(account.get("business_rules", False))
    surge += prepare_rules((rules_dir / "surge/rules.conf").read_text(), "surge", config, rules_dir, digest, business_rules)
    mihomo_base = json.loads((templates / "mihomo.json").read_text())
    mihomo_base["proxies"] = proxies
    mihomo_base["proxy-groups"] = [{"name": "PROXY", "type": "select", "proxies": names}]
    fragment = prepare_rules((rules_dir / "mihomo/rules.yaml").read_text(), "mihomo", config, rules_dir, digest, business_rules)
    # DNS classifications follow the same ordered domain rules, including custom
    # overrides; do not let a broad domestic set override an explicit proxy set.
    behaviors = dict(re.findall(r'\n  ([a-z0-9-]+):\n    type: (?:http|inline)\n    behavior: (\w+)', fragment))
    dns_policy = {}
    for line in fragment.splitlines():
        if not line.startswith('  - "RULE-SET,'):
            continue
        rule = json.loads(line.strip()[2:]).split(',')
        name, policy = rule[1:3]
        if behaviors.get(name) == "ipcidr":
            continue
        if name in ("private", "lan-com"):
            resolver = ["system"]
        elif policy == "DIRECT":
            resolver = ["https://dns.alidns.com/dns-query"]
        elif policy == "PROXY":
            resolver = ["https://1.1.1.1/dns-query#PROXY"]
        else:
            resolver = ["rcode://refused"]
        dns_policy["rule-set:" + name] = resolver
    mihomo_base["dns"]["nameserver-policy"] = dns_policy
    filters = mihomo_base["dns"]["fake-ip-filter"]
    for name in ("private", "lan-com"):
        if name == "lan-com" and not business_rules:
            continue
        source = rules_dir / "surge" / (name + ".list")
        if source.exists():
            for line in source.read_text().splitlines():
                parts = line.split(',')
                if len(parts) == 2 and parts[0] in ("DOMAIN", "DOMAIN-SUFFIX"):
                    filters.append(("+." if parts[0] == "DOMAIN-SUFFIX" else "") + parts[1])
    # JSON is a YAML-compatible mapping; writing each top-level JSON value also
    # allows the already-validated YAML rule fragment to be appended unchanged.
    mihomo = "\n".join(json.dumps(key) + ": " + json.dumps(value, ensure_ascii=False) for key, value in mihomo_base.items()) + "\n"
    fragment = fragment.replace("    proxy: PROXY", "    proxy: DIRECT")
    mihomo += fragment
    uri = converted["URI"].strip()
    if not uri.startswith("vmess://"):
        try:
            uri = base64.b64decode(uri, validate=True).decode()
        except (ValueError, UnicodeError):
            raise ValueError("Unexpected URI subscription export") from None
    uris = uri.splitlines()
    if len(uris) != len(names) or any(not line.startswith("vmess://") for line in uris):
        raise ValueError("Unexpected URI node list")
    return {"surge.conf": surge, "mihomo.yaml": mihomo,
            "shadowrocket.txt": base64.b64encode(("\n".join(uris) + "\n").encode()).decode() + "\n",
            "node.txt": "\n".join(uris) + "\n",
            "shadowrocket.conf": render_shadowrocket(
                config, rules_dir, digest, origin + "/profiles/" + token + "/shadowrocket.conf", business_rules)}


def generate(config):
    state = Path(config["state_dir"])
    rule_state = json.loads((state / "rules.json").read_text())
    digest = rule_state["digest"]
    config = dict(config, _rules_tag=rule_state["tag"])
    rules_dir = state / "rules/releases" / digest
    accounts = load_accounts(config)
    overrides = profile_overrides(state)
    template_files = sorted(Path(config["templates_dir"]).glob("*"))
    template_hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in template_files if p.is_file()}
    fingerprint = hashlib.sha256(json.dumps({"config": config, "accounts": accounts, "rules": digest,
                                            "templates": template_hashes, "overrides": overrides,
                                            "generator": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}, sort_keys=True).encode()).hexdigest()
    current = state / "profiles.json"
    if current.exists() and json.loads(current.read_text()).get("fingerprint") == fingerprint:
        return
    if config.get("rules_delivery") == "jsdelivr":
        cdn_state = state / "cdn-verified.json"
        expected = {"tag": rule_state["tag"], "digest": digest, "origin": rule_origin(config, digest)}
        if not cdn_state.exists() or json.loads(cdn_state.read_text()) != expected:
            count = verify_cdn(config, rules_dir, digest)
            atomic_write(cdn_state, json.dumps(expected) + "\n")
            print("Public CDN rules verified: " + str(count))
    profiles_root = state / "profiles"
    profiles_root.mkdir(mode=0o700, exist_ok=True)
    generations = profiles_root / "generations"
    generations.mkdir(mode=0o700, exist_ok=True)
    records = []
    staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=generations))
    try:
        for account_key, account in accounts.items():
            # This is a private filesystem identifier, never an HTTP credential.
            folder = hashlib.sha256(account_key.encode()).hexdigest()[:24]
            converted = substore(config, account_key, account["nodes"])
            profiles = render_profiles(config, account, converted, "", rules_dir, digest)
            edited = []
            for name in profiles:
                if folder + "/" + name in overrides:
                    profiles[name] = overrides[folder + "/" + name]
                    edited.append(name)
            directory = staging / folder
            directory.mkdir()
            for name, content in profiles.items():
                (directory / name).write_text(content)
            records.append({"label": account["label"], "business_rules": account["business_rules"],
                            "nodes": [n["name"] for n in account["nodes"]], "edited": edited,
                            "files": {name: str(profiles_root / "current" / folder / name) for name in profiles}})
        shared = staging / "shared"
        shared.mkdir()
        shadowrocket = render_shadowrocket(config, rules_dir, digest,
                                           config["public_url"].rstrip("/") + "/proxy-config/shadowrocket.conf")
        (shared / "shadowrocket.conf").write_text(shadowrocket)
        os.chmod(staging, 0o700)
        for path in staging.rglob("*"):
            os.chmod(path, 0o700 if path.is_dir() else 0o600)
        destination = generations / (str(time.time_ns()) + "-" + fingerprint[:12])
        os.rename(staging, destination)
        switch_link(profiles_root / "current", destination)
        atomic_write(current, json.dumps({"fingerprint": fingerprint, "rules": digest, "accounts": records}, ensure_ascii=False, indent=2) + "\n")
        lines = ["# DMIT SSH 配置文件", "", "仅通过 SSH 下载配置；公网下载入口已关闭。", "",
                 "Surge/Mihomo 导入本地配置文件。Shadowrocket 先复制 node.txt 的 vmess 地址导入节点，再导入 shadowrocket.conf。", "",
                 "完整配置没有自动更新 URL。规则更新后需重新 SSH 导出完整配置。", ""]
        for record in records:
            lines.extend(["## " + record["label"], ""])
            lines.extend("- " + name + ": " + path for name, path in record["files"].items())
            lines.append("")
        atomic_write(state / "subscriptions.md", "\n".join(lines) + "\n")
        print("Profiles generated: %d accounts, rules %s" % (len(records), digest[:12]))
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def export_profiles(config, stream, label=None):
    """Write an SSH-streamed archive; each account gets an independent folder."""
    state = Path(config["state_dir"])
    records = json.loads((state / "profiles.json").read_text())["accounts"]
    if label is not None:
        records = [r for r in records if r["label"] == label]
        if len(records) != 1:
            raise ValueError("Account label must match one active account")
    readme = ("Surge: import surge.conf as a local profile.\n"
              "Mihomo: import mihomo.yaml as a local profile.\n"
              "Shadowrocket: import the vmess address in node.txt, then import shadowrocket.conf.\n"
              "No managed-profile URL. Download a new archive over SSH after rule updates.\n"
              "Share only this account folder.\n").encode()
    with tarfile.open(fileobj=stream, mode="w|gz") as archive:
        used = set()
        for record in records:
            folder = re.sub(r"[^\w.-]", "_", record["label"])
            if folder in ("", ".", "..") or folder in used:
                raise ValueError("Unsafe or duplicate export label")
            used.add(folder)
            for name, path in record["files"].items():
                member = archive.gettarinfo(path, arcname=folder + "/" + name)
                member.mode = 0o600
                member.uid = member.gid = 0
                member.uname = member.gname = ""
                with open(path, "rb") as content:
                    archive.addfile(member, content)
            member = tarfile.TarInfo(folder + "/README.txt")
            member.size = len(readme)
            member.mode = 0o600
            archive.addfile(member, io.BytesIO(readme))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["rules", "profiles", "export"])
    parser.add_argument("--account", help="Export only this account display label")
    parser.add_argument("--config", type=Path, default=Path("/etc/proxy-distribution/config.json"))
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", config["repository"]):
        raise ValueError("Invalid repository")
    if config.get("rules_delivery") != "jsdelivr":
        raise ValueError("SSH-only profiles require public rules on jsDelivr")
    state = Path(config["state_dir"])
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (state / "sync.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if args.action == "export":
            with contextlib.redirect_stdout(sys.stderr):
                generate(config)
            export_profiles(config, sys.stdout.buffer, args.account)
        else:
            (mirror if args.action == "rules" else generate)(config)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # HTTP error URLs / converter responses can contain credentials.
        # Keep errors useful while ensuring those payloads cannot enter journals.
        if isinstance(error, (urllib.error.HTTPError, urllib.error.URLError)):
            print("Distribution failed: network request (%s)" % getattr(error, "code", type(error).__name__), file=sys.stderr)
        else:
            print("Distribution failed: " + type(error).__name__, file=sys.stderr)
        raise SystemExit(1)
