"""Synthetic offline fixtures only; never use production credentials in UI tests."""
import json
from pathlib import Path
import sys
import tempfile

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE))
import console as c

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
accounts = {name: {'label': label, 'nodes': [{'name': 'DMIT-Native'}], 'business_rules': False}
            for name, label in (('owner', '我的电脑'), ('friend', '演示账号'))}
c.d.load_accounts = lambda config: accounts
c.d.verify_cdn = lambda *args: 0
def converted(config, key, nodes):
    return {'proxies': [{'name': 'DMIT-Native', 'type': 'vmess', 'server': '203.0.113.1', 'port': 443, 'uuid': 'synthetic-' + key, 'tls': True}],
            'Surge': 'DMIT-Native=vmess,203.0.113.1,443,username=synthetic-' + key + ',tls=true',
            'URI': 'vmess://c3ludGhldGljLXRlc3Qtb25seQ=='}
c.d.substore = converted
c.d.generate(config)
c.serve(config, BASE / 'console/dist', 8766).serve_forever()
