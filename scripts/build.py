#!/usr/bin/env python3
"""Build three client rule sets from one immutable Loyalsoldier snapshot."""
import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
SUPPORTED = {"DOMAIN", "DOMAIN-SUFFIX", "DOMAIN-KEYWORD", "IP-CIDR", "IP-CIDR6"}


def fetch(url, token=None, allow_missing=False):
    headers = {"User-Agent": "mercer08-proxy-rules", "Accept": "application/vnd.github+json"}
    # Never attach a GitHub token to raw URLs, redirects, or arbitrary hosts.
    if token and url.startswith("https://api.github.com/repos/"):
        headers["Authorization"] = "Bearer " + token
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            if allow_missing and error.code == 404:
                return None
            if error.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == 2:
                raise
        time.sleep(2 ** attempt)
    raise RuntimeError("Download failed")


def domain_name(value):
    if not value or value != value.strip() or any(c in value for c in ",/*+!\"'\\ \t"):
        raise ValueError("Invalid or unsupported domain: " + value)
    value = value.rstrip(".").lower().encode("idna").decode("ascii")
    if not re.fullmatch(r"[a-z0-9_.-]+", value) or any(not part for part in value.split(".")):
        raise ValueError("Invalid domain: " + value)
    return value


def validate_rule(line):
    parts = line.split(",")
    kind = parts[0]
    if kind not in SUPPORTED or len(parts) < 2:
        raise ValueError("Unsupported rule: " + line)
    if kind.startswith("IP-CIDR"):
        if len(parts) not in (2, 3) or (len(parts) == 3 and parts[2] != "no-resolve"):
            raise ValueError("IP rules cannot contain a policy: " + line)
        network = ipaddress.ip_network(parts[1], strict=False)
        if network.version != (6 if kind == "IP-CIDR6" else 4):
            raise ValueError("Wrong IP family: " + line)
        return (kind, str(network), "no-resolve")
    if len(parts) != 2:
        raise ValueError("Domain rules cannot contain a policy: " + line)
    if kind == "DOMAIN-KEYWORD":
        value = parts[1].lower()
        if not re.fullmatch(r"[a-z0-9_.-]+", value):
            raise ValueError("Invalid domain keyword: " + line)
    else:
        value = domain_name(parts[1])
    return (kind, value)


def payload_items(text):
    """Strict parser for the upstream's simple YAML payload, not general YAML."""
    started = False
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if not started:
            if line != "payload:":
                raise ValueError("Expected YAML payload at line " + str(number))
            started = True
            continue
        if not line.startswith("- "):
            raise ValueError("Unsupported YAML at line " + str(number))
        value = line[2:].strip()
        if value.startswith("'"):
            if not value.endswith("'"):
                raise ValueError("Invalid quoted payload")
            value = value[1:-1].replace("''", "'")
        elif value.startswith('"'):
            value = json.loads(value)
        if not value or any(c.isspace() for c in value):
            raise ValueError("Invalid payload item: " + value)
        yield value
    if not started:
        raise ValueError("Missing YAML payload")


def parse_upstream(text, kind):
    result = set()
    for value in payload_items(text):
        if kind == "domain":
            if value.startswith("+."):
                rule = ("DOMAIN-SUFFIX", domain_name(value[2:]))
            else:
                rule = ("DOMAIN", domain_name(value))
        elif kind == "ip":
            network = ipaddress.ip_network(value, strict=False)
            rule = ("IP-CIDR6" if network.version == 6 else "IP-CIDR", str(network), "no-resolve")
        else:
            raise ValueError("Unsupported source kind: " + kind)
        result.add(rule)
    if not result:
        raise ValueError("Empty source")
    return result


def custom_rules(path):
    return {validate_rule(line.strip()) for line in path.read_text().splitlines()
            if line.strip() and not line.lstrip().startswith("#")}


