import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import yaml
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'deployment'))
import distribute as d
import personal
import versions
sys.path.insert(0, str(ROOT / 'scripts'))
import build_services


def preferences():
    return {'schema_version': 1, 'defaults': {}, 'company_device': 'WORK_MAC', 'home_device': 'HOME_MAC',
            'home_router': '192.168.50.1', 'home_domains': ['home.arpa'], 'home_networks': ['192.168.50.0/24'],
            'company_rules': ['DOMAIN-SUFFIX,work.example'], 'force_proxy': ['DOMAIN,media.example'],
            'force_direct': ['DOMAIN,stun.example']}


def services(state):
    inputs = state / 'inputs'; inputs.mkdir()
    for name in personal.CATEGORIES:
        (inputs / (name + '.yaml')).write_text('payload:\n  - "+.' + name + '.example"\n  - "api.' + name + '.example"\n')
    output = state / 'service-build'
    manifest = build_services.build(output, 'a' * 40, inputs)
    target = state / 'service-rules' / manifest['content_digest']; target.parent.mkdir()
    output.rename(target)
    pointer = {'tag': 'services-fixture-' + manifest['content_digest'][:10], 'digest': manifest['content_digest']}
    (state / 'personal-services.json').write_text(json.dumps(pointer))
    return pointer


def fixture(state):
    digest = 'b' * 64
    root = state / 'rules/releases' / digest
    for client in ('surge', 'shadowrocket', 'mihomo'):
        (root / client).mkdir(parents=True)
    origin = 'https://raw.githubusercontent.com/mercer08/proxy-rules/release/'
    for client in ('surge', 'shadowrocket'):
        lines = ['[Rule]', 'RULE-SET,' + origin + client + '/lan.list,DIRECT']
        for name, policy in [('wan-com', 'PROXY'), ('futu-broker', 'PROXY'), ('ai', 'AI'), ('apple', 'APPLE'), ('proxy', 'PROXY'), ('direct', 'DIRECT')]:
            (root / client / (name + '.list')).write_text('DOMAIN-SUFFIX,' + name + '.example\n')
            lines.append('RULE-SET,' + origin + client + '/' + name + '.list,' + policy)
        lines.append('FINAL,PROXY')
        (root / client / 'rules.conf').write_text('\n'.join(lines) + '\n')
    providers = {name: {'type': 'http', 'behavior': 'classical', 'url': origin + 'mihomo/' + name + '.yaml', 'path': './rules/' + name + '.yaml', 'interval': 86400} for name in ('private', 'lan', 'wan-com', 'futu-broker', 'ai', 'apple', 'proxy', 'direct')}
    rules = ['RULE-SET,' + name + ',' + policy for name, policy in [('private', 'DIRECT'), ('lan', 'DIRECT'), ('wan-com', 'PROXY'), ('futu-broker', 'PROXY'), ('ai', 'AI'), ('apple', 'APPLE'), ('proxy', 'PROXY'), ('direct', 'DIRECT')]] + ['MATCH,PROXY']
    (root / 'mihomo/rules.yaml').write_text('\n'.join(d.yaml_block({'rule-providers': providers, 'rules': rules})) + '\n')
    (state / 'rules.json').write_text(json.dumps({'digest': digest, 'tag': 'rules-fixture-' + digest[:10]}))
    d.atomic_write(state / 'private-rules/lan-com.list', 'DOMAIN-SUFFIX,private.work.example\n')
    config = {'state_dir': str(state), 'templates_dir': str(ROOT / 'deployment/templates'), 'server': '203.0.113.1',
              'repository': 'mercer08/proxy-rules', 'rules_delivery': 'jsdelivr', 'public_url': 'https://203.0.113.1', '_rules_tag': 'rules-fixture-' + digest[:10]}
    node = {'name': 'dmit-lax', 'type': 'vmess', 'server': '203.0.113.1', 'port': 443, 'uuid': 'synthetic', 'alterId': 0,
            'cipher': 'aes-128-gcm', 'tls': True, 'skip-cert-verify': False, 'network': 'ws', 'udp': True,
            'ws-opts': {'path': '/test', 'headers': {'Host': '203.0.113.1'}}}
    converted = {'proxies': [node], 'Surge': 'dmit-lax = vmess,203.0.113.1,443,username=synthetic,tls=true', 'URI': 'vmess://synthetic'}
    return config, root, digest, node, converted


