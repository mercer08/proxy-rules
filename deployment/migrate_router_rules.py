#!/usr/bin/env python3
"""Move router-only direct exceptions out of a generated Mihomo file override."""
import argparse
import contextlib
import fcntl
import json
from pathlib import Path
import re
import sys
import time

import distribute as d


def extract_private(text):
    """Read only the supported, generated YAML subset; never parse node credentials."""
    result = []
    hosts = re.search(r'(?ms)^hosts:\n(.*?)(?=^[^\s#]|\Z)', text)
    if hosts:
        for line in hosts.group(1).splitlines():
            if not line.strip() or line.lstrip().startswith('#'):
                continue
            match = re.fullmatch(r'  "([A-Za-z0-9_.-]+)": "([0-9a-fA-F:.]+)"', line)
            if not match:
                raise ValueError('Unsupported hosts syntax; review manually')
            result.append('HOST,' + match[1] + ',' + match[2])
    body = re.search(r'(?ms)^rules:\n(.*?)(?=^[^\s#-]|\Z)', text)
    if not body:
        raise ValueError('Missing generated rules block')
    for line in body[1].splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        match = re.fullmatch(r'  - (".*")', line)
        if not match:
            raise ValueError('Unsupported rule syntax; review manually')
        parts = json.loads(match[1]).split(',')
        if len(parts) >= 3 and parts[2] == 'DIRECT' and parts[0] in ('DOMAIN', 'DOMAIN-SUFFIX', 'IP-CIDR', 'IP-CIDR6'):
            result.append(','.join(parts[:2] + parts[3:]))
    d.private_lan_data('\n'.join(result))
    return list(dict.fromkeys(result))


def migrate(config, identifier, apply=False):
    if not re.fullmatch('[0-9a-f]{24}', identifier):
        raise ValueError('Invalid account identifier')
    state = Path(config['state_dir'])
    records = json.loads((state / 'profiles.json').read_text())['accounts']
    record = next((r for r in records if Path(r['files'].get('mihomo.yaml', '')).parent.name == identifier), None)
    if not record or not record.get('business_rules'):
        raise ValueError('Account must exist and enable private business rules')
    override = state / 'profile-overrides' / identifier / 'mihomo.yaml'
    if override.is_symlink() or not override.is_file():
        raise ValueError('Expected a regular Mihomo override file')
    original = override.read_text()
    additions = extract_private(original)
    if not additions:
        raise ValueError('No supported private exceptions found')
    private = d.private_lan_path(config)
    previous = private.read_text()
    merged = previous.rstrip() + '\n\n# Migrated router direct exceptions and static hosts\n' + '\n'.join(additions) + '\n'
    d.private_lan_data(merged)
    print('Private declarations to merge:', len(additions))
    print('Scope: accounts enabled for private business rules; public repository unchanged.')
    if not apply:
        print('Preview only. --apply backs up private inputs, removes this override and regenerates.')
        return
    backup = state / 'private-rule-migrations' / (time.strftime('%Y%m%dT%H%M%S') + '-' + str(time.time_ns()))
    backup.mkdir(mode=0o700, parents=True)
    d.atomic_write(backup / 'mihomo.yaml', original)
    d.atomic_write(backup / 'lan-com.list', previous)
    try:
        d.atomic_write(private, merged)
        override.unlink()
        with contextlib.redirect_stdout(sys.stderr):
            d.generate(config)
    except Exception:
        d.atomic_write(private, previous)
        d.atomic_write(override, original)
        with contextlib.redirect_stdout(sys.stderr):
            d.generate(config)
        raise
    print('Migration complete; private backup:', backup)
    print('Download and import the newly generated Mihomo file on the router.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=Path('/etc/proxy-distribution/config.json'))
    parser.add_argument('--account-id', required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    with (Path(config['state_dir']) / 'sync.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        migrate(config, args.account_id, args.apply)


if __name__ == '__main__':
    main()
