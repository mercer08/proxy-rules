"""Synthetic offline fixtures only; never use production credentials in UI tests."""
import json
from pathlib import Path
import sys
import tempfile

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE))
import console as c
sys.path.insert(0, str(BASE.parent / 'scripts'))
import build_services

temporary = tempfile.TemporaryDirectory(prefix='private-console-test-')
state = Path(temporary.name)
digest = 'b' * 64
rules = state / 'rules/releases' / digest
for client in ('surge', 'shadowrocket', 'mihomo'):
    directory = rules / client
    directory.mkdir(parents=True)
    (directory / ('rules.yaml' if client == 'mihomo' else 'rules.conf')).write_text(
        'rule-providers:\nrules:\n  - "MATCH,PROXY"\n' if client == 'mihomo' else '[Rule]\nDOMAIN-SUFFIX,example.com,DIRECT\nFINAL,PROXY\n')
(state / 'rules.json').write_text(json.dumps({'digest': digest, 'tag': 'rules-now-' + digest[:10]}))
config = {'state_dir': str(state), 'templates_dir': str(BASE / 'templates'), 'repository': 'mercer08/proxy-rules',
          'rules_delivery': 'jsdelivr', 'public_url': 'https://203.0.113.1', 'server': '203.0.113.1'}
accounts = {name: {'label': label, 'nodes': [{'name': 'dmit-lax' if name == 'owner' else 'dmit-fixture-friend'}], 'business_rules': name == 'owner'}
            for name, label in (('owner', '我的电脑'), ('friend', '演示账号'))}
personal_path = state / 'personal-settings/phone.json'
preferences = {'schema_version': 1, 'defaults': {}, 'company_device': 'WORK_MAC', 'home_device': 'HOME_MAC', 'home_router': '192.168.50.1',
               'home_domains': ['home.arpa'], 'home_networks': ['192.168.50.0/24'], 'company_rules': [], 'force_proxy': [], 'force_direct': []}
c.d.atomic_write(personal_path, json.dumps(preferences, indent=2))
config['personal_profiles'] = {'phone': str(personal_path)}
service_inputs = state / 'inputs'; service_inputs.mkdir()
for name in c.d.personal.CATEGORIES:
    (service_inputs / (name + '.yaml')).write_text('payload:\n  - "+.' + name + '.example"\n  - "api.' + name + '.example"\n')
service_output = state / 'service-build'
manifest = build_services.build(service_output, 'a' * 40, service_inputs)
service_target = state / 'service-rules' / manifest['content_digest']; service_target.parent.mkdir()
service_output.rename(service_target)
c.d.atomic_write(state / 'personal-services.json', json.dumps({'tag': 'services-fixture-' + manifest['content_digest'][:10], 'digest': manifest['content_digest']}))
def load_accounts(config):
    return {**accounts, 'phone': {'label': '我的 iPhone', 'nodes': [{'name': 'dmit-lax'}], 'business_rules': True,
            'personal': json.loads(personal_path.read_text()), 'personal_path': str(personal_path),
            'final_policy': c.d.personal.choices(json.loads(personal_path.read_text()), 'FINAL')[0]}}
c.d.load_accounts = load_accounts
c.d.verify_cdn = lambda *args: 0
def converted(config, key, nodes):
    name = nodes[0]['name']
    return {'proxies': [{'name': name, 'type': 'vmess', 'server': '203.0.113.1', 'port': 443, 'uuid': 'synthetic-' + key, 'tls': True,
                         'alterId': 0, 'cipher': 'aes-128-gcm', 'network': 'ws', 'udp': True, 'skip-cert-verify': False,
                         'ws-opts': {'path': '/synthetic-ws', 'headers': {'Host': '203.0.113.1'}}}],
            'Surge': name + '=vmess,203.0.113.1,443,username=synthetic-' + key + ',tls=true',
            'URI': 'vmess://c3ludGhldGljLXRlc3Qtb25seQ=='}
c.d.substore = converted
c.d.atomic_write(state / 'private-rules/lan-com.list', 'DOMAIN-SUFFIX,internal.business.test\n')
c.d.generate(config)
c.serve(config, BASE / 'console/dist', 8766).serve_forever()
