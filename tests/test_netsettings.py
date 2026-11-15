import json
import sqlite3
from pathlib import Path
import sys
import tempfile
import unittest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'deployment'))
import distribute as d
import netsettings as n


class NetworkSettingsTests(unittest.TestCase):
    def test_general_update_does_not_remove_wireguard_dns(self):
        source = '[General]\ndns-server = system\n[WireGuard home-wg]\ndns-server = 10.0.0.1\n[Rule]\nFINAL,PROXY\n'
        settings = {'schema_version': 1, 'surge': {'general': {'dns-server': '1.1.1.1'}}}
        result = n.render({'surge.conf': source}, settings, d.yaml_block)['surge.conf']
        self.assertIn('[General]\ndns-server = 1.1.1.1\n', result)
        self.assertIn('[WireGuard home-wg]\ndns-server = 10.0.0.1\n', result)
        self.assertEqual(result, n.render({'surge.conf': result}, settings, d.yaml_block)['surge.conf'])
        with self.assertRaisesRegex(ValueError, 'General section'):
            n.render({'surge.conf': '[Rule]\nFINAL,PROXY\n'}, settings, d.yaml_block)

    def test_prepend_targets_top_level_rules_not_sub_rules(self):
        source = 'dns:\n  enable: true\nsub-rules:\n  child:\n    - MATCH,DIRECT\nrules:\n  - MATCH,PROXY\n'
        settings = {'schema_version': 1, 'mihomo': {'rules_prepend': ['DOMAIN,example.com,DIRECT']}}
        parsed = yaml.safe_load(n.render({'mihomo.yaml': source}, settings, d.yaml_block)['mihomo.yaml'])
        self.assertEqual(parsed['sub-rules'], {'child': ['MATCH,DIRECT']})
        self.assertEqual(parsed['rules'], ['DOMAIN,example.com,DIRECT', 'MATCH,PROXY'])

    def test_overridden_dns_policy_keeps_precedence(self):
        source = '\n'.join(d.yaml_block({'dns': {'nameserver-policy': {
            '+.example.com': ['system'], 'geosite:cn': ['system'], '+.other.com': ['system']}}, 'rules': ['MATCH,PROXY']})) + '\n'
        settings = {'schema_version': 1, 'mihomo': {'dns': {'nameserver-policy': {
            '+.example.com': ['https://1.1.1.1/dns-query'], '+.new.com': ['system']}}}}
        result = n.render({'mihomo.yaml': source}, settings, d.yaml_block)
        policy = yaml.safe_load(result['mihomo.yaml'])['dns']['nameserver-policy']
        self.assertEqual(list(policy), ['+.example.com', 'geosite:cn', '+.other.com', '+.new.com'])
        self.assertEqual(result, n.render(result, settings, d.yaml_block))

    def test_surge_domain_resolvers_and_rejects_injection(self):
        settings = {'schema_version': 1, 'surge': {'hosts': {
            'tunnel.example': 'server:https://223.5.5.5/dns-query', '*.office.example': 'server:system'}}}
        result = n.render({'surge.conf': '[General]\n[Rule]\nFINAL,PROXY\n'}, settings, d.yaml_block)
        self.assertIn('*.office.example = server:system', result['surge.conf'])
        self.assertIn('tunnel.example = server:https://223.5.5.5/dns-query', result['surge.conf'])
        self.assertEqual(result, n.render(result, settings, d.yaml_block))
        settings['surge']['hosts']['tunnel.example'] += '\n[Proxy]'
        with self.assertRaises(ValueError):
            n.validate(settings)

    def test_merge_preserves_generated_dns_and_local_hosts(self):
        original = {'dns': {'nameserver': ['system'], 'fake-ip-filter': ['rule-set:private'],
                           'nameserver-policy': {'rule-set:ai': ['https://1.1.1.1/dns-query#AI'], 'rule-set:private': ['system']}},
                    'hosts': {'nas.home.arpa': '192.168.1.2'},
                    'rules': ['RULE-SET,ai,AI', 'MATCH,FINAL']}
        text = '\n'.join(d.yaml_block(original)) + '\n'
        settings = {'schema_version': 1, 'mihomo': {'dns': {'nameserver': ['https://1.1.1.1/dns-query#PROXY'],
                    'fake-ip-filter': ['+.home.arpa'], 'nameserver-policy': {'rule-set:private': ['rcode://refused']}},
                    'hosts': {'nas.home.arpa': '192.168.1.2', 'printer.home.arpa': ['192.168.1.3']},
                    'rules_prepend': ['NETWORK,udp,PROXY']}}
        output = n.render({'mihomo.yaml': text, 'node.txt': 'unchanged'}, settings, d.yaml_block)
        self.assertEqual(output['node.txt'], 'unchanged')
        parsed = yaml.safe_load(output['mihomo.yaml'])
        self.assertEqual(parsed['dns']['nameserver-policy']['rule-set:ai'], original['dns']['nameserver-policy']['rule-set:ai'])
        self.assertEqual(parsed['dns']['nameserver-policy']['rule-set:private'], ['rcode://refused'])
        self.assertEqual(parsed['dns']['fake-ip-filter'], ['rule-set:private', '+.home.arpa'])
        self.assertEqual(parsed['hosts']['printer.home.arpa'], ['192.168.1.3'])
        self.assertEqual(parsed['rules'][0], 'NETWORK,udp,PROXY')
        self.assertEqual(output, n.render(output, settings, d.yaml_block))

    def test_ini_keeps_tunnel_and_other_sections_and_rejects_injection(self):
        source = '[General]\ndns-server = system\n[Proxy]\nHOME = wireguard, private\n[Rule]\nFINAL,FINAL\n[Host]\nnas = 192.168.1.2\n'
        settings = {'schema_version': 1, 'surge': {'general': {'encrypted-dns-follow-outbound-mode': 'true'},
                    'rules_prepend': ['PROTOCOL,STUN,PROXY']}}
        result = n.render({'surge.conf': source}, settings, d.yaml_block)['surge.conf']
        self.assertIn('HOME = wireguard, private', result)
        self.assertIn('PROTOCOL,STUN,PROXY\nFINAL,FINAL', result)
        self.assertEqual(result, n.render({'surge.conf': result}, settings, d.yaml_block)['surge.conf'])
        settings['surge']['general']['dns-server'] = 'system\n[Proxy]'
        with self.assertRaises(ValueError): n.validate(settings)

    def test_network_inputs_use_email_not_subscription_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); database = root / 'panel.db'
            connection = sqlite3.connect(database)
            connection.execute('CREATE TABLE inbounds (id INTEGER, tag TEXT, enable INTEGER, protocol TEXT, settings TEXT, stream_settings TEXT)')
            client = {'id': 'synthetic-uuid', 'subId': 'different-sub-id', 'email': 'router-email', 'enable': True}
            connection.execute('INSERT INTO inbounds VALUES (1, ?, 1, ?, ?, ?)', ('direct', 'vmess', json.dumps({'clients': [client]}), json.dumps({'network': 'ws', 'wsSettings': {'path': '/synthetic'}})))
            connection.commit(); connection.close()
            private = root / 'network-settings/router.json'; private.parent.mkdir()
            private.write_text(json.dumps({'schema_version': 1, 'mihomo': {'dns': {'respect-rules': True}}}))
            config = {'database': str(database), 'state_dir': tmp, 'server': '192.0.2.1', 'port': 443,
                      'inbounds': {'direct': {'name': 'test', 'udp': True}},
                      'network_profiles': {'router-email': str(private)}}
            account = d.load_accounts(config)['different-sub-id']
            self.assertTrue(account['network']['mihomo']['dns']['respect-rules'])
            config['network_profiles'] = {'misspelled-email': str(private)}
            with self.assertRaisesRegex(ValueError, 'unknown account email'):
                d.load_accounts(config)
            config['network_profiles'] = {'router-email': str(private)}
            connection = sqlite3.connect(database)
            connection.execute('UPDATE inbounds SET enable=0')
            connection.commit(); connection.close()
            self.assertEqual(d.load_accounts(config), {})

    def test_surge_proxy_bootstrap_mapping_keeps_tunnel_dns(self):
        source = '[General]\ndns-server = system\n[Proxy]\nnode = vmess, node.example, 443\n[Rule]\nFINAL,PROXY\n[Host]\n*.home.arpa = server:192.168.1.1\n'
        settings = {'schema_version': 1, 'surge': {'hosts': {'node.example': '192.0.2.1'},
                    'general': {'encrypted-dns-server': 'https://1.1.1.1/dns-query', 'encrypted-dns-follow-outbound-mode': 'true'},
                    'rules_prepend': ['PROTOCOL,STUN,PROXY', 'PROTOCOL,DOH,PROXY']}}
        result = n.render({'surge.conf': source}, settings, d.yaml_block)
        self.assertIn('*.home.arpa = server:192.168.1.1', result['surge.conf'])
        self.assertIn('node.example = 192.0.2.1', result['surge.conf'])
        self.assertEqual(result, n.render(result, settings, d.yaml_block))

    def test_private_paths_and_input_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); p = root / 'network-settings/router.json'; p.parent.mkdir()
            p.write_text(json.dumps({'schema_version': 1, 'mihomo': {'dns': {'respect-rules': True}}}))
            c = {'state_dir': tmp, 'network_profiles': {'router': str(p)}}
            self.assertTrue(n.inputs(c)['router']['mihomo']['dns']['respect-rules'])
            p.write_text(json.dumps({'schema_version': 1, 'mihomo': {'dns': {'respect-rules': False}}}))
            self.assertFalse(n.inputs(c)['router']['mihomo']['dns']['respect-rules'])
            outside = root / 'outside.json'; outside.write_text(p.read_text()); c['network_profiles']['router'] = str(outside)
            with self.assertRaises(ValueError): n.inputs(c)


if __name__ == '__main__': unittest.main()
