"""Account-scoped network inputs; never store whole generated profiles as overrides."""
import json
import ipaddress
from pathlib import Path
import re

YAML_CLIENTS = {'mihomo': 'mihomo.yaml', 'stash': 'stash.yaml'}
INI_CLIENTS = {'surge': 'surge.conf', 'shadowrocket': 'shadowrocket.conf', 'loon': 'loon.conf'}


def validate(settings):
    if not isinstance(settings, dict) or settings.get('schema_version') != 1 or set(settings) - {'schema_version', *YAML_CLIENTS, *INI_CLIENTS}:
        raise ValueError('Invalid network settings schema')
    for client, options in settings.items():
        if client == 'schema_version':
            continue
        allowed = {'dns', 'hosts', 'rules_prepend'} if client in YAML_CLIENTS else {'general', 'hosts', 'rules_prepend'}
        if not isinstance(options, dict) or set(options) - allowed:
            raise ValueError('Unsupported network option')
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
                if not re.fullmatch(r'[A-Za-z0-9_.-]+', name) or not isinstance(address, str):
                    raise ValueError('Invalid static host')
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


def yaml_dns(text, changes, yaml_block):
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
            # Replace only requested keys, preserving all generated service/home policies.
            previous = existing[0].split('\n', 1)[1]
            for name in value:
                previous = re.sub(r'(?m)^    (?:' + re.escape(json.dumps(name)) + '|' + re.escape(name) + r'):[^\n]*\n(?:      [^\n]*\n)*', '', previous)
            replacement = '  nameserver-policy:\n' + previous + '\n'.join(yaml_block(value, 4)) + '\n'
        body = re.sub(pattern, lambda _: replacement, body, count=1) if existing else body + replacement
    return text[:match.start(1)] + body + text[match.end(1):]


def render(profiles, settings, yaml_block):
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
            if options.get('hosts'):
                section = re.search(r'(?ms)^hosts:\n(.*?)(?=^[a-z][a-z0-9-]*:|\Z)', text)
                body = section[1] if section else ''
                for name, address in options['hosts'].items():
                    pattern = r'(?ms)^  (?:' + re.escape(json.dumps(name)) + '|' + re.escape(name) + r'):[^\n]*\n(?:    [^\n]*\n)*'
                    body = re.sub(pattern, '', body)
                    body += '\n'.join(yaml_block({name: address}, 2)) + '\n'
                replacement = 'hosts:\n' + body
                text = text[:section.start()] + replacement + text[section.end():] if section else replacement + text
            header, marker, body = text.partition('rules:\n')
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
            for key, value in options.get('general', {}).items():
                text = re.sub(r'(?m)^' + re.escape(key) + r'\s*=.*\n?', '', text)
                text = text.replace('[General]\n', '[General]\n' + key + ' = ' + value + '\n', 1)
            header, marker, body = text.partition('[Rule]\n')
            lines = options.get('rules_prepend', [])
        if not marker:
            raise ValueError('Missing generated rules section')
        output[filename] = header + marker + ''.join(line + '\n' for line in lines if line not in body.splitlines()) + body
    return output
