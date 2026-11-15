"""Account-scoped network inputs; never store whole generated profiles as overrides."""
import json
import ipaddress
from pathlib import Path
import re
from urllib.parse import urlsplit

YAML_CLIENTS = {'mihomo': 'mihomo.yaml', 'stash': 'stash.yaml'}
INI_CLIENTS = {'surge': 'surge.conf', 'shadowrocket': 'shadowrocket.conf', 'loon': 'loon.conf'}
STUN_CLIENTS = {'surge', 'stash', 'loon'}
PRIVATE_DESTINATIONS = ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '169.254.0.0/16', '127.0.0.0/8')


def validate(settings):
    if not isinstance(settings, dict) or settings.get('schema_version') != 1 or set(settings) - {'schema_version', *YAML_CLIENTS, *INI_CLIENTS}:
        raise ValueError('Invalid network settings schema')
    for client, options in settings.items():
        if client == 'schema_version':
            continue
        allowed = {'dns', 'hosts', 'rules_prepend'} if client in YAML_CLIENTS else {'general', 'hosts', 'rules_prepend'}
        if client in STUN_CLIENTS:
            allowed.add('reject_stun')
        if client == 'mihomo':
            allowed.add('device_proxy')
        if client in YAML_CLIENTS:
            allowed.add('dns_policy_prepend')
        if not isinstance(options, dict) or set(options) - allowed:
            raise ValueError('Unsupported network option')
        if 'reject_stun' in options and type(options['reject_stun']) is not bool:
            raise ValueError('reject_stun must be boolean')
        if 'dns_policy_prepend' in options:
            policies = options['dns_policy_prepend']
            if not isinstance(policies, dict) or any(not isinstance(k, str) or not k or any(c in k for c in '\r\n') or
                    not isinstance(v, list) or not v or any(not isinstance(x, str) or not x or any(c in x for c in '\r\n') for x in v)
                    for k, v in policies.items()):
                raise ValueError('Invalid priority DNS policies')
        if 'device_proxy' in options:
            device = options['device_proxy']
            if not isinstance(device, dict) or set(device) != {'name', 'sources'} or not isinstance(device['name'], str) or not re.fullmatch(r'DEVICE-[A-Z0-9-]+', device['name']):
                raise ValueError('Invalid device proxy group')
            if not isinstance(device['sources'], list) or not device['sources']:
                raise ValueError('Device proxy requires source addresses')
            for source in device['sources']:
                network = ipaddress.ip_network(source, strict=True)
                if network.version != 4 or network.prefixlen != 32 or not network.is_private:
                    raise ValueError('Device proxy requires private IPv4 /32 sources')
        rules = options.get('rules_prepend', [])
        if not isinstance(rules, list) or any(not isinstance(r, str) or not r or '\n' in r or '\r' in r for r in rules):
            raise ValueError('Invalid network rules')
        if client in YAML_CLIENTS:
            hosts = options.get('hosts', {})
            if not isinstance(hosts, dict):
                raise ValueError('Invalid hosts mapping')
            for name, addresses in hosts.items():
                if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_*+.-]+', name):
                    raise ValueError('Invalid hosts name')
                for address in addresses if isinstance(addresses, list) else [addresses]:
                    ipaddress.ip_address(address)
            dns = options.get('dns', {})
            allowed_dns = {'enable', 'ipv6', 'listen', 'enhanced-mode', 'fake-ip-range', 'fake-ip-filter',
                           'respect-rules', 'follow-rule', 'prefer-h3', 'use-hosts', 'use-system-hosts',
                           'default-nameserver', 'proxy-server-nameserver', 'direct-nameserver',
                           'direct-nameserver-follow-policy', 'nameserver', 'nameserver-policy'}
            if not isinstance(dns, dict) or set(dns) - allowed_dns:
                raise ValueError('Unsupported DNS option')
            for key in ('fake-ip-filter', 'default-nameserver', 'proxy-server-nameserver', 'direct-nameserver', 'nameserver'):
                if key in dns and (not isinstance(dns[key], list) or not dns[key] or any(not isinstance(x, str) or '\n' in x or '\r' in x for x in dns[key])):
                    raise ValueError('Invalid DNS list')
            if not isinstance(dns.get('nameserver-policy', {}), dict):
                raise ValueError('Invalid DNS policy mapping')
        else:
            hosts = options.get('hosts', {})
            if not isinstance(hosts, dict):
                raise ValueError('Invalid static hosts')
            for name, address in hosts.items():
                if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_*?.-]+', name) or not isinstance(address, str):
                    raise ValueError('Invalid static host')
                if client == 'surge' and address.startswith('server:'):
                    resolver = address[len('server:'):]
                    if resolver == 'system':
                        continue
                    if resolver.startswith('https://'):
                        url = urlsplit(resolver)
                        if not re.fullmatch(r'https://[A-Za-z0-9.:-]+/[A-Za-z0-9/_-]+', resolver) or not url.hostname or url.username or url.password:
                            raise ValueError('Invalid host DNS server')
                    else:
                        ipaddress.ip_address(resolver)
                else:
                    ipaddress.ip_address(address)
            general = options.get('general', {})
            if not isinstance(general, dict) or any(not re.fullmatch('[a-z][a-z0-9-]*', k) or not isinstance(v, str) or any(c in v for c in '\r\n') for k, v in general.items()):
                raise ValueError('Invalid General settings')
    return settings


