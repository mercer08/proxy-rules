"""Render a firewall4 include that prevents protected devices bypassing Nikki."""
import argparse
import ipaddress
import json
from pathlib import Path
import re

from netsettings import PRIVATE_DESTINATIONS


def render(settings):
    if not isinstance(settings, dict) or set(settings) != {'sources', 'macs', 'endpoints', 'tun_device'}:
        raise ValueError('Invalid device guard settings')
    if not re.fullmatch(r'[A-Za-z0-9_-]+', settings['tun_device']):
        raise ValueError('Invalid TUN device')
    sources = [ipaddress.IPv4Address(source) for source in settings['sources']]
    if not sources or any(not source.is_private for source in sources):
        raise ValueError('Private device addresses required')
    macs = settings['macs']
    if not macs or any(not isinstance(mac, str) or not re.fullmatch(r'(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}', mac) for mac in macs):
        raise ValueError('Device MAC addresses required')
    endpoints = []
    for endpoint in settings['endpoints']:
        address = ipaddress.IPv4Address(endpoint['address'])
        port = endpoint['port']
        if address.is_private or type(port) is not int or not 0 < port < 65536:
            raise ValueError('Public proxy endpoint required')
        endpoints.append(str(address) + ' . ' + str(port))
    if not endpoints:
        raise ValueError('Proxy endpoints required')
    return '''# Managed device proxy guard. Included inside table inet fw4.
# Fail closed even if Nikki is stopped; only private LAN and trusted proxy transport pass.
set device_proxy_sources {
    type ipv4_addr
    elements = { SOURCES }
}
set device_proxy_macs {
    type ether_addr
    elements = { MACS }
}
set device_proxy_endpoints {
    type ipv4_addr . inet_service
    elements = { ENDPOINTS }
}
chain device_proxy_forward {
    type filter hook forward priority -10; policy accept;
    ether saddr @device_proxy_macs meta nfproto ipv4 ip saddr != @device_proxy_sources counter drop comment "device-proxy: unexpected IPv4 source"
    ip saddr @device_proxy_sources ip daddr { PRIVATE } counter return comment "device-proxy: private LAN"
    ip saddr @device_proxy_sources meta l4proto tcp ip daddr . tcp dport @device_proxy_endpoints counter return comment "device-proxy: trusted proxy transport"
    ip saddr @device_proxy_sources oifname "TUN_DEVICE" counter return comment "device-proxy: Nikki TUN"
    ip saddr @device_proxy_sources counter drop comment "device-proxy: block direct IPv4"
    ether saddr @device_proxy_macs meta nfproto ipv6 ip6 daddr { fc00::/7, fe80::/10, ff00::/8 } counter return comment "device-proxy: private IPv6"
    ether saddr @device_proxy_macs meta nfproto ipv6 counter drop comment "device-proxy: block public IPv6"
}
'''.replace('SOURCES', ', '.join(map(str, sources))).replace('MACS', ', '.join(macs)).replace('ENDPOINTS', ', '.join(endpoints)).replace('PRIVATE', ', '.join(PRIVATE_DESTINATIONS)).replace('TUN_DEVICE', settings['tun_device'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('settings', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.write_text(render(json.loads(args.settings.read_text())))
