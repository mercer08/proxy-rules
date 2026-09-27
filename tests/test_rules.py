import hashlib
import importlib.util
import ipaddress
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("rules_build", ROOT / "scripts/build.py")
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)


class RuleTests(unittest.TestCase):
    def test_exact_and_suffix_are_distinct(self):
        rules = b.parse_upstream("payload:\n - 'exact.com'\n - '+.suffix.com'\n", "domain")
        self.assertFalse(b.matches(("DOMAIN", "exact.com"), "sub.exact.com"))
        self.assertTrue(b.matches(("DOMAIN-SUFFIX", "suffix.com"), "suffix.com"))
        self.assertTrue(b.matches(("DOMAIN-SUFFIX", "suffix.com"), "sub.suffix.com"))
        self.assertFalse(b.matches(("DOMAIN-SUFFIX", "suffix.com"), "evilsuffix.com"))
        self.assertEqual(len(rules), 2)

    def test_ip_families_and_no_resolve(self):
        rules = b.parse_upstream("payload:\n - '10.0.0.1/8'\n - 'fc00::/7'\n", "ip")
        self.assertIn(("IP-CIDR", "10.0.0.0/8", "no-resolve"), rules)
        self.assertIn(("IP-CIDR6", "fc00::/7", "no-resolve"), rules)
        self.assertFalse(b.matches(("IP-CIDR", "10.0.0.0/8", "no-resolve"), ip="fd00::1"))
        self.assertEqual(b.serialize_rule(("IP-CIDR6", "fc00::/7", "no-resolve"), "DIRECT"),
                         "IP-CIDR6,fc00::/7,DIRECT,no-resolve")

    def test_malformed_or_unsupported_sources_fail(self):
        for text in ("<html>error</html>", "payload:\n", "payload:\n - '*.wildcard.com'\n", "payload:\n - '!negated.com'\n"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                b.parse_upstream(text, "domain")

    def test_custom_cannot_smuggle_policy_or_unknown_syntax(self):
        for line in ("DOMAIN,example.com,DIRECT", "IP-CIDR,10.0.0.0/8,PROXY", "URL-REGEX,.*", "IP-CIDR6,10.0.0.0/8"):
            with self.subTest(line=line), self.assertRaises(ValueError):
                b.validate_rule(line)

    def test_abnormal_source_changes_fail(self):
        limits = {"minimum_ratio": 0.5, "maximum_ratio": 2}
        for count in (49, 201):
            with self.assertRaises(ValueError):
                b.check_counts({"direct": count}, {"counts": {"direct": 100}}, limits)

    def fixture(self, root):
        config = json.loads((ROOT / "sources.json").read_text())
        for value in config["sets"].values():
            value["minimum"] = 1
        (root / "sources.json").write_text(json.dumps(config))
        (root / "custom").mkdir()
        (root / "tests").mkdir()
        (root / "inputs").mkdir()
        for name in ("direct", "proxy", "reject", "allow"):
            (root / "custom" / (name + ".list")).write_text("")
        (root / "custom/exclude.json").write_text("{}")
        (root / "LICENSE").write_text("fixture license")
        (root / "NOTICE.md").write_text("fixture notice")
        inputs = {"private": ["+.local"], "direct": ["+.cn.example", "exact.example"],
                  "proxy": ["+.foreign.example"], "reject": ["+.ads.example"],
                  "lan": ["10.0.0.0/8", "fc00::/7"], "cn": ["1.0.1.0/24"],
                  "telegram": ["149.154.160.0/20"]}
        for name, payload in inputs.items():
            (root / "inputs" / config["sets"][name]["file"]).write_text(b.yaml_payload(payload))
        cases = [{"domain": "router.local", "expected": "DIRECT"},
                 {"ip": "10.0.0.1", "expected": "DIRECT"},
                 {"domain": "foreign.example", "expected": "PROXY"},
                 {"domain": "cn.example", "expected": "DIRECT"},
                 {"domain": "unknown.example", "expected": "PROXY"}]
        (root / "tests/cases.json").write_text(json.dumps(cases))
        return config

    def test_complete_build_client_outputs_and_checksums(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            (root / "custom/proxy.list").write_text("DOMAIN,api.cn.example\n")
            manifest = b.build(root, root / "out", root / "inputs", "a" * 40)
            domainset = (root / "out/surge/direct.domainset").read_text().splitlines()
            self.assertEqual(domainset, ["exact.example", ".cn.example"])
            sr = (root / "out/shadowrocket/direct.list").read_text()
            self.assertIn("DOMAIN,exact.example", sr)
            self.assertIn("DOMAIN-SUFFIX,cn.example", sr)
            mi = (root / "out/mihomo/direct.yaml").read_text()
            self.assertIn('"exact.example"', mi)
            self.assertIn('"+.cn.example"', mi)
            for client, filename in (("surge", "rules.conf"), ("shadowrocket", "rules.conf"), ("mihomo", "rules.yaml")):
                text = (root / "out" / client / filename).read_text()
                self.assertNotIn("/reject.", text)
                self.assertLess(text.index("custom-proxy"), text.index("/direct."))
            for line in (root / "out/checksums.sha256").read_text().splitlines():
                digest, name = line.split("  ", 1)
                self.assertEqual(digest, hashlib.sha256((root / "out" / name).read_bytes()).hexdigest())
            self.assertEqual(manifest["ip_families"]["lan"], [4, 6])

    def test_custom_overrides_and_lan_priority(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            (root / "custom/proxy.list").write_text("DOMAIN-SUFFIX,cn.example\nDOMAIN-SUFFIX,local\n")
            (root / "custom/direct.list").write_text("DOMAIN-SUFFIX,foreign.example\n")
            cases = [{"domain": "cn.example", "expected": "PROXY"},
                     {"domain": "foreign.example", "expected": "DIRECT"},
                     {"domain": "router.local", "expected": "DIRECT"}]
            (root / "tests/cases.json").write_text(json.dumps(cases))
            b.build(root, root / "out", root / "inputs", "a" * 40)

    def test_custom_conflict_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            for name in ("direct", "proxy"):
                (root / "custom" / (name + ".list")).write_text("DOMAIN,conflict.com\n")
            with self.assertRaisesRegex(ValueError, "Conflicting"):
                b.build(root, root / "out", root / "inputs", "a" * 40)

    def test_exclusion_and_ad_allow(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            (root / "inputs/reject.txt").write_text(b.yaml_payload(["+.ads.example", "+.other.example"]))
            (root / "custom/allow.list").write_text("DOMAIN-SUFFIX,ads.example\n")
            b.build(root, root / "out", root / "inputs", "a" * 40)
            self.assertNotIn("ads.example", (root / "out/shadowrocket/reject.list").read_text())
            self.assertIn("other.example", (root / "out/shadowrocket/reject.list").read_text())

    def test_narrow_ad_exception_under_parent_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            (root / "custom/allow.list").write_text("DOMAIN,api.ads.example\n")
            with self.assertRaisesRegex(ValueError, "broader block"):
                b.build(root, root / "out", root / "inputs", "a" * 40)

    def test_suffix_ad_allow_removes_descendant_blocks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            (root / "inputs/reject.txt").write_text(b.yaml_payload(["api.ads.example", "+.sub.ads.example", "+.other.example"]))
            (root / "custom/allow.list").write_text("DOMAIN-SUFFIX,ads.example\n")
            b.build(root, root / "out", root / "inputs", "a" * 40)
            text = (root / "out/shadowrocket/reject.list").read_text()
            self.assertNotIn("ads.example", text)
            self.assertIn("other.example", text)

    def test_stale_exclusion_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            (root / "custom/exclude.json").write_text(json.dumps({"direct": ["DOMAIN,no-longer-listed.example"]}))
            with self.assertRaisesRegex(ValueError, "no longer matches"):
                b.build(root, root / "out", root / "inputs", "a" * 40)


if __name__ == "__main__":
    unittest.main()