def inputs(config):
    mappings = config.get('network_profiles', {})
    if not isinstance(mappings, dict):
        raise ValueError('network_profiles must be a mapping')
    if not mappings:
        return {}
    allowed = (Path(config['state_dir']) / 'network-settings').resolve()
    result = {}
    for email, filename in mappings.items():
        path = Path(filename)
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(allowed):
            raise ValueError('Network settings must be private regular files')
        result[email] = validate(json.loads(path.read_text()))
    return result


def yaml_dns(text, changes, yaml_block, prepend_policy=False):
    match = re.search(r'(?ms)^dns:\n(.*?)(?=^[a-z][a-z0-9-]*:|\Z)', text)
    if not match:
        raise ValueError('Missing generated DNS section')
    body = match[1]
    for key, value in changes.items():
        pattern = r'(?ms)^  ' + re.escape(key) + r':[^\n]*\n.*?(?=^  [a-z][a-z0-9-]*:|\Z)'
        existing = re.search(pattern, body)
        if key == 'fake-ip-filter' and existing:
            # Generated list values are JSON strings; retain private/provider filters.
            old = [json.loads(v) for v in re.findall(r'^    - (.+)$', existing[0], re.M)]
            value = list(dict.fromkeys(old + value))
        replacement = '\n'.join(yaml_block({key: value}, 2)) + '\n'
        if key == 'nameserver-policy' and existing:
            # Replace requested keys in place: policy order determines precedence.
            previous = existing[0].split('\n', 1)[1]
            pending = dict(value)
            for name, entry in value.items():
                policy = r'(?m)^    (?:' + re.escape(json.dumps(name)) + '|' + re.escape(name) + r'):[^\n]*\n(?:      [^\n]*\n)*'
                if prepend_policy:
                    previous = re.sub(policy, '', previous)
                    continue
                block = '\n'.join(yaml_block({name: entry}, 4)) + '\n'
                previous, count = re.subn(policy, lambda _: block, previous, count=1)
                if count:
                    pending.pop(name)
            replacement = '  nameserver-policy:\n' + previous
            if pending:
                added = '\n'.join(yaml_block(pending, 4)) + '\n'
                replacement = '  nameserver-policy:\n' + added + previous if prepend_policy else replacement + added
        body = re.sub(pattern, lambda _: replacement, body, count=1) if existing else body + replacement
    return text[:match.start(1)] + body + text[match.end(1):]


def device_proxy(text, settings, yaml_block, proxies):
    """Route a device before ordinary policy; only LAN and proxy transport bypass it."""
    if not proxies or any(p.get('type') != 'vmess' or not p.get('udp') for p in proxies):
        raise ValueError('Device proxy requires UDP-capable VMess nodes')
    names = [p['name'] for p in proxies]
    if settings['name'] in names or len(names) != len(set(names)):
        raise ValueError('Conflicting device proxy group')
    section = re.search(r'(?ms)^proxy-groups:\n(.*?)(?=^[a-z][a-z0-9-]*:|\Z)', text)
    if not section:
        raise ValueError('Missing generated proxy groups')
    block = '\n'.join(yaml_block([{'name': settings['name'], 'type': 'select', 'proxies': names + ['REJECT']}], 2)) + '\n'
    pattern = r'(?ms)^  -\n    name: ' + re.escape(json.dumps(settings['name'])) + r'\n.*?(?=^  -|\Z)'
    previous = re.search(pattern, section[1])
    if previous and previous[0].strip() != block.strip():
        raise ValueError('Conflicting device proxy group')
    if not previous:
        text = text[:section.end(1)] + block + text[section.end(1):]
    rules = []
    for source in settings['sources']:
        for destination in PRIVATE_DESTINATIONS:
            rules.append('AND,((SRC-IP-CIDR,' + source + '),(IP-CIDR,' + destination + ')),DIRECT')
        for proxy in proxies:
            address = ipaddress.ip_address(proxy['server'])
            if address.version != 4 or address.is_private or not isinstance(proxy['port'], int) or not 0 < proxy['port'] < 65536:
                raise ValueError('Device proxy requires public IPv4 node endpoints')
            # The endpoint is a trusted proxy transport, not an arbitrary direct destination.
            rules.append('AND,((SRC-IP-CIDR,' + source + '),(NETWORK,tcp),(IP-CIDR,' + str(address) + '/32),(DST-PORT,' + str(proxy['port']) + ')),DIRECT')
        rules += ['SRC-IP-CIDR,' + source + ',' + settings['name'], 'SRC-IP-CIDR,' + source + ',REJECT']
    section = re.search(r'(?m)^rules:\n', text)
    if not section:
        raise ValueError('Missing generated rules section')
    lines = ['  - ' + json.dumps(rule) for rule in rules]
    body = [line for line in text[section.end():].splitlines() if line not in lines]
    return text[:section.end()] + '\n'.join(lines + body) + '\n'