class PersonalTests(unittest.TestCase):
    def test_categories_build_from_one_commit_and_publish_no_policies(self):
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary); pointer = services(state)
            manifest = json.loads((state / 'service-rules' / pointer['digest'] / 'manifest.json').read_text())
            self.assertEqual(manifest['upstream']['commit'], 'a' * 40)
            self.assertEqual(set(manifest['counts']), set(personal.CATEGORIES))
            self.assertTrue(all(n == 2 for n in manifest['counts'].values()))
            self.assertNotIn('DEVICE:', (state / 'service-rules' / pointer['digest'] / 'google.list').read_text())

    def test_preferences_cannot_inject_rules_or_use_unsafe_paths(self):
        for changed in ({'defaults': {'AI': 'DEVICE:other'}}, {'company_device': 'WORK\n[Rule]'}, {'force_proxy': ['DOMAIN,test,DIRECT']}, {'unknown': 1}):
            with self.assertRaises(ValueError):
                personal.validate({**preferences(), **changed})
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary); file = state / 'outside.json'; file.write_text('{}')
            with self.assertRaises(ValueError):
                personal.settings_paths({'state_dir': str(state), 'personal_profiles': {'iphone': str(file)}})

    def test_four_apps_preserve_node_and_category_order_without_affecting_other_accounts(self):
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary); config, root, digest, node, converted = fixture(state)
            account = {'label': 'phone', 'nodes': [node], 'business_rules': True, 'final_policy': 'PROXY'}
            before = d.render_profiles(config, account, converted, '', root, digest)
            services(state); settings_file = state / 'personal-settings/phone.json'; d.atomic_write(settings_file, json.dumps(preferences()))
            config['personal_profiles'] = {'phone': str(settings_file)}
            after = d.render_profiles(config, account, converted, '', root, digest)
            self.assertEqual(before, after)  # Merely enabling infrastructure changes no legacy output.
            phone = d.render_profiles(config, {**account, 'personal': preferences()}, converted, '', root, digest)
            for name in ('node.txt', 'shadowrocket.txt'):
                self.assertEqual(before[name], phone[name])
            self.assertIn('HOME = subnet, default=DEVICE:HOME_MAC, ROUTER:192.168.50.1=DIRECT', phone['surge.conf'])
            self.assertIn('FINAL,FINAL,dns-failed', phone['surge.conf'])
            self.assertLess(phone['surge.conf'].index('private.work.example,COMPANY_LAN'), phone['surge.conf'].index('/lan.list,DIRECT'))
            self.assertLess(phone['surge.conf'].index('/ai.list,AI'), phone['surge.conf'].index('/google.list,GOOGLE'))
            self.assertLess(phone['surge.conf'].index('/youtube.list,YOUTUBE'), phone['surge.conf'].index('/google.list,GOOGLE'))
            for name in ('stash.yaml', 'mihomo.yaml'):
                parsed = yaml.safe_load(phone[name]); groups = {g['name']: g['proxies'] for g in parsed['proxy-groups']}
                self.assertEqual(groups['MICROSOFT'][0], 'DIRECT')
                self.assertEqual(groups['PAYPAL'][0], 'DIRECT')
                self.assertEqual(groups['FINAL'][0], 'PROXY')
                self.assertEqual(parsed['rules'][-1], 'MATCH,FINAL')
                self.assertLess(parsed['rules'].index('RULE-SET,ai,AI'), parsed['rules'].index('RULE-SET,svc-google,GOOGLE'))
                self.assertEqual(parsed['proxies'], [node])
                self.assertIn('svc-microsoft', parsed['rule-providers'])
                if name == 'stash.yaml':
                    self.assertTrue(all(p['type'] == 'http' for p in parsed['rule-providers'].values()))
                    self.assertFalse(any(k.startswith('rule-set:') for k in parsed['dns']['nameserver-policy']))
            self.assertNotIn('DEVICE:', phone['shadowrocket.conf'])
            self.assertNotIn('[MITM]', phone['surge.conf'])

    def test_version_backup_deduplicates_and_restores_only_selected_account(self):
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary); record = {'label': 'phone', 'files': {}}
            for name in versions.FILES:
                path = state / 'current/phone' / name; d.atomic_write(path, 'old-' + name); record['files'][name] = str(path)
            config = {'state_dir': str(state)}; identifier = 'a' * 24
            first = versions.backup(config, record, identifier, d.atomic_write)
            self.assertEqual(first, versions.backup(config, record, identifier, d.atomic_write))
            d.atomic_write(record['files']['surge.conf'], 'new')
            friend = state / 'profile-overrides' / ('b' * 24) / 'surge.conf'; d.atomic_write(friend, 'friend')
            versions.restore(config, record, identifier, first['version'], d.atomic_write, lambda: None)
            for name in versions.CONFIGS:
                self.assertEqual((state / 'profile-overrides' / identifier / name).read_text(), 'old-' + name)
            self.assertEqual(friend.read_text(), 'friend')
            self.assertEqual(len(versions.list_versions(config, identifier)), 2)
            self.assertEqual((versions.root(config, identifier) / first['version']).stat().st_mode & 0o777, 0o700)
            with zipfile.ZipFile(io.BytesIO(versions.package(config, identifier, first['version']))) as archive:
                self.assertEqual(archive.read('surge.conf'), b'old-surge.conf')
            d.atomic_write(record['files']['node.txt'], 'rotated-credentials')
            with self.assertRaises(ValueError):
                versions.restore(config, record, identifier, first['version'], d.atomic_write, lambda: None)
            with self.assertRaises(ValueError):
                versions.read_version(config, identifier, '../escape')

    def test_global_microsoft_paypal_preserve_every_other_setting_and_personal_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            state=Path(temporary);config,root,digest,node,converted=fixture(state)
            services(state)
            for business in (False,True):
                account={'label':'fixture','nodes':[node],'business_rules':business,'final_policy':'PROXY' if business else 'DIRECT'}
                before=d.render_profiles(config,account,converted,'',root,digest)
                enabled={**config,'global_service_groups':True}
                after=d.render_profiles(enabled,account,converted,'',root,digest)
                self.assertEqual(after,personal.render_global_services(after,enabled,d.yaml_block))
                for name in ('node.txt','shadowrocket.txt'):
                    self.assertEqual(before[name],after[name])
                for name in ('surge.conf','shadowrocket.conf'):
                    self.assertIn('MICROSOFT = select, DIRECT, PROXY',after[name])
                    self.assertIn('PAYPAL = select, DIRECT, PROXY',after[name])
                    cleaned='\n'.join(l for l in after[name].splitlines() if not l.startswith(('MICROSOFT =','PAYPAL =')) and not (l.startswith('RULE-SET,') and ('/microsoft.list,' in l or '/paypal.list,' in l)))+'\n'
                    self.assertEqual(before[name],cleaned)
                for name in ('mihomo.yaml','stash.yaml'):
                    old=yaml.safe_load(before[name]);new=yaml.safe_load(after[name])
                    groups={g['name']:g for g in new['proxy-groups']}
                    self.assertEqual(groups['MICROSOFT']['proxies'],['DIRECT','PROXY'])
                    self.assertEqual(groups['PAYPAL']['proxies'],['DIRECT','PROXY'])
                    new['proxy-groups']=[g for g in new['proxy-groups'] if g['name'] not in ('MICROSOFT','PAYPAL')]
                    for n in ('microsoft','paypal'):
                        new['rule-providers'].pop('svc-'+n)
                        new['rules'].remove('RULE-SET,svc-'+n+','+n.upper())
                        if name=='mihomo.yaml':new['dns']['nameserver-policy'].pop('rule-set:svc-'+n)
                    self.assertEqual(old,new)
                personal_account={**account,'personal':preferences()}
                personal_config={**config,'personal_profiles':{'fixture':str(state/'personal-settings/fixture.json')}}
                self.assertEqual(d.render_profiles(personal_config,personal_account,converted,'',root,digest),d.render_profiles({**personal_config,'global_service_groups':True},personal_account,converted,'',root,digest))

    def test_failed_restore_keeps_existing_override_and_detects_corrupt_backups(self):
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary); record = {'label': 'phone', 'files': {}}
            for name in versions.FILES:
                path = state / 'current' / name; d.atomic_write(path, name); record['files'][name] = str(path)
            config = {'state_dir': str(state)}; identifier = 'a' * 24
            m = versions.backup(config, record, identifier, d.atomic_write)
            override = state / 'profile-overrides' / identifier / 'surge.conf'; d.atomic_write(override, 'existing')
            def fail(): raise RuntimeError('fixture')
            with self.assertRaises(RuntimeError):
                versions.restore(config, record, identifier, m['version'], d.atomic_write, fail)
            self.assertEqual(override.read_text(), 'existing')
            self.assertFalse((override.parent / 'stash.yaml').exists())
            (versions.root(config, identifier) / m['version'] / 'surge.conf').write_text('tampered')
            with self.assertRaises(ValueError):
                versions.package(config, identifier, m['version'])
            replacement = versions.backup(config, record, identifier, d.atomic_write)
            self.assertNotEqual(replacement['version'], m['version'])
            self.assertEqual(versions.read_version(config, identifier, replacement['version'])[1]['surge.conf'], b'surge.conf')
