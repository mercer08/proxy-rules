"""Private, account-scoped home WireGuard tunnel rendered into every client profile."""
import base64
import ipaddress
import json
from pathlib import Path
import re

NAME = 'HOME-WIREGUARD'
SECTION = 'home-wg'
KEYS = {'schema_version', 'private_key', 'address', 'dns', 'mtu', 'peer', 'home_router', 'test_url', 'home_domains', 'home_networks', 'home_ssids'}
PEER_KEYS = {'public_key', 'preshared_key', 'endpoint', 'allowed_ips', 'keepalive'}


def key(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9+/]{43}=', value) or len(base64.b64decode(value)) != 32:
        raise ValueError('Invalid WireGuard key')
    return value


def validate(settings):
    if not isinstance(settings, dict) or settings.get('schema_version') != 1 or set(settings) - KEYS:
        raise ValueError('Home WireGuard settings schema_version must be 1')
    key(settings.get('private_key'))
    for name in ('address', 'dns', 'home_router'):
        if ipaddress.ip_address(settings.get(name, '')).version != 4:
            raise ValueError('IPv4 ' + name + ' required')
    if not isinstance(settings.get('mtu', 1280), int) or not 1280 <= settings.get('mtu', 1280) <= 1500:
        raise ValueError('Invalid WireGuard MTU')
    if 'test_url' in settings and not re.fullmatch(r'https?://[A-Za-z0-9.:\[\]/_-]+', settings['test_url']):
        raise ValueError('Invalid WireGuard test URL')
    ssids = settings.get('home_ssids', [])
    if not isinstance(ssids, list) or len(ssids) > 10 or any(
            not isinstance(ssid, str) or not 0 < len(ssid.encode()) <= 32 or any(c in ssid for c in '",=\r\n')
            or ssid.strip() != ssid or ssid.lower() in ('default', 'cellular') for ssid in ssids):
        raise ValueError('Invalid home Wi-Fi names')
    peer = settings.get('peer')
    if not isinstance(peer, dict) or set(peer) - PEER_KEYS or not {'public_key', 'endpoint', 'allowed_ips'} <= set(peer):
        raise ValueError('Invalid WireGuard peer')
    key(peer['public_key'])
    if 'preshared_key' in peer:
        key(peer['preshared_key'])
    host, _, port = peer['endpoint'].rpartition(':')
    if not re.fullmatch(r'[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*', host) or not port.isdigit() or not 0 < int(port) < 65536:
        raise ValueError('Invalid WireGuard endpoint')
    if not isinstance(peer.get('keepalive', 25), int) or not 0 <= peer.get('keepalive', 25) <= 3600:
        raise ValueError('Invalid WireGuard keepalive')
    for name, limit in (('allowed_ips', 32), ('home_networks', 100), ('home_domains', 100)):
        values = peer[name] if name == 'allowed_ips' else settings.get(name, [])
        if not isinstance(values, list) or len(values) > limit or (name == 'allowed_ips' and not values):
            raise ValueError('Invalid ' + name)
        for value in values:
            if name == 'home_domains':
                if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*', value):
                    raise ValueError('Invalid home domain')
            elif ipaddress.ip_network(value, strict=True).version != 4:
                raise ValueError('IPv4 networks required')
    return settings


def settings_paths(config):
    mappings = config.get('home_wireguard', {})
    if not isinstance(mappings, dict):
        raise ValueError('home_wireguard must be a mapping')
    if not mappings:
        return {}
    allowed = (Path(config['state_dir']) / 'wireguard-settings').resolve()
    result = {}
    for email, filename in mappings.items():
        path = Path(filename)
        if path.is_symlink() or not path.resolve().is_relative_to(allowed) or not path.is_file():
            raise ValueError('Home WireGuard settings must be a private regular file')
        result[email] = path
    return result


def inputs(config):
    return {email: validate(json.loads(path.read_text())) for email, path in settings_paths(config).items()}


def merge_rules(lines, home_rules):
    """Keep home rules together: after existing HOME entries, otherwise first."""
    missing = [rule for rule in home_rules if rule not in lines]
    existing = [i for i, line in enumerate(lines) if line in home_rules]
    index = existing[-1] + 1 if existing else 0
    return lines[:index] + missing + lines[index:]


def rules(settings):
    return (['DOMAIN-SUFFIX,' + d + ',HOME' for d in settings.get('home_domains', [])] +
            ['IP-CIDR,' + n + ',HOME,no-resolve' for n in settings.get('home_networks', [])])


def endpoint(settings):
    host, _, port = settings['peer']['endpoint'].rpartition(':')
    return host, int(port)