def matches(rule, domain=None, ip=None):
    kind, value = rule[:2]
    if kind.startswith("IP-CIDR"):
        return bool(ip and ipaddress.ip_address(ip) in ipaddress.ip_network(value))
    if not domain:
        return False
    domain = domain.lower().rstrip(".")
    if kind == "DOMAIN":
        return domain == value
    if kind == "DOMAIN-SUFFIX":
        return domain == value or domain.endswith("." + value)
    return value in domain


def custom_order(config):
    if any(item["name"] == "lan-com" for item in config.get("custom_sets", [])):
        raise ValueError("Private LAN rules cannot be published")
    return [("direct", "DIRECT"), ("proxy", "PROXY"), ("reject", "REJECT")] + [
        (item["name"], item["policy"]) for item in config.get("custom_sets", [])]


def custom_output_name(name):
    return "custom-" + name if name in ("direct", "proxy", "reject") else name


def effective_groups(sets, custom, ads, config=None):
    return [
        (sets["private"], "DIRECT"), (sets["lan"], "DIRECT"),
        *[(custom[name], policy) for name, policy in custom_order(config or {})],
        (sets["reject"] if ads else set(), "REJECT"),
        (sets.get("apple", set()), "DIRECT"),
        (sets["proxy"], "PROXY"), (sets["direct"], "DIRECT"),
        (sets["telegram"], "PROXY"), (sets["cn"], "DIRECT")]


def verify_cases(sets, custom, cases, ads, default, config=None):
    groups = effective_groups(sets, custom, ads, config)
    for case in cases:
        policy = default
        for rules, destination in groups:
            if any(matches(rule, case.get("domain"), case.get("ip")) for rule in rules):
                policy = destination
                break
        if policy != case["expected"]:
            raise ValueError("Routing check failed: " + json.dumps(case) + "; got " + policy)


def check_counts(counts, previous, limits):
    if not previous:
        return
    for name, count in counts.items():
        old = previous.get("counts", {}).get(name)
        if old and not limits["minimum_ratio"] <= count / old <= limits["maximum_ratio"]:
            raise ValueError("Abnormal count change for %s: %s -> %s" % (name, old, count))


def serialize_rule(rule, policy=None):
    parts = list(rule)
    if policy:
        parts.insert(2, policy)
    return ",".join(parts)


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def yaml_payload(items):
    return ("payload:\n" + "".join("  - " + json.dumps(item, ensure_ascii=False) + "\n" for item in items)
            if items else "payload: []\n")


def render(output, sets, custom, config):
    all_sets = dict(sets)
    all_sets.update({custom_output_name(name): rules for name, rules in custom.items()})
    for name, rules in all_sets.items():
        ordered = sorted(rules)
        classical = [serialize_rule(rule) for rule in ordered]
        for client in ("surge", "shadowrocket"):
            write(output / client / (name + ".list"), "# Generated rules; no policy names.\n" + "\n".join(classical) + "\n")
        if name in sets and config["sets"][name]["kind"] == "domain":
            payload = [("+." if rule[0] == "DOMAIN-SUFFIX" else "") + rule[1] for rule in ordered]
            # Surge's optimized DOMAIN-SET preserves exact vs suffix semantics.
            write(output / "surge" / (name + ".domainset"), "\n".join(
                ("." if rule[0] == "DOMAIN-SUFFIX" else "") + rule[1] for rule in ordered) + "\n")
        elif name in sets:
            payload = [rule[1] for rule in ordered]
        else:
            payload = classical
        write(output / "mihomo" / (name + ".yaml"), yaml_payload(payload))

    base = "https://raw.githubusercontent.com/" + config["publish_repository"] + "/release/"
    order = [("private", "DIRECT"), ("lan", "DIRECT"),
             *[(custom_output_name(name), policy) for name, policy in custom_order(config)],
             ("reject", "REJECT"), *(([("apple", "APPLE")] if "apple" in sets else [])), ("proxy", "PROXY"), ("direct", "DIRECT"),
             ("telegram", "PROXY"), ("cn", "DIRECT")]
    for ads in (False, True):
        suffix = "-ads" if ads else ""
        active = [(name, policy) for name, policy in order if all_sets[name] and (ads or name != "reject")]
        for client in ("surge", "shadowrocket"):
            lines = ["# Rule fragment only: define PROXY and APPLE policy/groups in your profile.", "[Rule]"]
            for name, policy in active:
                domainset = client == "surge" and name in sets and config["sets"][name]["kind"] == "domain"
                rule_type = "DOMAIN-SET" if domainset else "RULE-SET"
                ext = ".domainset" if domainset else ".list"
                lines.append("%s,%s%s/%s%s,%s" % (rule_type, base, client, name, ext, policy))
            lines.append("FINAL," + config["default_policy"])
            write(output / client / ("rules" + suffix + ".conf"), "\n".join(lines) + "\n")
        lines = ["# Merge this fragment into a full profile with PROXY and APPLE groups.", "rule-providers:"]
        for name, _ in active:
            behavior = config["sets"][name]["kind"] if name in sets else "classical"
            if behavior == "ip":
                behavior = "ipcidr"
            lines.extend(["  " + name + ":", "    type: http", "    behavior: " + behavior,
                          "    format: yaml", "    url: " + json.dumps(base + "mihomo/" + name + ".yaml"),
                          "    path: ./ruleset/" + name + ".yaml", "    interval: 86400", "    proxy: PROXY"])
        lines.append("rules:")
        for name, policy in active:
            rule = "RULE-SET," + name + "," + policy
            if name in sets and config["sets"][name]["kind"] == "ip":
                rule += ",no-resolve"
            lines.append("  - " + json.dumps(rule))
        lines.append("  - " + json.dumps("MATCH," + config["default_policy"]))
        write(output / "mihomo" / ("rules" + suffix + ".yaml"), "\n".join(lines) + "\n")
    return all_sets