def render(profiles, settings, yaml_block, proxies=None):
    if not settings:
        return profiles
    validate(settings)
    output = dict(profiles)
    for client, filename in {**YAML_CLIENTS, **INI_CLIENTS}.items():
        if client not in settings or filename not in output:
            continue
        options = settings[client]
        text = output[filename]
        if client in YAML_CLIENTS:
            text = yaml_dns(text, options.get('dns', {}), yaml_block)
            if options.get('dns_policy_prepend'):
                text = yaml_dns(text, {'nameserver-policy': options['dns_policy_prepend']}, yaml_block, prepend_policy=True)
            if options.get('hosts'):
                section = re.search(r'(?ms)^hosts:\n(.*?)(?=^[a-z][a-z0-9-]*:|\Z)', text)
                body = section[1] if section else ''
                for name, address in options['hosts'].items():
                    pattern = r'(?ms)^  (?:' + re.escape(json.dumps(name)) + '|' + re.escape(name) + r'):[^\n]*\n(?:    [^\n]*\n)*'
                    body = re.sub(pattern, '', body)
                    body += '\n'.join(yaml_block({name: address}, 2)) + '\n'
                replacement = 'hosts:\n' + body
                text = text[:section.start()] + replacement + text[section.end():] if section else replacement + text
            section = re.search(r'(?m)^rules:\n', text)
            header, marker, body = (text[:section.start()], section[0], text[section.end():]) if section else (text, '', '')
            lines = ['  - ' + json.dumps(r) for r in options.get('rules_prepend', [])]
        else:
            hosts = options.get('hosts', {})
            if hosts:
                section = re.search(r'(?ms)^\[Host\]\n(.*?)(?=^\[|\Z)', text)
                extra = ''
                for domain, address in hosts.items():
                    found = re.search(r'(?m)^' + re.escape(domain) + r'\s*=\s*(.*?)\s*$', section[1]) if section else None
                    if found and found[1] != address:
                        raise ValueError('Conflicting static proxy host')
                    if not found:
                        extra += domain + ' = ' + address + '\n'
                if section:
                    text = text[:section.end()].rstrip() + '\n' + extra + text[section.end():]
                else:
                    text += '\n[Host]\n' + extra
            general = options.get('general', {})
            if general:
                section = re.search(r'(?ms)^\[General\]\n(.*?)(?=^\[|\Z)', text)
                if not section:
                    raise ValueError('Missing generated General section')
                body = section[1]
                for key, value in general.items():
                    body = re.sub(r'(?m)^' + re.escape(key) + r'\s*=.*\n?', '', body)
                    body = key + ' = ' + value + '\n' + body
                text = text[:section.start(1)] + body + text[section.end(1):]
            header, marker, body = text.partition('[Rule]\n')
            lines = options.get('rules_prepend', [])
        if not marker:
            raise ValueError('Missing generated rules section')
        if options.get('reject_stun'):
            stun = '  - ' + json.dumps('PROTOCOL,STUN,REJECT') if client in YAML_CLIENTS else 'PROTOCOL,STUN,REJECT'
            lines = [stun] + lines
        text = header + marker + ''.join(line + '\n' for line in lines if line not in body.splitlines()) + body
        if options.get('device_proxy'):
            text = device_proxy(text, options['device_proxy'], yaml_block, proxies)
        output[filename] = text
    return output
