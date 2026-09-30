import importlib.util
from pathlib import Path
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('final_order_distribution', ROOT / 'deployment/distribute.py')
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)


class FinalOrderTests(unittest.TestCase):
    def test_ini_keeps_device_login_and_default_choices(self):
        source = ('[Proxy]\nHOME-TAILSCALE = tailscale, section-name=home-tailnet\n'
                  '[Proxy Group]\nPROXY = select, dmit-lax\nFINAL = select, DIRECT, PROXY\nHOME = subnet, default=HOME-TAILSCALE\n'
                  '[Rule]\nDOMAIN-SUFFIX,home.arpa,HOME\nFINAL,FINAL,dns-failed\n'
                  '[Tailscale home-tailnet]\ninteractive-login = true\n')
        for name in ('surge.conf', 'shadowrocket.conf'):
            result = d.final_last_profile(source, name)
            self.assertIn('HOME = subnet, default=HOME-TAILSCALE\nFINAL = select, DIRECT, PROXY\n[Rule]', result)
            self.assertEqual(result.split('[Rule]', 1)[1], source.split('[Rule]', 1)[1])
            self.assertEqual(result.split('[Proxy Group]', 1)[0], source.split('[Proxy Group]', 1)[0])
            self.assertEqual(d.final_last_profile(result, name), result)

    def test_yaml_preserves_all_values_and_group_metadata(self):
        value = {'proxies': [{'name': 'dmit-lax', 'udp': True}],
                 'proxy-groups': [{'name': 'PROXY', 'type': 'select', 'proxies': ['dmit-lax']},
                                  {'name': 'FINAL', 'type': 'select', 'proxies': ['DIRECT', 'PROXY'], 'icon': 'https://example.com/icon'},
                                  {'name': 'HOME', 'type': 'select', 'proxies': ['DIRECT', 'REJECT']}],
                 'rules': ['DOMAIN-SUFFIX,home.arpa,HOME', 'MATCH,FINAL'],
                 'dns': {'nameserver-policy': {'home.arpa': ['system']}}}
        for name in ('mihomo.yaml', 'stash.yaml'):
            source = '\n'.join(d.yaml_block(value)) + '\n'
            result = d.final_last_profile(source, name)
            parsed = yaml.safe_load(result)
            self.assertEqual([g['name'] for g in parsed['proxy-groups']], ['PROXY', 'HOME', 'FINAL'])
            parsed['proxy-groups'] = value['proxy-groups']
            self.assertEqual(parsed, value)
            self.assertEqual(d.final_last_profile(result, name), result)

    def test_moves_early_catchall_without_reordering_specific_rules(self):
        source = 'rules:\n  - "MATCH,FINAL"\n  - "DOMAIN,a.example,DIRECT"\n  - "DOMAIN,b.example,PROXY"\n'
        result = yaml.safe_load(d.final_last_profile(source, 'mihomo.yaml'))
        self.assertEqual(result['rules'], ['DOMAIN,a.example,DIRECT', 'DOMAIN,b.example,PROXY', 'MATCH,FINAL'])

    def test_duplicate_finals_fail_instead_of_losing_configuration(self):
        for name, source in [('surge.conf', '[Proxy Group]\nFINAL = select, DIRECT\nFINAL = select, PROXY\n'),
                             ('stash.yaml', 'proxy-groups:\n  - name: FINAL\n    proxies: [DIRECT]\n  - name: FINAL\n    proxies: [PROXY]\n')]:
            with self.assertRaises(ValueError):
                d.final_last_profile(source, name)

    def test_node_exports_remain_byte_identical(self):
        for name in ('node.txt', 'shadowrocket.txt'):
            self.assertEqual(d.final_last_profile('vmess://synthetic\n', name), 'vmess://synthetic\n')


if __name__ == '__main__':
    unittest.main()