def build(root, output, input_dir=None, commit=None, previous=None):
    if (root / "custom/lan-com.list").exists():
        raise ValueError("Private LAN file must not exist in the public source tree")
    config = json.loads((root / "sources.json").read_text())
    upstream = config["upstream"]
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", upstream["repository"]):
        raise ValueError("Invalid upstream repository")
    if input_dir is None and commit is None:
        url = "https://api.github.com/repos/%s/git/ref/heads/%s" % (upstream["repository"], upstream["branch"])
        commit = json.loads(fetch(url, os.environ.get("GITHUB_TOKEN")))["object"]["sha"]
    if not commit or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("An immutable 40-character upstream commit is required")
    sets, raw_hashes = {}, {}
    excludes = json.loads((root / "custom/exclude.json").read_text())
    if set(excludes) - set(config["sets"]):
        raise ValueError("Unknown exclusion category")
    for name, source in config["sets"].items():
        rules = set()
        for filename in [source["file"], *source.get("additional_files", [])]:
            if not re.fullmatch(r"[a-z]+\.txt", filename):
                raise ValueError("Invalid source filename")
            raw = (input_dir / filename).read_bytes() if input_dir else fetch(
                "https://raw.githubusercontent.com/%s/%s/%s" % (upstream["repository"], commit, filename))
            raw_hashes[filename] = hashlib.sha256(raw).hexdigest()
            rules.update(parse_upstream(raw.decode("utf-8-sig"), source["kind"]))
        if len(rules) < source["minimum"]:
            raise ValueError("Source below minimum count: " + name)
        removals = {validate_rule(line) for line in excludes.get(name, [])}
        missing = removals - rules
        if missing:
            raise ValueError("Exclusion no longer matches upstream %s: %s" % (name, sorted(missing)))
        sets[name] = rules - removals
        if not sets[name]:
            raise ValueError("Exclusions emptied source: " + name)
    order = custom_order(config)
    names = [name for name, _ in order]
    if len(names) != len(set(names)):
        raise ValueError("Duplicate custom rule set name")
    if len({custom_output_name(name) for name in names}) != len(names):
        raise ValueError("Duplicate custom output name")
    for name, policy in order:
        if not re.fullmatch(r"[a-z][a-z0-9-]*", name) or custom_output_name(name) in sets or name == "allow":
            raise ValueError("Invalid custom rule set name: " + name)
        if policy not in ("DIRECT", "PROXY", "REJECT"):
            raise ValueError("Invalid custom policy: " + policy)
    custom = {name: custom_rules(root / "custom" / (name + ".list")) for name in names}
    for index, (left, left_policy) in enumerate(order):
        for right, right_policy in order[index + 1:]:
            if left_policy != right_policy and custom[left] & custom[right]:
                raise ValueError("Conflicting custom rules in %s and %s" % (left, right))
    allow = custom_rules(root / "custom/allow.list")
    # A narrower exception cannot override a broader block without a special
    # client-dependent sub-rule. Require removal of the blocking parent instead.
    for rule in sorted(allow, key=lambda r: (len(r[1].split(".")), r[0] != "DOMAIN-SUFFIX", r[1])):
        if rule[0] not in ("DOMAIN", "DOMAIN-SUFFIX"):
            raise ValueError("Advertising allow rules must be domain-based")
        broader = {block for block in sets["reject"] if block != rule and matches(block, domain=rule[1])}
        if broader:
            raise ValueError("Advertising exception is covered by a broader block; use exclude.json: " + str(sorted(broader)))
        sets["reject"] = {block for block in sets["reject"]
                          if not (block == rule or (rule[0] == "DOMAIN-SUFFIX" and matches(rule, domain=block[1])))}
    # Dedicated Apple routing owns exact duplicate entries formerly in the
    # aggregate sets; broad parent rules remain behind APPLE in rule order.
    for name in ("direct", "proxy"):
        sets[name] -= sets.get("apple", set())
    counts = {name: len(rules) for name, rules in sets.items()}
    check_counts(counts, previous, config["count_change_limits"])
    cases = json.loads((root / "tests/cases.json").read_text())
    verify_cases(sets, custom, cases, False, config["default_policy"], config)
    verify_cases(sets, custom, cases, True, config["default_policy"], config)
    render(output, sets, custom, config)
    write(output / "LICENSE", (root / "LICENSE").read_text())
    write(output / "NOTICE.md", (root / "NOTICE.md").read_text())
    write(output / "README.md", "# Generated proxy rules\n\nUsage and source code: https://github.com/" + config["publish_repository"] + "\n\nDefault fragments do not enable community advertising blocks. `rules-ads` fragments do.\n")
    hashes = {str(path.relative_to(output)): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in sorted(output.rglob("*")) if path.is_file() and path.name not in ("manifest.json", "checksums.sha256")}
    digest = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    manifest = {"schema_version": 1, "content_digest": digest, "upstream": dict(upstream, commit=commit),
                "input_sha256": raw_hashes, "counts": counts, "custom_counts": {k: len(v) for k, v in custom.items()},
                "ip_families": {k: sorted({ipaddress.ip_network(r[1]).version for r in v})
                                for k, v in sets.items() if config["sets"][k]["kind"] == "ip"},
                "advertising_enabled_by_default": False, "sha256": hashes}
    write(output / "manifest.json", json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    hashes["manifest.json"] = hashlib.sha256((output / "manifest.json").read_bytes()).hexdigest()
    write(output / "checksums.sha256", "".join(value + "  " + name + "\n" for name, value in sorted(hashes.items())))
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    parser.add_argument("--input-dir", type=Path)
    parser.add_argument("--upstream-commit")
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--previous-url")
    args = parser.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        parser.error("Output must be empty; build into a fresh staging directory")
    previous = json.loads(args.previous.read_text()) if args.previous else None
    if args.previous_url:
        raw = fetch(args.previous_url, allow_missing=True)
        previous = json.loads(raw) if raw else None
    manifest = build(ROOT, args.output, args.input_dir, args.upstream_commit, previous)
    print(json.dumps({"upstream_commit": manifest["upstream"]["commit"], "counts": manifest["counts"],
                      "ip_families": manifest["ip_families"], "content_digest": manifest["content_digest"]}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, urllib.error.URLError) as error:
        print("Build failed: " + str(error), file=sys.stderr)
        sys.exit(1)
