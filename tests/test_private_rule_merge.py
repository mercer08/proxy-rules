import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('private_distribution', ROOT / 'deployment/distribute.py')
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)
import migrate_router_rules as migration


class PrivateMergeTests(unittest.TestCase):
    def test_full_configuration_edit_is_rejected_before_writing(self):
        import console
        app = console.Console.__new__(console.Console)
        with self.assertRaises(console.ConsoleError) as caught:
            app.edit('a' * 24, 'mihomo.yaml', 'edited', 'etag')
        self.assertEqual(caught.exception.status, 403)

    def test_host_and_cidr_validation(self):
        rules, hosts = d.private_lan_data('HOST,nas.home.arpa,192.168.1.2\nIP-CIDR,203.0.113.4/32\nDOMAIN-SUFFIX,internal.test\n')
        self.assertEqual(hosts, {'nas.home.arpa': '192.168.1.2'})
        self.assertEqual(rules, ['DOMAIN,nas.home.arpa', 'IP-CIDR,203.0.113.4/32,no-resolve', 'DOMAIN-SUFFIX,internal.test'])
        self.assertEqual(d.private_direct(rules[1]), 'IP-CIDR,203.0.113.4/32,DIRECT,no-resolve')
        self.assertEqual(d.personal.domain_patterns(rules), ['nas.home.arpa', '+.internal.test'])
        for invalid in ('HOST,nas,invalid', 'HOST,nas,192.0.2.1\nHOST,nas,192.0.2.2', 'IP-CIDR,192.0.2.1/24', 'IP-CIDR,192.0.2.1/32,PROXY'):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                d.private_lan_data(invalid)

    def test_current_versions_survive_private_merge_and_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'lan.list'
            path.write_text('HOST,nas.home.arpa,192.168.1.2\nIP-CIDR,203.0.113.4/32\n')
            config = {'private_lan_file': str(path)}
            source = {'mihomo.yaml': 'dns:\n  enable: true\nrule-providers:\n  ai:\n    url: "https://example.test/current/ai.yaml"\nrules:\n  - "MATCH,FINAL"\n', 'surge.conf': '[Rule]\nFINAL,FINAL\n', 'node.txt': 'unchanged'}
            self.assertEqual(d.merge_private_hosts(source, config, {'business_rules': False}), source)
            merged = d.merge_private_hosts(source, config, {'business_rules': True})
            self.assertIn('use-hosts: true', merged['mihomo.yaml'])
            self.assertIn('nas.home.arpa', merged['mihomo.yaml'])
            self.assertIn('https://example.test/current/ai.yaml', merged['mihomo.yaml'])
            self.assertIn('[Host]\nnas.home.arpa = 192.168.1.2', merged['surge.conf'])
            self.assertEqual(merged['node.txt'], 'unchanged')
            fragment = 'rule-providers:\nrules:\n  - "RULE-SET,proxy,PROXY"\n'
            injected = d.inject_private_lan(fragment, 'mihomo', config)
            self.assertIn('IP-CIDR,203.0.113.4/32,no-resolve', injected)
            self.assertNotIn('HOST,', injected)

    def test_private_hosts_merge_with_existing_wireguard_hosts(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'lan.list'
            path.write_text('HOST,nas.home.arpa,192.168.1.2\n')
            config = {'private_lan_file': str(path)}
            source = {'surge.conf': '[Host]\nrouter.home.arpa = 192.168.1.1\n\n[Rule]\nFINAL,PROXY\n'}
            merged = d.merge_private_hosts(source, config, {'business_rules': True})['surge.conf']
            self.assertEqual(merged.count('[Host]'), 1)
            self.assertIn('router.home.arpa = 192.168.1.1', merged)
            self.assertLess(merged.index('nas.home.arpa = 192.168.1.2'), merged.index('[Rule]'))
            source['surge.conf'] = '[Host]\nnas.home.arpa = 192.168.1.3\n'
            with self.assertRaises(ValueError):
                d.merge_private_hosts(source, config, {'business_rules': True})

    def test_extract_migrates_only_local_direct_exceptions(self):
        text = 'hosts:\n  "nas.home.arpa": "192.168.1.2"\nproxies:\n  - name: unchanged\nrules:\n  - "DOMAIN-SUFFIX,example.test,DIRECT"\n  - "IP-CIDR,203.0.113.4/32,DIRECT,no-resolve"\n  - "RULE-SET,ai,AI"\n  - "MATCH,FINAL"\n'
        self.assertEqual(migration.extract_private(text), ['HOST,nas.home.arpa,192.168.1.2', 'DOMAIN-SUFFIX,example.test', 'IP-CIDR,203.0.113.4/32,no-resolve'])

    def test_failed_generation_restores_private_input_and_override(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            identifier = 'a' * 24
            override = state / 'profile-overrides' / identifier / 'mihomo.yaml'
            override.parent.mkdir(parents=True)
            original = 'rules:\n  - "DOMAIN,internal.test,DIRECT"\n  - "MATCH,FINAL"\n'
            override.write_text(original)
            private = state / 'lan.list'
            private.write_text('DOMAIN,old.test\n')
            (state / 'profiles.json').write_text(json.dumps({'accounts': [{'business_rules': True, 'files': {'mihomo.yaml': str(state / identifier / 'mihomo.yaml')}}]}))
            config = {'state_dir': tmp, 'private_lan_file': str(private)}
            with patch.object(migration.d, 'generate', side_effect=[RuntimeError('failed'), None]), self.assertRaises(RuntimeError):
                migration.migrate(config, identifier, True)
            self.assertEqual(override.read_text(), original)
            self.assertEqual(private.read_text(), 'DOMAIN,old.test\n')
            self.assertEqual(len(list((state / 'private-rule-migrations').glob('*/mihomo.yaml'))), 1)


if __name__ == '__main__':
    unittest.main()
