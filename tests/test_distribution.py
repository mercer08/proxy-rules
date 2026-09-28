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


class DistributionTests(unittest.TestCase):
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
            node = {"name": "DMIT-Native", "server": "203.0.113.1"}
            converted = {"proxies": [node],
                         "Surge": 'DMIT-Native=vmess,203.0.113.1,443,ws-headers="Host:"203.0.113.1"",vmess-aead=true,tls=true',
                         "URI": "vmess://synthetic"}
            config = {"templates_dir": str(ROOT / "deployment/templates"), "server": "203.0.113.1",
                      "public_url": "https://203.0.113.1", "repository": "mercer08/proxy-rules"}
            rendered = d.render_profiles(config, {}, converted, "a" * 48, root, "b" * 64)
            self.assertIn("ws-headers=Host:203.0.113.1,vmess-aead=true", rendered["surge.conf"])
            self.assertNotIn('Host:"', rendered["surge.conf"])
            dns_line = next(line for line in rendered["mihomo.yaml"].splitlines() if line.startswith('"dns":'))
            dns = json.loads(dns_line.split(": ", 1)[1])
            self.assertEqual(list(dns["nameserver-policy"]), ["rule-set:proxy", "rule-set:direct"])
            self.assertTrue(dns["nameserver-policy"]["rule-set:proxy"][0].endswith("#PROXY"))

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
            providers = "rule-providers:\n" + "".join("  " + name + ":\n    type: http\n    behavior: classical\n" for name in names)
            rules = "rules:\n" + "".join('  - "RULE-SET,' + name + ',' +
                ("DIRECT" if name in ("private", "lan-com") else "PROXY") + '"\n' for name in names)
            (root / "mihomo/rules.yaml").write_text(providers + rules + '  - "MATCH,PROXY"\n')
            converted = {"proxies": [{"name": "DMIT-Native"}], "Surge": "DMIT-Native=vmess,203.0.113.1,443,tls=true", "URI": "vmess://synthetic"}
            config = {"templates_dir": str(ROOT / "deployment/templates"), "server": "203.0.113.1",
                      "public_url": "https://203.0.113.1", "repository": "mercer08/proxy-rules"}
            for enabled in (False, True):
                rendered = d.render_profiles(config, {"business_rules": enabled}, converted, "a" * 48, root, "b" * 64)
                for filename in ("surge.conf", "mihomo.yaml", "shadowrocket.conf"):
                    for name in d.BUSINESS_RULE_SETS:
                        self.assertEqual(name in rendered[filename], enabled, filename + ": " + name)
                    self.assertIn("private", rendered[filename])
                    self.assertIn("PROXY", rendered[filename])
                dns = json.loads(next(line.split(": ", 1)[1] for line in rendered["mihomo.yaml"].splitlines() if line.startswith('"dns":')))
                self.assertEqual("+.internal.business.test" in dns["fake-ip-filter"], enabled)
                self.assertIn("+.localnet.test", dns["fake-ip-filter"])
                self.assertIn("/profiles/" + "a" * 48 + "/shadowrocket.conf", rendered["shadowrocket.conf"])
            shared = d.render_shadowrocket(config, root, "b" * 64, "https://203.0.113.1/proxy-config/shadowrocket.conf")
            self.assertTrue(all(name not in shared for name in d.BUSINESS_RULE_SETS))


if __name__ == "__main__":
    unittest.main()
