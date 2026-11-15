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
