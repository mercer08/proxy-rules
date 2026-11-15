import base64
from pathlib import Path
import sys
import unittest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'deployment'))
import distribute as d
import wireguard as w

CONF = '[General]\nloglevel = notify\n\n[Proxy]\ndmit-lax = direct\n\n[Proxy Group]\nPROXY = select, dmit-lax\n\n[Rule]\nFINAL,PROXY\n'
YAML = ('proxies:\n  -\n    name: "dmit-lax"\n    type: "direct"\nproxy-groups:\n  -\n    name: "PROXY"\n    type: "select"\n'
        '    proxies:\n      - "dmit-lax"\ndns:\n  nameserver-policy: {}\n  fake-ip-filter: []\nrules:\n  - "MATCH,PROXY"\n')


def guest():
    """Synthetic guest peer that may reach one home host only; no home router, domains or Wi-Fi."""
    return {'schema_version': 1, 'private_key': base64.b64encode(bytes(32)).decode(), 'address': '10.77.0.9', 'dns': '10.77.0.1',
            'home_networks': ['172.16.0.128/32'],
            'peer': {'public_key': base64.b64encode(bytes([1] * 32)).decode(), 'endpoint': 'home.example:51820',
                     'allowed_ips': ['172.16.0.128/32']}}


class GuestWireGuardTests(unittest.TestCase):
    def render(self, settings):
        profiles = {name: CONF for name in ('surge.conf', 'shadowrocket.conf', 'loon.conf')}
        profiles.update({name: YAML for name in ('mihomo.yaml', 'stash.yaml')})
        return w.render(profiles, settings, d.yaml_block)

    def test_single_host_guest_never_switches_to_direct_on_a_foreign_gateway(self):
        output = self.render(guest())
        surge = output['surge.conf']
        self.assertIn('HOME = subnet, default=HOME-WIREGUARD\n', surge)
        self.assertNotIn('ROUTER:', surge)
        self.assertNotIn('[SSID Setting]', surge)
        self.assertIn('allowed-ips = "172.16.0.128/32"', surge)
        for name in ('surge.conf', 'shadowrocket.conf', 'loon.conf'):
            rules = output[name].split('[Rule]\n', 1)[1].splitlines()
            self.assertEqual(rules[0], 'IP-CIDR,172.16.0.128/32,HOME,no-resolve', name)
            self.assertNotIn('DOMAIN-SUFFIX', output[name].split('[Rule]\n', 1)[1], name)
        self.assertNotIn('[Host]', output['loon.conf'])
        for name in ('mihomo.yaml', 'stash.yaml'):
            parsed = yaml.safe_load(output[name])
            self.assertEqual(parsed['rules'][0], 'IP-CIDR,172.16.0.128/32,HOME,no-resolve', name)
            self.assertFalse(parsed['dns']['nameserver-policy'], name)
        tunnel = next(p for p in yaml.safe_load(output['mihomo.yaml'])['proxies'] if p['name'] == 'HOME-WIREGUARD')
        self.assertEqual(tunnel['allowed-ips'], ['172.16.0.128/32'])

    def test_home_router_still_validated_and_rendered_when_present(self):
        settings = dict(guest(), home_router='172.16.0.1')
        surge = self.render(settings)['surge.conf']
        self.assertIn('HOME = subnet, default=HOME-WIREGUARD, ROUTER:172.16.0.1=DIRECT\n', surge)
        self.assertIn('ROUTER:172.16.0.1 dns-server="172.16.0.1"', surge)
        with self.assertRaises(ValueError):
            w.validate(dict(guest(), home_router='not-an-ip'))


if __name__ == '__main__':
    unittest.main()
