#!/usr/bin/env python3
"""Publish separate service tags without changing the default base-rule release."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from publish import run
from build import fetch


def publish(source, repo):
    manifest = json.loads((source / 'manifest.json').read_text())
    with tempfile.TemporaryDirectory(prefix='service-rules-') as temporary:
        checkout = Path(temporary) / 'checkout'
        checkout.mkdir()
        run('git', 'init', '--initial-branch=services', cwd=checkout)
        run('git', 'config', 'user.name', 'github-actions[bot]', cwd=checkout)
        run('git', 'config', 'user.email', '41898282+github-actions[bot]@users.noreply.github.com', cwd=checkout)
        run('git', 'config', 'credential.helper', '', cwd=checkout)
        run('git', 'config', '--add', 'credential.helper', '!gh auth git-credential', cwd=checkout)
        run('git', 'remote', 'add', 'origin', 'https://github.com/' + repo + '.git', cwd=checkout)
        found = run('git', 'ls-remote', '--exit-code', '--heads', 'origin', 'services', check=False)
        if found.returncode not in (0, 2):
            raise RuntimeError('Cannot inspect service branch')
        if found.returncode == 0:
            run('git', 'fetch', '--depth=1', 'origin', 'services', cwd=checkout)
            run('git', 'checkout', '-B', 'services', 'FETCH_HEAD', cwd=checkout)
            previous = json.loads((checkout / 'manifest.json').read_text())
            for name, count in manifest['counts'].items():
                if not 0.5 <= count / previous['counts'][name] <= 2:
                    raise ValueError('Abnormal service count change: ' + name)
            if previous['content_digest'] == manifest['content_digest']:
                pointer = json.loads((checkout / 'release.json').read_text())
            else:
                pointer = None
                run('git', 'rm', '-r', '--ignore-unmatch', '.', cwd=checkout)
        else:
            pointer = None
        if pointer is None:
            tag = 'services-' + datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + manifest['content_digest'][:10]
            for path in source.iterdir():
                shutil.copy2(path, checkout / path.name)
            pointer = {'tag': tag, 'digest': manifest['content_digest']}
            (checkout / 'release.json').write_text(json.dumps(pointer) + '\n')
            run('git', 'add', '.', cwd=checkout)
            run('git', 'commit', '-m', 'Publish ' + tag, cwd=checkout)
            run('git', 'tag', tag, cwd=checkout)
            run('git', 'push', '--atomic', 'origin', 'HEAD:refs/heads/services', 'refs/tags/' + tag, cwd=checkout)
        # Verify CDN delivery of the immutable public snapshot before reporting success.
        origin = 'https://cdn.jsdelivr.net/gh/' + repo + '@' + pointer['tag'] + '/'
        for name, expected in manifest['sha256'].items():
            if hashlib.sha256(fetch(origin + name)).hexdigest() != expected:
                raise ValueError('Service CDN checksum mismatch: ' + name)
        print('Service snapshot verified: ' + pointer['tag'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--repository', default='mercer08/proxy-rules')
    args = parser.parse_args()
    if args.repository != 'mercer08/proxy-rules':
        parser.error('Unexpected repository')
    publish(args.source, args.repository)
