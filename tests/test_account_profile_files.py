import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'deployment'))
import console as c
import distribute as d


class AccountProfileFileTests(unittest.TestCase):
    def test_scoped_selection_excludes_other_apps_and_overrides(self):
        profiles = {name: 'synthetic-' + name for name in d.PROFILE_FILES}
        config = {'account_profile_files': {'a' * 24: ['mihomo.yaml']}}
        self.assertEqual(d.account_profile_outputs(profiles, config, 'a' * 24), {'mihomo.yaml': profiles['mihomo.yaml']})
        self.assertEqual(d.account_profile_outputs(profiles, config, 'b' * 24), profiles)
        self.assertEqual(len(profiles), 6)

    def test_invalid_selection_fails_before_publication(self):
        profiles = {name: '' for name in d.PROFILE_FILES}
        for names in ([], ['../secret'], ['mihomo.yaml', 'mihomo.yaml'], 'mihomo.yaml', [{}]):
            with self.assertRaises(ValueError):
                d.account_profile_outputs(profiles, {'account_profile_files': {'a' * 24: names}}, 'a' * 24)

    def test_single_file_console_identity_edit_access_and_download(self):
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary); identifier = 'a' * 24
            generation = state / 'profiles/generations/test' / identifier
            generation.mkdir(parents=True)
            (generation / 'mihomo.yaml').write_text('mode: rule\n')
            (state / 'profiles/current').symlink_to(generation.parent)
            record = {'label': 'router', 'business_rules': True, 'nodes': ['synthetic'],
                      'files': {'mihomo.yaml': str(state / 'profiles/current' / identifier / 'mihomo.yaml')}}
            (state / 'profiles.json').write_text(json.dumps({'accounts': [record]}))
            app = c.Console({'state_dir': str(state)}, state)
            self.assertEqual(app.list_accounts()[0]['files'], ['mihomo.yaml'])
            self.assertEqual(app.file(identifier, 'mihomo.yaml')['content'], 'mode: rule\n')
            with self.assertRaises(c.ConsoleError) as error:
                app.file(identifier, 'surge.conf')
            self.assertEqual(error.exception.status, 404)
            data, _ = app.package(identifier)
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                self.assertEqual(set(archive.namelist()), {'mihomo.yaml', 'README.txt'})


if __name__ == '__main__':
    unittest.main()
