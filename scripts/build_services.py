#!/usr/bin/env python3
"""Publishable domain-only service categories, independent of base rule releases."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
from build import fetch, parse_upstream

REPOSITORY = 'MetaCubeX/meta-rules-dat'
CATEGORIES = ('microsoft', 'paypal', 'google', 'github', 'youtube', 'netflix', 'telegram', 'steam')


def build(output, commit=None, input_dir=None):
    if commit is None:
        commit = json.loads(fetch('https://api.github.com/repos/' + REPOSITORY + '/commits/meta', os.getenv('GITHUB_TOKEN')))['sha']
    if not re.fullmatch('[a-f0-9]{40}', commit):
        raise ValueError('Immutable upstream commit required')
    output.mkdir(parents=True, exist_ok=True)
    def category(name):
        filename = 'geo/geosite/' + name + '.yaml'
        raw = (input_dir / (name + '.yaml')).read_bytes() if input_dir else fetch('https://raw.githubusercontent.com/' + REPOSITORY + '/' + commit + '/' + filename)
        rules = sorted(parse_upstream(raw.decode(), 'domain'))
        if len(rules) < 2:
            raise ValueError('Insufficient service coverage: ' + name)
        return name, raw, rules
    counts, inputs = {}, {}
    for name, raw, rules in ThreadPoolExecutor(max_workers=4).map(category, CATEGORIES):
        counts[name] = len(rules)
        inputs[name] = hashlib.sha256(raw).hexdigest()
        for suffix, content in [('list', '\n'.join(','.join(r) for r in rules) + '\n'),
                                ('yaml', 'payload:\n' + ''.join('  - ' + json.dumps(','.join(r)) + '\n' for r in rules))]:
            (output / (name + '.' + suffix)).write_text(content)
    (output / 'NOTICE.md').write_text('Domain categories from MetaCubeX/meta-rules-dat, GPL-3.0.\nhttps://github.com/MetaCubeX/meta-rules-dat\nUpstream commit: ' + commit + '\n')
    # The generated `meta` branch omits LICENSE; distribute the standard GPL-3.0 text.
    license_text = (Path(__file__).resolve().parents[1] / 'LICENSE').read_text() if not input_dir else 'Synthetic test fixture, not for publication.\n'
    (output / 'LICENSE').write_text(license_text)
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.is_file() and p.name != 'manifest.json'}
    manifest = {'schema_version': 1, 'upstream': {'repository': REPOSITORY, 'commit': commit},
                'counts': counts, 'input_sha256': inputs, 'sha256': hashes,
                'content_digest': hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--commit')
    args = parser.parse_args()
    print(json.dumps(build(args.output, args.commit)['counts']))
