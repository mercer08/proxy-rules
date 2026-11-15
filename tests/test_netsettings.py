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
import deviceguard


class NetworkSettingsTests(unittest.TestCase):
    def test_local_dns_authority_precedes_private_policy_and_ai_reordering(self):
        original = {'dns': {'nameserver-policy': {'rule-set:private': ['rcode://refused'],
                    'rule-set:ai': ['https://1.1.1.1/dns-query#AI']}},
                    'rules': ['RULE-SET,private,DIRECT', 'RULE-SET,ai,AI', 'MATCH,PROXY']}
        source = '\n'.join(d.yaml_block(original)) + '\n'
        policies = {'+.home.arpa': ['127.0.0.1:53'], '+.10.in-addr.arpa': ['127.0.0.1:53']}
        settings = {'schema_version': 1, 'mihomo': {'dns_policy_prepend': policies}}
        output = n.render({'mihomo.yaml': source}, settings, d.yaml_block)
        output['mihomo.yaml'] = d.prioritize_mihomo_ai(output['mihomo.yaml'], policies)
        parsed = yaml.safe_load(output['mihomo.yaml'])['dns']['nameserver-policy']
        self.assertEqual(list(parsed)[:3], ['+.home.arpa', '+.10.in-addr.arpa', 'rule-set:private'])
        again = n.render(output, settings, d.yaml_block)
        again['mihomo.yaml'] = d.prioritize_mihomo_ai(again['mihomo.yaml'], policies)
        self.assertEqual(output, again)

    def test_device_proxy_overrides_public_direct_but_keeps_lan_and_transport(self):
        source = '\n'.join(d.yaml_block({'dns': {'enable': True}, 'proxy-groups': [
            {'name': 'PROXY', 'type': 'select', 'proxies': ['test-node']}], 'rules': [
            'DOMAIN-SUFFIX,example.cn,DIRECT', 'MATCH,DIRECT']})) + '\n'
        settings = {'schema_version': 1, 'mihomo': {'device_proxy': {
            'name': 'DEVICE-PRIVATE', 'sources': ['172.16.0.113/32']}}}
        proxies = [{'name': 'test-node', 'type': 'vmess', 'server': '8.8.8.8', 'port': 443, 'udp': True}]
        output = n.render({'mihomo.yaml': source}, settings, d.yaml_block, proxies)
        parsed = yaml.safe_load(output['mihomo.yaml'])
        self.assertEqual(parsed['proxy-groups'][-1], {'name': 'DEVICE-PRIVATE', 'type': 'select', 'proxies': ['test-node', 'REJECT']})
        guard = 'SRC-IP-CIDR,172.16.0.113/32,DEVICE-PRIVATE'
        index = parsed['rules'].index(guard)
        self.assertEqual(parsed['rules'][index + 1], 'SRC-IP-CIDR,172.16.0.113/32,REJECT')
        self.assertLess(index, parsed['rules'].index('DOMAIN-SUFFIX,example.cn,DIRECT'))
        self.assertTrue(any('IP-CIDR,192.168.0.0/16' in rule for rule in parsed['rules'][:index]))
        self.assertTrue(any('NETWORK,tcp' in rule and 'DST-PORT,443' in rule for rule in parsed['rules'][:index]))
        self.assertEqual(output, n.render(output, settings, d.yaml_block, proxies))
        proxies[0]['udp'] = False
        with self.assertRaisesRegex(ValueError, 'UDP-capable'):
            n.render({'mihomo.yaml': source}, settings, d.yaml_block, proxies)

    def test_native_stun_reject_only_supported_clients(self):
        settings = {'schema_version': 1, **{client: {'reject_stun': True} for client in ('surge', 'stash', 'loon')}}
        profiles = {'surge.conf': '[General]\n[Rule]\nFINAL,PROXY\n', 'loon.conf': '[General]\n[Rule]\nFINAL,PROXY\n',
                    'stash.yaml': 'dns:\n  enable: true\nrules:\n  - MATCH,PROXY\n', 'mihomo.yaml': 'unchanged', 'shadowrocket.conf': 'unchanged'}
        output = n.render(profiles, settings, d.yaml_block)
        for name in ('surge.conf', 'loon.conf'):
            self.assertIn('[Rule]\nPROTOCOL,STUN,REJECT\n', output[name])
        self.assertEqual(yaml.safe_load(output['stash.yaml'])['rules'][0], 'PROTOCOL,STUN,REJECT')
        self.assertEqual(output['mihomo.yaml'], 'unchanged')
        self.assertEqual(output['shadowrocket.conf'], 'unchanged')
        self.assertEqual(output, n.render(output, settings, d.yaml_block))
        for client in ('mihomo', 'shadowrocket'):
            with self.assertRaises(ValueError):
                n.validate({'schema_version': 1, client: {'reject_stun': True}})

    def test_device_firewall_closes_direct_ipv4_ipv6_and_validates_inputs(self):
        settings = {'sources': ['172.16.0.113'], 'macs': ['02:00:00:00:00:01'],
                    'endpoints': [{'address': '8.8.8.8', 'port': 443}], 'tun_device': 'nikki'}
        text = deviceguard.render(settings)
        self.assertIn('hook forward priority -10', text)
        self.assertIn('block direct IPv4', text)
        self.assertIn('block public IPv6', text)
        self.assertIn('unexpected IPv4 source', text)
        self.assertNotIn('ct state established', text)  # Established direct flows must also be stopped.
        self.assertLess(text.index('trusted proxy transport'), text.index('block direct IPv4'))
        with self.assertRaises(ValueError):
            deviceguard.render({**settings, 'tun_device': 'nikki"; accept'})
        with self.assertRaises(ValueError):
            deviceguard.render({**settings, 'macs': ['invalid']})

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
        source = 'dns:\n  enable: true\nsub-rules:\n  child:\n    - MATCH,DIRECT\nrules:\n  - "RULE-SET,ai,AI"\n  - MATCH,PROXY\n'
        settings = {'schema_version': 1, 'mihomo': {'rules_prepend': ['DOMAIN,example.com,DIRECT']}}
        parsed = yaml.safe_load(d.prioritize_mihomo_ai(n.render({'mihomo.yaml': source}, settings, d.yaml_block)['mihomo.yaml']))
        self.assertEqual(parsed['sub-rules'], {'child': ['MATCH,DIRECT']})
        self.assertEqual(parsed['rules'], ['DOMAIN,example.com,DIRECT', 'RULE-SET,ai,AI', 'MATCH,PROXY'])

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