def surge_section(settings):
    peer = settings['peer']
    options = ['public-key = ' + peer['public_key']]
    if peer.get('preshared_key'):
        options.append('preshared-key = ' + peer['preshared_key'])
    options += ['allowed-ips = "' + ', '.join(peer['allowed_ips']) + '"', 'endpoint = ' + peer['endpoint'],
                'keepalive = ' + str(peer.get('keepalive', 25))]
    return ('[WireGuard ' + SECTION + ']\nprivate-key = ' + settings['private_key'] + '\nself-ip = ' + settings['address'] +
            '\ndns-server = ' + settings['dns'] + '\nmtu = ' + str(settings.get('mtu', 1280)) + '\npeer = (' + ', '.join(options) + ')\n')


def loon_proxy(settings):
    peer = settings['peer']
    fields = ['public-key="' + peer['public_key'] + '"']
    if peer.get('preshared_key'):
        fields.append('preshared-key="' + peer['preshared_key'] + '"')
    fields += ['allowed-ips="' + ','.join(peer['allowed_ips']) + '"', 'endpoint=' + peer['endpoint']]
    return (NAME + ' = WireGuard,interface-ip=' + settings['address'] + ',private-key="' + settings['private_key'] + '",mtu=' +
            str(settings.get('mtu', 1280)) + ',dns=' + settings['dns'] + ',keepalive=' + str(peer.get('keepalive', 25)) +
            ',peers=[{' + ','.join(fields) + '}],udp=true')


def shadowrocket_proxy(settings):
    # Shadowrocket's documented one-line form (no [WireGuard] section, no allowed-ips field).
    # The preshared key follows the same camelCase naming as privateKey/publicKey.
    host, port = endpoint(settings)
    peer = settings['peer']
    fields = ['privateKey=' + settings['private_key'], 'publicKey=' + peer['public_key']]
    if peer.get('preshared_key'):
        fields.append('presharedKey=' + peer['preshared_key'])
    fields += ['ip=' + settings['address'], 'dns=' + settings['dns'], 'mtu=' + str(settings.get('mtu', 1280)),
               'keepalive=' + str(peer.get('keepalive', 25)), 'udp=1']
    return NAME + ' = wireguard,' + host + ',' + str(port) + ',' + ','.join(fields)


def add_lines(text, section, lines):
    """Add missing lines to a section, creating it at the end of text when absent."""
    missing = [line for line in lines if line not in text.splitlines()]
    if not missing:
        return text
    header = '[' + section + ']\n'
    if header in text:
        return text.replace(header, header + ''.join(line + '\n' for line in missing), 1)
    return text.rstrip('\n') + '\n\n' + header + ''.join(line + '\n' for line in missing)


def render_conf(text, filename, settings):
    header, body = text.split('[Rule]\n', 1)
    general, rest = header.split('[Proxy]\n', 1)
    nodes, groups = rest.split('[Proxy Group]\n', 1)
    # Loon and Shadowrocket route HOME straight to the node. A fallback test group there marked
    # the only tunnel unavailable after one failed check, until the next check ten minutes later.
    if filename == 'loon.conf':
        node = loon_proxy(settings)
        if settings.get('home_ssids'):
            home = ('HOME = ssid, default = ' + NAME + ', cellular = ' + NAME +
                    ''.join(', "' + ssid + '" = DIRECT' for ssid in settings['home_ssids']))
        else:
            home = 'HOME = select, ' + NAME + ', DIRECT, REJECT'
    elif filename == 'shadowrocket.conf':
        node = shadowrocket_proxy(settings)
        home = 'HOME = select, ' + NAME + ', DIRECT, REJECT, policy-select-name=' + NAME
    else:
        node = NAME + ' = wireguard, section-name=' + SECTION + (', test-url=' + settings['test_url'] + ', test-timeout=8' if settings.get('test_url') else '')
        # Home Wi-Fi names and the home router both mean "at home"; the router also covers wired Macs.
        ssids = ''.join(', ' + ('"SSID:' + ssid + '"' if ' ' in ssid else 'SSID:' + ssid) + '=DIRECT' for ssid in settings.get('home_ssids', []))
        home = 'HOME = subnet, default=' + NAME + ssids + ', ROUTER:' + settings['home_router'] + '=DIRECT'
    nodes = nodes.rstrip() + '\n' + node + '\n\n'
    lines = [line for line in groups.rstrip('\n').splitlines() if not re.match(r'\s*HOME\s*=', line)]
    lines = [('# COMPANY_LAN is local only. HOME uses the home WireGuard tunnel.' if line.startswith('# Local LAN access only.') else line) for line in lines]
    groups = '\n'.join(lines + [home]) + '\n\n'
    if filename == 'surge.conf':
        groups += surge_section(settings) + '\n'
    body = '\n'.join(merge_rules(body.splitlines(), rules(settings))) + '\n'
    # At home HOME is DIRECT, and public DNS only knows the WAN address of home names,
    # so home networks must resolve through the home router.
    router = settings['home_router']
    if filename == 'surge.conf' and not re.search(r'(?m)^ROUTER:' + re.escape(router) + r'\s', body):
        body = add_lines(body, 'SSID Setting', ['ROUTER:' + router + ' dns-server="' + router + '", encrypted-dns-server="off"'])
    elif filename == 'loon.conf' and settings.get('home_ssids'):
        general = add_lines(general, 'Host', ['ssid:' + ssid + ' = server:' + router for ssid in settings['home_ssids']]).rstrip('\n') + '\n\n'
    return general + '[Proxy]\n' + nodes + '[Proxy Group]\n' + groups + '[Rule]\n' + body


