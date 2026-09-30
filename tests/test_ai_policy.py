import importlib.util
from pathlib import Path
import sys
import unittest

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'deployment'))
import distribute as d


class AiPolicyTests(unittest.TestCase):
    def test_ini_override_cannot_select_direct(self):
        for name in ('surge.conf', 'shadowrocket.conf'):
            source = ('[Proxy Group]\nPROXY = select, dmit-lax\n'
                      'AI = select, DIRECT, PROXY, policy-select-name=DIRECT, icon-url=https://example.com/ai.png\n'
                      'APPLE = select, DIRECT, PROXY\nFINAL = select, DIRECT, PROXY\n'
                      '[Rule]\nRULE-SET,https://example.com/ai.list,AI\nFINAL,FINAL,dns-failed\n'
                      '[Tailscale home-tailnet]\ninteractive-login = true\n')
            result = d.normalize_profile(source, name)
            expected = source.replace('AI = select, DIRECT, PROXY, policy-select-name=DIRECT,',
                                      'AI = select, PROXY, policy-select-name=PROXY,')
            self.assertEqual(result, expected)
            self.assertEqual(d.normalize_profile(result, name), result)

    def test_yaml_keeps_rules_and_other_group_settings(self):
        document = {'dns': {'enable': True},
                    'proxy-groups': [
                        {'name': 'PROXY', 'type': 'select', 'proxies': ['dmit-lax']},
                        {'name': 'AI', 'type': 'select', 'proxies': ['DIRECT', 'PROXY'],
                         'icon': 'https://example.com/ai.png'},
                        {'name': 'APPLE', 'type': 'select', 'proxies': ['DIRECT', 'PROXY']},
                        {'name': 'FINAL', 'type': 'select', 'proxies': ['DIRECT', 'PROXY']}],
                    'rules': ['RULE-SET,ai,AI', 'MATCH,FINAL']}
        for name in ('mihomo.yaml', 'stash.yaml'):
            for source in (yaml.safe_dump(document, sort_keys=False),
                           '\n'.join(d.yaml_block(document)) + '\n'):
                result = d.normalize_profile(source, name)
                expected = yaml.safe_load(source)
                expected['proxy-groups'][1]['proxies'] = ['PROXY']
                self.assertEqual(yaml.safe_load(result), expected)
                self.assertEqual(d.normalize_profile(result, name), result)

    def test_flow_choices_and_direct_only_override(self):
        source = 'proxy-groups:\n  - name: AI\n    type: select\n    proxies: [DIRECT]\n  - name: FINAL\n    type: select\n    proxies: [DIRECT, PROXY]\nrules:\n  - MATCH,FINAL\n'
        result = yaml.safe_load(d.normalize_profile(source, 'stash.yaml'))
        self.assertEqual(result['proxy-groups'][0]['proxies'], ['PROXY'])

    def test_duplicate_ai_fails_instead_of_partial_enforcement(self):
        source = '[Proxy Group]\nAI = select, DIRECT, PROXY\nAI = select, PROXY\n'
        with self.assertRaises(ValueError):
            d.normalize_profile(source, 'surge.conf')

    def test_node_exports_unchanged(self):
        for name in ('node.txt', 'shadowrocket.txt'):
            source = 'vmess://synthetic\n'
            self.assertEqual(d.normalize_profile(source, name), source)


if __name__ == '__main__':
    unittest.main()
