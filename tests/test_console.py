import contextlib
import hashlib
import http.client
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'deployment'))
import console as c
from test_personal import preferences


class ConsoleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.state = Path(self.temp.name)
        self.identifier = 'a' * 24
        self.other = 'b' * 24
        self.records = []
        for identifier, label in ((self.identifier, 'owner'), (self.other, 'friend')):
            folder = self.state / 'profiles/generations/test' / identifier
            folder.mkdir(parents=True)
            files = {}
            for name in c.d.PROFILE_FILES:
                (folder / name).write_text('[Rule]\nFINAL,PROXY\n' + label)
                files[name] = str(self.state / 'profiles/current' / identifier / name)
            self.records.append({'label': label, 'business_rules': label == 'owner', 'nodes': ['DMIT-Native'], 'files': files, 'edited': []})
        (self.state / 'profiles/current').symlink_to(self.state / 'profiles/generations/test')
        (self.state / 'profiles.json').write_text(json.dumps({'accounts': self.records}))
        self.assets = self.state / 'assets'
        self.assets.mkdir()
        (self.assets / 'index.html').write_text('<html>test</html>')
        c.d.atomic_write(self.state / 'private-rules/lan-com.list', 'DOMAIN-SUFFIX,internal.business.test\n')
        self.server = c.serve({'state_dir': str(self.state)}, self.assets, 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, path, method='GET', body=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.port)
        values = {'Content-Type': 'application/json', **(headers or {})}
        connection.request(method, path, json.dumps(body) if body is not None else None, values)
        response = connection.getresponse()
        result = response.status, response.read(), dict(response.getheaders())
        connection.close()
        return result

    def test_loopback_only_origin_guards_and_no_cache(self):
        self.assertEqual(self.server.server_address[0], '127.0.0.1')
        status, body, headers = self.request('/api/accounts')
        self.assertEqual(status, 200)
        self.assertEqual(len(json.loads(body)['accounts']), 2)
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertEqual(headers['X-Frame-Options'], 'DENY')
        for values in ({'Host': 'public.example'}, {'Origin': 'https://evil.example'}, {'Sec-Fetch-Site': 'cross-site'}):
            self.assertEqual(self.request('/api/accounts', headers=values)[0], 403)
        self.assertEqual(self.request('/../profiles.json')[0], 404)
        self.assertEqual(self.request('/api/accounts/' + self.identifier + '/files/profiles.json')[0], 404)

    def test_account_package_is_scoped_and_unknown_account_is_rejected(self):
        status, body, _ = self.request('/api/accounts/' + self.other + '/download')
        self.assertEqual(status, 200)
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            self.assertEqual(len(archive.namelist()), 7)
            self.assertIn('friend', archive.read('surge.conf').decode())
            self.assertNotIn('owner', archive.read('surge.conf').decode())
        self.assertEqual(self.request('/api/accounts/' + 'c' * 24 + '/download')[0], 404)

    def test_external_link_can_open_homepage_without_allowing_cross_site_api_access(self):
        navigation = {'Sec-Fetch-Site': 'cross-site', 'Sec-Fetch-Mode': 'navigate',
                      'Sec-Fetch-Dest': 'document', 'Sec-Fetch-User': '?1'}
        for path in ('/', '/index.html'):
            status, body, headers = self.request(path, headers=navigation)
            self.assertEqual(status, 200)
            self.assertIn(b'<html>', body)
            self.assertEqual(headers['X-Frame-Options'], 'DENY')
        for path in ('/api/accounts', '/api/accounts/' + self.identifier + '/download',
                     '/api/accounts/' + self.identifier + '/files/surge.conf'):
            self.assertEqual(self.request(path, headers=navigation)[0], 403)
        for changed in ({'Sec-Fetch-Dest': 'iframe'}, {'Sec-Fetch-Mode': 'cors'},
                        {'Sec-Fetch-User': '?0'}, {'Origin': 'https://evil.example'},
                        {'Host': 'public.example'}):
            self.assertEqual(self.request('/', headers={**navigation, **changed})[0], 403)
        self.assertEqual(self.request('/', headers={'Sec-Fetch-Site': 'cross-site'})[0], 403)
        self.assertEqual(self.request('/api/refresh', 'POST', {}, navigation)[0], 403)
        self.assertEqual(self.request('/', 'POST', {}, navigation)[0], 403)

    def test_edit_conflict_private_persistence_reset_and_failed_generation_rollback(self):
        app = self.server.console
        path = '/api/accounts/' + self.identifier + '/files/surge.conf'
        original = json.loads(self.request(path)[1])
        with patch.object(app, 'regenerate') as regenerate:
            self.assertEqual(self.request(path, 'PUT', {'content': 'edit', 'etag': 'stale'})[0], 409)
            self.assertEqual(self.request(path, 'PUT', {'content': '#!MANAGED-CONFIG https://example.com', 'etag': original['etag']})[0], 400)
            self.assertEqual(self.request(path, 'PUT', {'content': 'edit', 'etag': original['etag']})[0], 200)
            regenerate.assert_called_once()
        override = self.state / 'profile-overrides' / self.identifier / 'surge.conf'
        self.assertEqual(override.read_text(), 'edit')
        self.assertEqual(override.stat().st_mode & 0o777, 0o600)
        self.assertEqual(override.parent.stat().st_mode & 0o777, 0o700)
        with patch.object(app, 'regenerate', side_effect=RuntimeError('do not expose payload')):
            status, body, _ = self.request(path, 'PUT', {'content': 'bad', 'etag': original['etag']})
            self.assertEqual(status, 503)
            self.assertNotIn(b'payload', body)
            self.assertEqual(override.read_text(), 'edit')
        with patch.object(app, 'regenerate'):
            self.assertEqual(self.request(path, 'DELETE', {'etag': original['etag']})[0], 200)
        self.assertFalse(override.exists())

    def test_private_lan_validation_conflicts_rollback_and_guards(self):
        path = '/api/private-rules/lan-com'
        status, body, headers = self.request(path)
        self.assertEqual(status, 200)
        self.assertEqual(headers['Cache-Control'], 'no-store')
        original = json.loads(body)
        app = self.server.console
        changed = 'DOMAIN,second.internal.test\n'
        with patch.object(app, 'regenerate') as regenerate:
            self.assertEqual(self.request(path, 'PUT', {'content': changed, 'etag': 'stale'})[0], 409)
            for invalid in ('DOMAIN,test,DIRECT', 'RULE-SET,https://example.com', 'DOMAIN,test\x00'):
                self.assertEqual(self.request(path, 'PUT', {'content': invalid, 'etag': original['etag']})[0], 400)
            self.assertEqual(self.request(path, 'PUT', {'content': changed, 'etag': original['etag']})[0], 200)
            regenerate.assert_called_once()
        private = c.d.private_lan_path(app.config)
        self.assertEqual(private.stat().st_mode & 0o777, 0o600)
        self.assertEqual(private.read_text(), changed)
        current = json.loads(self.request(path)[1])
        with patch.object(app, 'regenerate', side_effect=RuntimeError('secret')):
            status, body, _ = self.request(path, 'PUT', {'content': original['content'], 'etag': current['etag']})
            self.assertEqual(status, 503)
            self.assertNotIn(b'secret', body)
            self.assertEqual(private.read_text(), changed)
        self.assertEqual(self.request(path, headers={'Origin': 'https://evil.example'})[0], 403)
        self.assertEqual(self.request(path, 'DELETE', {'etag': current['etag']})[0], 405)

    def test_personal_settings_and_versions_are_scoped_and_restore_conflicts_are_checked(self):
        path = self.state / 'personal-settings/phone.json'
        c.d.atomic_write(path, json.dumps(preferences()))
        self.records[0]['personal_path'] = str(path)
        self.server.console.config['personal_profiles'] = {'phone': str(path)}
        (self.state / 'profiles.json').write_text(json.dumps({'accounts': self.records}))
        prefix = '/api/accounts/' + self.identifier
        original = json.loads(self.request(prefix + '/personal')[1])
        friend_before = {n: Path(p).read_bytes() for n, p in self.records[1]['files'].items()}
        changed = preferences(); changed['defaults']['MICROSOFT'] = 'PROXY'
        with patch.object(self.server.console, 'regenerate'):
            self.assertEqual(self.request(prefix + '/personal', 'PUT', {'content': json.dumps(changed), 'etag': 'stale'})[0], 409)
            self.assertEqual(self.request(prefix + '/personal', 'PUT', {'content': json.dumps(changed), 'etag': original['etag']})[0], 200)
        self.assertEqual(json.loads(path.read_text())['defaults']['MICROSOFT'], 'PROXY')
        listing = json.loads(self.request(prefix + '/versions')[1]); self.assertEqual(len(listing['versions']), 1)
        version = listing['versions'][0]['version']
        download = self.request(prefix + '/versions/' + version + '/download')
        self.assertEqual(download[0], 200)
        with zipfile.ZipFile(io.BytesIO(download[1])) as archive:
            self.assertEqual(archive.read('surge.conf'), Path(self.records[0]['files']['surge.conf']).read_bytes())
        c.d.atomic_write(self.records[0]['files']['stash.yaml'], 'changed-in-another-tab')
        restore = prefix + '/versions/' + version + '/restore'
        self.assertEqual(self.request(restore, 'POST', {'etag': listing['etag']})[0], 409)
        listing = json.loads(self.request(prefix + '/versions')[1])
        with patch.object(self.server.console, 'regenerate'):
            self.assertEqual(self.request(restore, 'POST', {'etag': listing['etag']})[0], 200)
        self.assertEqual((self.state / 'profile-overrides' / self.identifier / 'stash.yaml').read_text(), '[Rule]\nFINAL,PROXY\nowner')
        for name, body in friend_before.items():
            self.assertEqual(Path(self.records[1]['files'][name]).read_bytes(), body)
        self.assertEqual(self.request('/api/accounts/' + self.other + '/personal')[0], 404)
        self.assertEqual(self.request('/api/accounts/' + self.other + '/versions')[0], 404)
