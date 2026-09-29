"""Private, explicitly account-scoped preferences and independent public services."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import tempfile

CATEGORIES = ('microsoft', 'paypal', 'google', 'github', 'youtube', 'netflix', 'telegram', 'steam')
PUBLIC_GROUPS = ('AI', 'APPLE', 'MICROSOFT', 'PAYPAL', 'GOOGLE', 'GITHUB', 'TELEGRAM', 'YOUTUBE', 'NETFLIX', 'STEAM', 'COMPANY_WAN', 'BROKER', 'FINAL')
DEFAULTS = {g: ('DIRECT' if g in ('APPLE', 'MICROSOFT', 'PAYPAL') else 'PROXY') for g in PUBLIC_GROUPS}


def validate(settings):
    if not isinstance(settings, dict) or settings.get('schema_version') != 1:
        raise ValueError('Personal settings schema_version must be 1')
    if set(settings) - {'schema_version', 'defaults', 'company_device', 'home_device', 'home_router', 'home_domains', 'home_networks', 'company_rules', 'force_proxy', 'force_direct'}:
        raise ValueError('Unknown personal setting')
    defaults = settings.get('defaults', {})
    if not isinstance(defaults, dict) or set(defaults) - set(PUBLIC_GROUPS) or any(v not in ('PROXY', 'DIRECT') for v in defaults.values()):
        raise ValueError('Invalid group defaults')
    for name in ('company_device', 'home_device'):
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', settings.get(name, '')):
            raise ValueError('Invalid Ponte device name')
    if ipaddress.ip_address(settings.get('home_router', '')).version != 4:
        raise ValueError('IPv4 home router required')
    for key in ('home_domains', 'home_networks'):
        if not isinstance(settings.get(key, []), list) or len(settings.get(key, [])) > 100:
            raise ValueError('Invalid private network list')
    for net in settings.get('home_networks', []):
        ipaddress.ip_network(net, strict=True)
    for domain in settings.get('home_domains', []):
        domain_rule('DOMAIN-SUFFIX,' + domain)
    for key in ('company_rules', 'force_proxy', 'force_direct'):
        rules = settings.get(key, [])
        if not isinstance(rules, list) or len(rules) > 1000:
            raise ValueError('Invalid personal rule list')
        for rule in rules:
            domain_rule(rule)
    return settings


def domain_rule(rule):
    if not isinstance(rule, str) or not re.fullmatch(r'(DOMAIN|DOMAIN-SUFFIX|DOMAIN-KEYWORD),[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*', rule):
        raise ValueError('Invalid personal domain rule')
    return rule


def settings_paths(config):
    mappings = config.get('personal_profiles', {})
    if not isinstance(mappings, dict):
        raise ValueError('personal_profiles must be a mapping')
    result = {}
    for email, filename in mappings.items():
        path = Path(filename)
        allowed = (Path(config['state_dir']) / 'personal-settings').resolve()
        if path.is_symlink() or not path.resolve().is_relative_to(allowed) or not path.is_file():
            raise ValueError('Personal settings must be a private regular file')
        result[email] = path
    return result


def inputs(config):
    return {email: validate(json.loads(path.read_text())) for email, path in settings_paths(config).items()}


def mirror_services(config, fetch, atomic_write):
    if not config.get('personal_profiles'):
        return
    state = Path(config['state_dir'])
    repo = config['repository']
    pointer = json.loads(fetch('https://raw.githubusercontent.com/' + repo + '/services/release.json'))
    tag, digest = pointer['tag'], pointer['digest']
    if not re.fullmatch(r'[a-f0-9]{64}', digest) or not re.fullmatch(r'services-[A-Za-z0-9-]+-' + digest[:10], tag):
        raise ValueError('Invalid service version')
    index = state / 'personal-services.json'
    if index.exists() and json.loads(index.read_text()) == pointer:
        return
    origin = 'https://cdn.jsdelivr.net/gh/' + repo + '@' + tag + '/'
    manifest_raw = fetch(origin + 'manifest.json')
    manifest = json.loads(manifest_raw)
    hashes = manifest['sha256']
    required = {name + ext for name in CATEGORIES for ext in ('.list', '.yaml')} | {'NOTICE.md', 'LICENSE'}
    if manifest.get('schema_version') != 1 or set(hashes) != required or manifest.get('content_digest') != digest or hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest() != digest:
        raise ValueError('Invalid service manifest')
    parent = state / 'service-rules'
    parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    destination = parent / digest
    if not destination.exists():
        with tempfile.TemporaryDirectory(dir=parent) as temporary:
            staging = Path(temporary)
            def download(name):
                body = fetch(origin + name)
                if hashlib.sha256(body).hexdigest() != hashes[name]:
                    raise ValueError('Service checksum mismatch')
                if name.endswith('.list'):
                    for line in body.decode().splitlines():
                        domain_rule(line)
                atomic_write(staging / name, body)
            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(download, sorted(hashes)))
            atomic_write(staging / 'manifest.json', manifest_raw)
            os.rename(staging, destination)
            staging.mkdir()
    atomic_write(index, json.dumps(pointer) + '\n')


def service_state(config):
    if not config.get('personal_profiles'):
        return None
    pointer = json.loads((Path(config['state_dir']) / 'personal-services.json').read_text())
    digest, tag = pointer['digest'], pointer['tag']
    if not re.fullmatch(r'[a-f0-9]{64}', digest) or not re.fullmatch(r'services-[A-Za-z0-9-]+-' + digest[:10], tag):
        raise ValueError('Invalid cached service version')
    folder = Path(config['state_dir']) / 'service-rules' / digest
    manifest = json.loads((folder / 'manifest.json').read_text())
    if manifest.get('content_digest') != digest or hashlib.sha256(json.dumps(manifest['sha256'], sort_keys=True).encode()).hexdigest() != digest:
        raise ValueError('Cached service manifest mismatch')
    for name, expected in manifest['sha256'].items():
        if Path(name).name != name or hashlib.sha256((folder / name).read_bytes()).hexdigest() != expected:
            raise ValueError('Cached service checksum mismatch')
    return pointer


def choices(settings, group):
    first = settings.get('defaults', {}).get(group, DEFAULTS[group])
    return [first, 'DIRECT' if first == 'PROXY' else 'PROXY']


def domain_patterns(rules):
    return [('+' + '.' if r.startswith('DOMAIN-SUFFIX,') else '') + r.split(',')[1] for r in rules if not r.startswith('DOMAIN-KEYWORD,')]


def prefix_rules(settings, private, client):
    # Explicit domain exits precede every local DNS/IP classification.
    rules = [r + ',PROXY' for r in settings.get('force_proxy', [])]
    rules += [r + ',DIRECT' for r in settings.get('force_direct', [])]
    rules += ['DOMAIN-SUFFIX,' + d + ',HOME' for d in settings.get('home_domains', [])]
    rules += [r + ',COMPANY_LAN' for r in dict.fromkeys(settings.get('company_rules', []) + private)]
    rules += [('IP-CIDR6' if ':' in n else 'IP-CIDR') + ',' + n + ',HOME,no-resolve' for n in settings.get('home_networks', [])]
    return rules


def render(profiles, config, account, private, yaml_block):
    settings = account.get('personal')
    if not settings:
        return profiles
    validate(settings)
    pointer = service_state(config)
    origin = 'https://cdn.jsdelivr.net/gh/' + config['repository'] + '@' + pointer['tag'] + '/'
    output = dict(profiles)
    for filename in ('surge.conf', 'shadowrocket.conf'):
        client = 'surge' if filename == 'surge.conf' else 'shadowrocket'
        header, body = profiles[filename].split('[Rule]\n', 1)
        general, rest = header.split('[Proxy]\n', 1)
        nodes, _ = rest.split('[Proxy Group]\n', 1)
        general = re.sub(r'(?m)^dns-server\s*=.*$', 'dns-server = system', general)
        if client == 'surge':
            general = general.rstrip() + '\nencrypted-dns-server = https://dns.alidns.com/dns-query, https://doh.pub/dns-query\nhijack-dns = *:53\n'
        groups = ['PROXY = select, ' + ', '.join(p['name'] for p in account['nodes'])]
        for group in PUBLIC_GROUPS:
            options = choices(settings, group)
            groups.append(group + ' = select, ' + ', '.join(options) + (', policy-select-name=' + options[0] if client == 'shadowrocket' else ''))
        if client == 'surge':
            groups += ['COMPANY_LAN = select, DEVICE:' + settings['company_device'] + ', DIRECT',
                       'HOME = subnet, default=DEVICE:' + settings['home_device'] + ', ROUTER:' + settings['home_router'] + '=DIRECT']
        else:
            groups += ['# Local LAN access only. Surge Ponte requires Surge or a separately configured remote tunnel.',
                       'COMPANY_LAN = select, DIRECT, REJECT, policy-select-name=DIRECT', 'HOME = select, DIRECT, REJECT, policy-select-name=DIRECT']
        lines = body.splitlines()
        lines = [l for l in lines if not (l.startswith('# Private rule set:') or any(l == r + ',DIRECT' for r in private))]
        lines = [l.replace('/wan-com.list,PROXY', '/wan-com.list,COMPANY_WAN').replace('/futu-broker.list,PROXY', '/futu-broker.list,BROKER').replace('/telegram.list,PROXY', '/telegram.list,TELEGRAM') for l in lines]
        services = ['RULE-SET,' + origin + name + '.list,' + name.upper() + ',update-interval=86400' for name in ('microsoft', 'paypal', 'github', 'telegram', 'youtube', 'netflix', 'steam', 'google')]
        index = next((i for i, l in enumerate(lines) if '/proxy.' in l), len(lines) - 1)
        lines[index:index] = services
        lines = prefix_rules(settings, private, client) + lines
        lines = ['FINAL,FINAL,dns-failed' if client == 'surge' and l == 'FINAL,FINAL' else l for l in lines]
        result = '# Personal service profile; public CDN rules + private device preferences.\n' + general.rstrip() + '\n\n[Proxy]\n' + nodes.rstrip() + '\n\n[Proxy Group]\n' + '\n'.join(groups) + '\n\n[Rule]\n' + '\n'.join(lines).strip() + '\n'
        if client == 'surge':
            result += '\n[SSID Setting]\nROUTER:' + settings['home_router'] + ' dns-server="' + settings['home_router'] + '", encrypted-dns-server="off"\n'
        output[filename] = result
    for filename in ('mihomo.yaml', 'stash.yaml'):
        text = profiles[filename]
        client = 'mihomo' if filename == 'mihomo.yaml' else 'stash'
        groups = [{'name': 'PROXY', 'type': 'select', 'proxies': [n['name'] for n in account['nodes']]}]
        groups += [{'name': g, 'type': 'select', 'proxies': choices(settings, g)} for g in PUBLIC_GROUPS]
        groups += [{'name': g, 'type': 'select', 'proxies': ['DIRECT', 'REJECT']} for g in ('COMPANY_LAN', 'HOME')]
        text = re.sub(r'(?ms)^proxy-groups:\n.*?(?=^[a-z][a-z0-9-]*:|\Z)', lambda m: '\n'.join(yaml_block({'proxy-groups': groups})) + '\n', text, count=1)
        # System resolution for private networks; public services follow direct/proxy intent.
        policies = {}
        # Mihomo reuses the existing private providers instead of duplicating their domains.
        all_private = settings.get('company_rules', []) + ([] if client == 'mihomo' else private) + ['DOMAIN-SUFFIX,' + d for d in settings.get('home_domains', [])]
        patterns = list(dict.fromkeys(['localhost', '+.local', '+.lan'] + domain_patterns(all_private)))
        for pattern in patterns:
            policies[pattern] = 'system'
        if client == 'mihomo':
            policies.update({'rule-set:private': ['system'], 'rule-set:lan-com': ['system']})
            for name in ('ai', 'apple', 'wan-com', 'futu-broker', *CATEGORIES, 'proxy', 'direct'):
                group = {'wan-com': 'COMPANY_WAN', 'futu-broker': 'BROKER', 'proxy': 'PROXY', 'direct': 'DIRECT'}.get(name, name.upper())
                direct = group == 'DIRECT' or group in ('APPLE', 'MICROSOFT', 'PAYPAL')
                policies['rule-set:svc-' + name if name in CATEGORIES else 'rule-set:' + name] = ['https://dns.alidns.com/dns-query#' + group if direct and group != 'DIRECT' else 'https://dns.alidns.com/dns-query' if direct else 'https://1.1.1.1/dns-query#' + group]
            dns = {'enable': True, 'ipv6': False, 'enhanced-mode': 'fake-ip', 'fake-ip-range': '198.18.0.1/16',
                   'fake-ip-filter': patterns + ['rule-set:private', 'rule-set:lan-com'], 'default-nameserver': ['223.5.5.5', '119.29.29.29'],
                   'proxy-server-nameserver': ['https://dns.alidns.com/dns-query'],
                   'nameserver': ['https://1.1.1.1/dns-query#FINAL'], 'nameserver-policy': policies,
                   'direct-nameserver': ['https://dns.alidns.com/dns-query'], 'direct-nameserver-follow-policy': True}
        else:
            dns = {'nameserver': ['https://dns.alidns.com/dns-query', 'https://doh.pub/dns-query'],
                   'nameserver-policy': policies, 'fake-ip-filter': patterns}
        text = re.sub(r'(?ms)^dns:\n.*?(?=^[a-z][a-z0-9-]*:|\Z)', lambda m: '\n'.join(yaml_block({'dns': dns})) + '\n', text, count=1)
        providers = {('svc-' + n): {'type': 'http', 'behavior': 'classical', 'url': origin + n + '.yaml',
                                    'path': './rules/services-' + n + '.yaml', 'interval': 86400} for n in CATEGORIES}
        marker = text.index('rules:\n')
        # A complete mapping needs to merge under the existing provider key, not duplicate it.
        text = text[:marker] + '\n'.join(yaml_block(providers, 2)) + '\n' + text[marker:]
        header, body = text.split('rules:\n', 1)
        lines = body.splitlines()
        lines = [l for l in lines if not any(l.strip() == '- ' + json.dumps(r + ',DIRECT') for r in private)]
        lines = [l.replace('RULE-SET,lan-com,DIRECT', 'RULE-SET,lan-com,COMPANY_LAN').replace('RULE-SET,wan-com,PROXY', 'RULE-SET,wan-com,COMPANY_WAN').replace('RULE-SET,futu-broker,PROXY', 'RULE-SET,futu-broker,BROKER').replace('RULE-SET,telegram,PROXY', 'RULE-SET,telegram,TELEGRAM') for l in lines]
        index = next((i for i, l in enumerate(lines) if 'RULE-SET,proxy,' in l), len(lines) - 1)
        lines[index:index] = ['  - ' + json.dumps('RULE-SET,svc-' + n + ',' + n.upper()) for n in ('microsoft', 'paypal', 'github', 'telegram', 'youtube', 'netflix', 'steam', 'google')]
        lines = ['  - ' + json.dumps(r) for r in prefix_rules(settings, private, client)] + lines
        output[filename] = '# Personal profile. HOME/COMPANY_LAN are local only; remote access needs a separately configured tunnel.\n' + header + 'rules:\n' + '\n'.join(lines).strip('\n') + '\n'
    return output
