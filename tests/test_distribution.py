import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import sys
import tarfile
import tempfile
import unittest
import yaml
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("distribution", ROOT / "deployment/distribute.py")
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)
sys.path.insert(0, str(ROOT / "deployment"))
import install as installer


def archive(files):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as output:
        for name, data in files.items():
            member = tarfile.TarInfo(name)
            member.size = len(data)
            output.addfile(member, io.BytesIO(data))
    return buffer.getvalue()


def vmess_node(name="DMIT-Native", uuid="synthetic-secret"):
    return {"name": name, "type": "vmess", "server": "203.0.113.1", "port": 443,
            "uuid": uuid, "alterId": 0, "cipher": "aes-128-gcm", "network": "ws",
            "tls": True, "skip-cert-verify": False, "udp": True,
            "ws-opts": {"path": "/test-ws", "headers": {"Host": "203.0.113.1"}}}


class DistributionTests(unittest.TestCase):
    def test_shadowrocket_contains_complete_account_node(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "shadowrocket").mkdir()
            (root / "shadowrocket/rules.conf").write_text("[Rule]\nFINAL,PROXY\n")
            node = {"name": "dmit-lax", "type": "vmess", "server": "203.0.113.1", "port": 443,
                    "uuid": "00000000-0000-4000-8000-000000000001", "alterId": 0,
                    "cipher": "aes-128-gcm", "network": "ws", "tls": True,
                    "skip-cert-verify": False, "udp": True,
                    "ws-opts": {"path": "/test-ws", "headers": {"Host": "203.0.113.1"}}}
            config = {"templates_dir": str(ROOT / "deployment/templates"),
                      "repository": "mercer08/proxy-rules", "public_url": "https://203.0.113.1"}
            profile = d.render_shadowrocket(config, root, "b" * 64, "", proxies=[node])
            self.assertIn("[Proxy]\n", profile)
            line = next(line for line in profile.splitlines() if line.startswith("dmit-lax ="))
            parts = [part.strip() for part in line.split("=", 1)[1].split(",")]
            self.assertEqual(parts[:3], ["vmess", node["server"], str(node["port"])])
            options = dict(part.split("=", 1) for part in parts[3:])
            self.assertEqual(options["password"], node["uuid"])
            self.assertEqual(options["method"], node["cipher"])
            self.assertEqual(options["alterId"], "0")
            self.assertEqual(options["obfs"], "websocket")
            self.assertEqual(options["obfs-host"], node["ws-opts"]["headers"]["Host"])
            self.assertEqual(options["obfs-uri"], node["ws-opts"]["path"])
            self.assertEqual(options["peer"], node["server"])
            self.assertEqual(options["tls"], "true")
            self.assertEqual(options["skip-cert-verify"], "false")
            self.assertEqual(options["udp"], "1")
            self.assertIn("PROXY = select,dmit-lax", profile)
            self.assertNotIn("policy-regex-filter", profile)

    def bundle(self):
        files = {"surge/rules.conf": b"[Rule]\nFINAL,PROXY\n",
                 "mihomo/rules.yaml": b"rules:\n - MATCH,PROXY\n",
                 "shadowrocket/rules.conf": b"[Rule]\nFINAL,PROXY\n"}
        hashes = {name: hashlib.sha256(content).hexdigest() for name, content in files.items()}
        manifest = {"schema_version": 1, "sha256": hashes,
                    "content_digest": hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()}
        files["manifest.json"] = json.dumps(manifest).encode()
        hashes = {name: hashlib.sha256(content).hexdigest() for name, content in files.items()}
        files["checksums.sha256"] = "".join(value + "  " + name + "\n" for name, value in hashes.items()).encode()
        return files

    def test_valid_snapshot_and_tampered_files(self):
        files = self.bundle()
        for tamper in (False, True):
            altered = dict(files)
            if tamper:
                altered["surge/rules.conf"] += b"DOMAIN-SUFFIX,example.com,DIRECT\n"
            bundle = archive(altered)
            with tempfile.TemporaryDirectory() as directory:
                if tamper:
                    with self.assertRaises(ValueError):
                        d.unpack_verified(bundle, hashlib.sha256(bundle).hexdigest(), Path(directory))
                else:
                    self.assertEqual(d.unpack_verified(bundle, hashlib.sha256(bundle).hexdigest(), Path(directory))["schema_version"], 1)

    def test_traversal_and_unchecked_files_cannot_be_published(self):
        for name in ("../escape", "/absolute", "extra-secret.txt"):
            files = self.bundle()
            files[name] = b"bad"
            bundle = archive(files)
            with tempfile.TemporaryDirectory() as directory, self.assertRaises(ValueError):
                d.unpack_verified(bundle, hashlib.sha256(bundle).hexdigest(), Path(directory))

    def test_symlinks_are_rejected(self):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as output:
            member = tarfile.TarInfo("linked")
            member.type = tarfile.SYMTYPE
            member.linkname = "/etc/passwd"
            output.addfile(member)
        bundle = buffer.getvalue()
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(ValueError):
            d.unpack_verified(bundle, hashlib.sha256(bundle).hexdigest(), Path(directory))

    def test_canonical_disabled_accounts_and_removed_memberships_are_omitted(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "x-ui.db"
            connection = sqlite3.connect(database)
            connection.executescript("""
                CREATE TABLE inbounds (id INTEGER,tag TEXT,enable INTEGER,protocol TEXT,settings TEXT,stream_settings TEXT);
                CREATE TABLE clients (id INTEGER,sub_id TEXT,uuid TEXT,email TEXT,enable INTEGER,expiry_time INTEGER);
                CREATE TABLE client_inbounds (client_id INTEGER,inbound_id INTEGER);
            """)
            clients = [{"id": "old-uuid", "subId": name, "email": name, "enable": True} for name in ["active", "disabled", "expired", "removed"]]
            connection.execute("INSERT INTO inbounds VALUES (1,?,?,?,?,?)", ("dmit-direct", 1, "vmess", json.dumps({"clients": clients}), json.dumps({"network": "ws", "wsSettings": {"path": "/ws"}})))
            for index, name in enumerate(["active", "disabled", "expired", "removed"], 1):
                connection.execute("INSERT INTO clients VALUES (?,?,?,?,?,?)", (index, name, "new-uuid", name, name != "disabled", 1 if name == "expired" else 0))
                if name != "removed":
                    connection.execute("INSERT INTO client_inbounds VALUES (?,1)", (index,))
            connection.commit()
            connection.close()
            config = {"database": str(database), "server": "203.0.113.1", "port": 443,
                      "account_labels": {"active": "friendly-name"}, "business_rule_accounts": ["active"],
                      "inbounds": {"dmit-direct": {"name": "DMIT-Native", "udp": False}}}
            accounts = d.load_accounts(config, now=100)
            self.assertEqual(list(accounts), ["active"])
            self.assertEqual(accounts["active"]["label"], "friendly-name")
            self.assertTrue(accounts["active"]["business_rules"])
            node = accounts["active"]["nodes"][0]
            self.assertEqual(node["uuid"], "new-uuid")
            self.assertEqual(node["server"], "203.0.113.1")
            self.assertEqual(node["port"], 443)
            self.assertTrue(node["tls"])
            self.assertFalse(node["skip-cert-verify"])

    def test_rule_urls_are_pinned_to_the_server_mirror(self):
        config = {"repository": "mercer08/proxy-rules", "public_url": "https://203.0.113.1"}
        source = "RULE-SET,https://raw.githubusercontent.com/mercer08/proxy-rules/release/surge/wan-com.list,PROXY"
        output = d.rewrite_rules(source, config, "a" * 64)
        self.assertNotIn("githubusercontent", output)
        self.assertIn("/proxy-rules/" + "a" * 64 + "/surge/wan-com.list,PROXY", output)

    def test_cdn_urls_require_a_matching_immutable_tag(self):
        config = {"repository": "mercer08/proxy-rules", "rules_delivery": "jsdelivr",
                  "_rules_tag": "rules-20260928T010000Z-" + "a" * 10}
        source = "DOMAIN-SET,https://raw.githubusercontent.com/mercer08/proxy-rules/release/surge/private.domainset,DIRECT"
        self.assertIn("cdn.jsdelivr.net/gh/mercer08/proxy-rules@" + config["_rules_tag"], d.rewrite_rules(source, config, "a" * 64))
        for tag in ("release", "main", "rules-20260928T010000Z-" + "b" * 10):
            with self.assertRaises(ValueError):
                d.rewrite_rules(source, dict(config, _rules_tag=tag), "a" * 64)

    def test_private_generation_and_single_account_ssh_export(self):
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary)
            digest = "b" * 64
            rules = state / "rules/releases" / digest
            for client in ("surge", "shadowrocket", "mihomo"):
                (rules / client).mkdir(parents=True)
                (rules / client / ("rules.yaml" if client == "mihomo" else "rules.conf")).write_text(
                    'rule-providers:\nrules:\n  - "MATCH,PROXY"\n' if client == "mihomo" else "[Rule]\nFINAL,PROXY\n")
            (state / "rules.json").write_text(json.dumps({"digest": digest, "tag": "rules-now-" + digest[:10]}))
            config = {"state_dir": str(state), "templates_dir": str(ROOT / "deployment/templates"),
                      "repository": "mercer08/proxy-rules", "rules_delivery": "jsdelivr",
                      "public_url": "https://203.0.113.1", "server": "203.0.113.1"}
            accounts = {name: {"label": name, "nodes": [{"name": "DMIT-Native"}], "business_rules": False} for name in ("owner", "friend")}
            converted = {"proxies": [vmess_node()],
                         "Surge": "DMIT-Native=vmess,203.0.113.1,443,password=synthetic-secret", "URI": "vmess://synthetic"}
            with patch.object(d, "load_accounts", return_value=accounts), patch.object(d, "substore", return_value=converted), patch.object(d, "verify_cdn", return_value=18):
                d.generate(config)
            records = json.loads((state / "profiles.json").read_text())["accounts"]
            for record in records:
                self.assertNotIn("links", record)
                for path in record["files"].values():
                    file = Path(path)
                    self.assertEqual(file.stat().st_mode & 0o777, 0o600)
                    self.assertEqual(file.parent.stat().st_mode & 0o777, 0o700)
                    self.assertNotIn("/profiles/", file.read_text())
            self.assertFalse((state / "tokens.json").exists())
            friend_id = hashlib.sha256(b"friend").hexdigest()[:24]
            override = state / "profile-overrides" / friend_id / "surge.conf"
            d.atomic_write(override, "[Rule]\nFINAL,PROXY\n# persistent personal edit\n")
            with patch.object(d, "load_accounts", return_value=accounts), patch.object(d, "substore", return_value=converted):
                d.generate(config)
                d.generate(config)
            friend = next(r for r in json.loads((state / "profiles.json").read_text())["accounts"] if r["label"] == "friend")
            self.assertEqual(friend["edited"], ["surge.conf"])
            self.assertIn("persistent personal edit", Path(friend["files"]["surge.conf"]).read_text())
            output = io.BytesIO()
            d.export_profiles(config, output, "friend")
            with tarfile.open(fileobj=io.BytesIO(output.getvalue()), mode="r:gz") as exported:
                self.assertTrue(all(m.name.startswith("friend/") for m in exported.getmembers()))
                self.assertTrue(all(m.mode == 0o600 for m in exported.getmembers()))
                self.assertIn(b"synthetic-secret", exported.extractfile("friend/mihomo.yaml").read())
            with self.assertRaises(ValueError):
                d.export_profiles(config, io.BytesIO(), "missing")
            config_file = state / "config.json"
            config_file.write_text(json.dumps(config))
            cli_output = io.BytesIO()
            cli_stream = io.TextIOWrapper(cli_output, encoding="utf-8")
            with patch.object(d.sys, "argv", ["distribute.py", "export", "--config", str(config_file), "--account", "friend"]), patch.object(d.sys, "stdout", cli_stream), patch.object(d, "generate"):
                d.main()
            cli_stream.flush()
            with tarfile.open(fileobj=io.BytesIO(cli_output.getvalue()), mode="r:gz") as exported:
                self.assertEqual(len(exported.getmembers()), 7)
                self.assertTrue(all(m.name.startswith("friend/") for m in exported.getmembers()))

    def test_cdn_verification_rejects_tampering_and_never_fetches_business_rules(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw = "https://raw.githubusercontent.com/mercer08/proxy-rules/release/"
            hashes = {}
            for client in ("surge", "shadowrocket", "mihomo"):
                (root / client).mkdir()
                if client == "mihomo":
                    fragment = 'rule-providers:\n  private:\n    type: http\n    url: "' + raw + 'mihomo/private.yaml"\n  lan-com:\n    type: http\n    url: "' + raw + 'mihomo/lan-com.yaml"\nrules:\n  - "RULE-SET,private,DIRECT"\n  - "RULE-SET,lan-com,DIRECT"\n'
                    filename = "rules.yaml"
                    rulefile = "private.yaml"
                else:
                    fragment = "[Rule]\nRULE-SET," + raw + client + "/private.list,DIRECT\nRULE-SET," + raw + client + "/lan-com.list,DIRECT\nFINAL,PROXY\n"
                    filename = "rules.conf"
                    rulefile = "private.list"
                (root / client / filename).write_text(fragment)
                hashes[client + "/" + rulefile] = hashlib.sha256(b"public-rules").hexdigest()
            (root / "manifest.json").write_text(json.dumps({"sha256": hashes}))
            config = {"repository": "mercer08/proxy-rules", "rules_delivery": "jsdelivr", "_rules_tag": "rules-now-" + "a" * 10}
            with patch.object(d, "fetch", return_value=b"public-rules") as download:
                self.assertEqual(d.verify_cdn(config, root, "a" * 64), 3)
                self.assertTrue(all("lan-com" not in call.args[0] for call in download.call_args_list))
            with patch.object(d, "fetch", return_value=b"tampered"), self.assertRaises(ValueError):
                d.verify_cdn(config, root, "a" * 64)

    def test_nginx_include_is_added_to_tls_server_only_and_is_idempotent(self):
        text = '''# A comment with { }
server { listen 80; location / { return 404; } }
server {
 listen 443 ssl default_server;
 if ($host != "203.0.113.1") { return 444; }
 location ~ "^/example/[a-f0-9]{48}$" { return 404; }
}
'''
        result = installer.insert_https_include(text)
        self.assertEqual(result.count(installer.NGINX_INCLUDE), 1)
        self.assertGreater(result.index(installer.NGINX_INCLUDE), result.index("listen 443"))
        self.assertEqual(installer.insert_https_include(result), result)
        with self.assertRaises(ValueError):
            installer.insert_https_include("server { listen 80; }")

    def test_templates_keep_dns_policy_order_and_fix_surge_host_quoting(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for client in ["surge", "shadowrocket", "mihomo"]:
                (root / client).mkdir()
            for client in ["surge", "shadowrocket"]:
                (root / client / "rules.conf").write_text("[Rule]\nFINAL,PROXY\n")
            (root / "mihomo/rules.yaml").write_text('''rule-providers:
  proxy:
    type: http
    behavior: domain
  direct:
    type: http
    behavior: domain
rules:
  - "RULE-SET,proxy,PROXY"
  - "RULE-SET,direct,DIRECT"
  - "MATCH,PROXY"
''')
            node = vmess_node()
            converted = {"proxies": [node],
                         "Surge": 'DMIT-Native=vmess,203.0.113.1,443,ws-headers="Host:"203.0.113.1"",vmess-aead=true,tls=true',
                         "URI": "vmess://synthetic"}
            config = {"templates_dir": str(ROOT / "deployment/templates"), "server": "203.0.113.1",
                      "public_url": "https://203.0.113.1", "repository": "mercer08/proxy-rules"}
            rendered = d.render_profiles(config, {}, converted, "a" * 48, root, "b" * 64)
            self.assertIn("ws-headers=Host:203.0.113.1,vmess-aead=true", rendered["surge.conf"])
            self.assertNotIn('Host:"', rendered["surge.conf"])
            mihomo = yaml.safe_load(rendered["mihomo.yaml"])
            dns = mihomo["dns"]
            self.assertEqual(list(dns["nameserver-policy"]), ["rule-set:proxy", "rule-set:direct"])
            self.assertTrue(dns["nameserver-policy"]["rule-set:proxy"][0].endswith("#PROXY"))
            self.assertEqual(mihomo["rules"], ["RULE-SET,proxy,PROXY", "RULE-SET,direct,DIRECT", "MATCH,DIRECT"])
            self.assertEqual(mihomo["proxies"], [node])
            self.assertIn("block-quic = always-allow", rendered["surge.conf"])
            self.assertNotIn("block-quic=on", rendered["surge.conf"])
            self.assertIn("block-quic = always-allow", rendered["shadowrocket.conf"])
            renamed = dict(converted, proxies=[dict(node, name="dmit-lax")],
                           Surge=converted["Surge"].replace("DMIT-Native", "dmit-lax"))
            renamed_profile = d.render_profiles(config, {}, renamed, "a" * 48, root, "b" * 64)
            group = next(line for line in renamed_profile["shadowrocket.conf"].splitlines() if line.startswith("PROXY ="))
            self.assertEqual(group.split(",")[1], "dmit-lax")
            self.assertNotIn("DMIT-Native", group)
            self.assertIn("policy-select-name=dmit-lax", group)

    def test_business_rules_are_account_scoped_in_all_clients_and_dns(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            names = ["private", "lan-com", "wan-com", "proxy", "futu-broker"]
            for client in ["surge", "shadowrocket", "mihomo"]:
                (root / client).mkdir()
            origin = "https://raw.githubusercontent.com/mercer08/proxy-rules/release/"
            for client in ["surge", "shadowrocket"]:
                lines = ["[Rule]"] + ["RULE-SET," + origin + client + "/" + name + ".list," +
                    ("DIRECT" if name in ("private", "lan-com") else "PROXY") for name in names]
                (root / client / "rules.conf").write_text("\n".join(lines) + "\nFINAL,PROXY\n")
            (root / "surge/private.list").write_text("DOMAIN-SUFFIX,localnet.test\n")
            (root / "surge/lan-com.list").write_text("DOMAIN-SUFFIX,internal.business.test\n")
            for client in ("surge", "shadowrocket", "mihomo"):
                for name in d.BUSINESS_RULE_SETS:
                    rule = "DOMAIN-SUFFIX,internal.business.test" if name == "lan-com" else "IP-CIDR,203.0.113.0/24,no-resolve"
                    content = 'payload:\n  - ' + json.dumps(rule) + '\n' if client == "mihomo" else rule + '\n'
                    (root / client / (name + (".yaml" if client == "mihomo" else ".list"))).write_text(content)
            providers = "rule-providers:\n" + "".join("  " + name + ":\n    type: http\n    behavior: classical\n    url: " + json.dumps(origin + "mihomo/" + name + ".yaml") + "\n" for name in names)
            rules = "rules:\n" + "".join('  - "RULE-SET,' + name + ',' +
                ("DIRECT" if name in ("private", "lan-com") else "PROXY") + '"\n' for name in names)
            (root / "mihomo/rules.yaml").write_text(providers + rules + '  - "MATCH,PROXY"\n')
            converted = {"proxies": [vmess_node()], "Surge": "DMIT-Native=vmess,203.0.113.1,443,tls=true", "URI": "vmess://synthetic"}
            private = root / "private-rules/lan-com.list"
            d.atomic_write(private, "DOMAIN-SUFFIX,internal.business.test\n")
            config = {"templates_dir": str(ROOT / "deployment/templates"), "server": "203.0.113.1",
                      "private_lan_file": str(private), "state_dir": str(root),
                      "public_url": "https://203.0.113.1", "repository": "mercer08/proxy-rules"}
            for enabled in (False, True):
                rendered = d.render_profiles(config, {"business_rules": enabled}, converted, "a" * 48, root, "b" * 64)
                for filename in ("surge.conf", "mihomo.yaml", "shadowrocket.conf"):
                    for name in d.BUSINESS_RULE_SETS:
                        self.assertEqual(name in rendered[filename], enabled, filename + ": " + name)
                    self.assertIn("private", rendered[filename])
                    self.assertIn("PROXY", rendered[filename])
                mihomo = yaml.safe_load(rendered["mihomo.yaml"])
                dns = mihomo["dns"]
                self.assertEqual("rule-set:lan-com" in dns["fake-ip-filter"], enabled)
                self.assertEqual(dns["fake-ip-filter"], ["rule-set:private"] + (["rule-set:lan-com"] if enabled else []))
                self.assertFalse(any('REJECT' in rule for rule in mihomo["rules"]))
                self.assertNotIn("update-url", rendered["shadowrocket.conf"])
                self.assertNotIn("#!MANAGED-CONFIG", rendered["surge.conf"])
                self.assertNotIn("/profiles/", rendered["surge.conf"])
                self.assertEqual(rendered["node.txt"], "vmess://synthetic\n")
            # A clean public snapshot has no LAN provider or reference. Private
            # injection must work independently of the old public files.
            for client, filename in (("surge", "rules.conf"), ("shadowrocket", "rules.conf"), ("mihomo", "rules.yaml")):
                path = root / client / filename
                path.write_text(d.strip_private_rule_references(path.read_text(), client))
                (root / client / ("lan-com.yaml" if client == "mihomo" else "lan-com.list")).unlink()
            shared = d.render_shadowrocket(config, root, "b" * 64, "https://203.0.113.1/proxy-config/shadowrocket.conf")
            self.assertTrue(all(name not in shared for name in d.BUSINESS_RULE_SETS))
            cdn_config = dict(config, rules_delivery="jsdelivr", _rules_tag="rules-now-" + "b" * 10)
            for enabled in (False, True):
                rendered = d.render_profiles(cdn_config, {"business_rules": enabled}, converted, "a" * 48, root, "b" * 64)
                for filename in ("surge.conf", "mihomo.yaml", "shadowrocket.conf"):
                    self.assertNotIn("/proxy-rules/", rendered[filename])
                    self.assertNotIn("githubusercontent", rendered[filename])
                    self.assertIn("cdn.jsdelivr.net/gh/", rendered[filename])
                    self.assertNotIn("/lan-com.", rendered[filename])
                    for name in ("wan-com", "futu-broker"):
                        self.assertEqual("/" + name + "." in rendered[filename], enabled)
                if enabled:
                    self.assertIn("type: inline", rendered["mihomo.yaml"])
                    for filename in ("surge.conf", "shadowrocket.conf"):
                        self.assertNotIn("IP-CIDR,203.0.113.0/24,PROXY,no-resolve", rendered[filename])
                        self.assertLess(rendered[filename].index("internal.business.test"), rendered[filename].index("/proxy.list"))
                dns = yaml.safe_load(rendered["mihomo.yaml"])["dns"]
                self.assertEqual("rule-set:lan-com" in dns["nameserver-policy"], enabled)
                self.assertEqual("rule-set:lan-com" in dns["fake-ip-filter"], enabled)

    def test_stash_uses_plain_private_rules_and_final_policy_is_account_scoped(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw = "https://raw.githubusercontent.com/mercer08/proxy-rules/release/"
            for client in ("surge", "shadowrocket", "mihomo"):
                (root / client).mkdir()
            fragment = 'rule-providers:\n'
            for name in ("private", "apple", "proxy"):
                fragment += f'  {name}:\n    type: http\n    behavior: domain\n    url: "{raw}mihomo/{name}.yaml"\n    proxy: PROXY\n'
            fragment += 'rules:\n  - "RULE-SET,private,DIRECT"\n  - "RULE-SET,apple,APPLE"\n  - "RULE-SET,proxy,PROXY"\n  - "MATCH,PROXY"\n'
            (root / 'mihomo/rules.yaml').write_text(fragment)
            for client in ('surge', 'shadowrocket'):
                (root / client / 'rules.conf').write_text('[Rule]\nRULE-SET,' + raw + client + '/apple.list,APPLE\nFINAL,PROXY\n')
            private = root / 'private-rules/lan-com.list'
            d.atomic_write(private, 'DOMAIN,host.internal.test\nDOMAIN-SUFFIX,corp.internal.test\n')
            config = {'state_dir': str(root), 'private_lan_file': str(private),
                      'templates_dir': str(ROOT / 'deployment/templates'), 'server': '203.0.113.1',
                      'public_url': 'https://203.0.113.1', 'repository': 'mercer08/proxy-rules',
                      'rules_delivery': 'jsdelivr', '_rules_tag': 'rules-now-' + 'b' * 10}
            converted = {'proxies': [vmess_node()], 'Surge': 'DMIT-Native=vmess,203.0.113.1,443,tls=true', 'URI': 'vmess://synthetic'}
            for owner in (False, True):
                rendered = d.render_profiles(config, {'business_rules': owner}, converted, '', root, 'b' * 64)
                policy = 'PROXY' if owner else 'DIRECT'
                for file in ('surge.conf', 'shadowrocket.conf'):
                    self.assertTrue(rendered[file].endswith('FINAL,' + policy + '\n'))
                    self.assertIn('APPLE = select', rendered[file])
                for file in ('mihomo.yaml', 'stash.yaml'):
                    profile = yaml.safe_load(rendered[file])
                    self.assertEqual(profile['rules'][-1], 'MATCH,' + policy)
                    self.assertEqual(profile['proxy-groups'][1], {'name':'APPLE','type':'select','proxies':['DIRECT','PROXY']})
                    self.assertLess(profile['rules'].index('RULE-SET,apple,APPLE'), profile['rules'].index('RULE-SET,proxy,PROXY'))
                stash = yaml.safe_load(rendered['stash.yaml'])
                self.assertNotIn('lan-com', stash['rule-providers'])
                self.assertTrue(all(p['type'] == 'http' and 'payload' not in p for p in stash['rule-providers'].values()))
                self.assertFalse(any('rule-set:' in p for p in stash['dns']['nameserver-policy']))
                self.assertFalse(any('rule-set:' in p for p in stash['dns']['fake-ip-filter']))
                self.assertEqual('DOMAIN,host.internal.test,DIRECT' in stash['rules'], owner)
                self.assertEqual('host.internal.test' in stash['dns']['nameserver-policy'], owner)
                if owner:
                    self.assertEqual(stash['dns']['nameserver-policy']['+.corp.internal.test'], 'system')
                    self.assertLess(stash['rules'].index('DOMAIN,host.internal.test,DIRECT'), stash['rules'].index('RULE-SET,apple,APPLE'))


if __name__ == "__main__":
    unittest.main()