def yaml_section(text, name):
    match = re.search(r'(?ms)^' + name + r':\n.*?(?=^[a-z][a-z0-9-]*:|\Z)', text)
    if not match:
        raise ValueError('Missing ' + name + ' section')
    return match


def render_yaml(text, filename, settings, yaml_block):
    host, port = endpoint(settings)
    peer = settings['peer']
    proxy = {'name': NAME, 'type': 'wireguard', 'server': host, 'port': port, 'ip': settings['address'],
             'private-key': settings['private_key'], 'public-key': peer['public_key']}
    if filename == 'mihomo.yaml':
        if peer.get('preshared_key'):
            proxy['pre-shared-key'] = peer['preshared_key']
        proxy.update({'allowed-ips': peer['allowed_ips'], 'persistent-keepalive': peer.get('keepalive', 25), 'remote-dns-resolve': True})
    else:
        if peer.get('preshared_key'):
            proxy['preshared-key'] = peer['preshared_key']
        proxy['keepalive'] = peer.get('keepalive', 25)
    proxy.update({'dns': [settings['dns']], 'mtu': settings.get('mtu', 1280), 'udp': True})
    match = yaml_section(text, 'proxies')
    text = text[:match.end()].rstrip('\n') + '\n' + '\n'.join(yaml_block([proxy], 2)) + '\n' + text[match.end():]
    home = {'name': 'HOME', 'type': 'select', 'proxies': [NAME, 'DIRECT', 'REJECT']}
    if filename == 'stash.yaml' and settings.get('home_ssids'):
        # Stash switches a select group by Wi-Fi name; Mihomo has no SSID matching.
        home['ssid-policy'] = {**{ssid: 'DIRECT' for ssid in settings['home_ssids']}, 'cellular': NAME, 'default': NAME}
    group = '\n'.join(yaml_block([home], 2)) + '\n'
    match = yaml_section(text, 'proxy-groups')
    block, count = re.subn(r'(?ms)^  -\n    name: "HOME"\n.*?(?=^  -\n|\Z)', lambda m: group, match.group())
    if not count:
        block = block.rstrip('\n') + '\n' + group
    text = text[:match.start()] + block + text[match.end():]
    patterns = ['+.' + d for d in settings.get('home_domains', [])]
    resolver = settings['dns'] + '#HOME' if filename == 'mihomo.yaml' else 'system'
    for name, entries in (('nameserver-policy', [json.dumps(p) + ': ' + json.dumps(resolver) for p in patterns]),
                          ('fake-ip-filter', ['- ' + json.dumps(p) for p in patterns])):
        text = text.replace('  ' + name + ': {}\n', '  ' + name + ':\n').replace('  ' + name + ': []\n', '  ' + name + ':\n')
        match = re.search(r'(?m)^  ' + name + r':\n((?:    [^\n]*\n)*)', text)
        if not match:
            raise ValueError('Missing DNS ' + name)
        lines = match.group(1).splitlines(keepends=True)
        # Home names always use the tunnel resolver instead of an earlier personal default.
        lines = [line for line in lines if not any(line.startswith('    ' + json.dumps(p) + ':') for p in patterns)]
        existing = ''.join(lines)
        added = ''.join('    ' + entry + '\n' for entry in entries if '    ' + entry + '\n' not in existing)
        text = text[:match.start(1)] + added + existing + text[match.end(1):]
    header, body = text.split('rules:\n', 1)
    return header + 'rules:\n' + '\n'.join(merge_rules(body.splitlines(), ['  - ' + json.dumps(rule) for rule in rules(settings)])) + '\n'


def render(profiles, settings, yaml_block):
    """Add the tunnel before Loon conversion, so all five apps share one rule order."""
    if not settings:
        return profiles
    validate(settings)
    output = dict(profiles)
    for filename, text in profiles.items():
        if filename in ('surge.conf', 'shadowrocket.conf', 'loon.conf'):
            output[filename] = render_conf(text, filename, settings)
        elif filename in ('mihomo.yaml', 'stash.yaml'):
            output[filename] = render_yaml(text, filename, settings, yaml_block)
    return output
