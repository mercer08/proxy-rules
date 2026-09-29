"""Immutable private per-account file backups and verified, scoped restores."""
import hashlib
import io
import json
import os
from pathlib import Path
import re
import tempfile
import time
import zipfile

FILES = ('surge.conf', 'mihomo.yaml', 'stash.yaml', 'shadowrocket.conf', 'shadowrocket.txt', 'node.txt')
CONFIGS = FILES[:4]


def account_etag(record):
    hashes = {name: hashlib.sha256(Path(record['files'][name]).read_bytes()).hexdigest() for name in FILES}
    return hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()


def root(config, identifier):
    if not re.fullmatch(r'[a-f0-9]{24}', identifier):
        raise ValueError('Invalid account identifier')
    path = Path(config['state_dir']) / 'profile-versions' / identifier
    if path.is_symlink() or path.parent.is_symlink():
        raise ValueError('Unsafe version directory')
    return path


def backup(config, record, identifier, atomic_write, reason='before-change'):
    contents = {name: Path(record['files'][name]).read_bytes() for name in FILES}
    hashes = {name: hashlib.sha256(body).hexdigest() for name, body in contents.items()}
    digest = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    parent = root(config, identifier)
    parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    os.chmod(parent.parent, 0o700)
    for item in parent.iterdir():
        if re.fullmatch(r'[0-9]+-[a-f0-9]{12}', item.name) and item.is_dir() and not item.is_symlink():
            try:
                previous, _ = read_version(config, identifier, item.name)
            except (ValueError, KeyError, TypeError, FileNotFoundError):
                continue
            if previous['digest'] == digest:
                return previous
    stamp = time.time_ns()
    version = str(stamp) + '-' + digest[:12]
    metadata = {'version': version, 'created_ns': stamp, 'reason': reason, 'label': record['label'],
                'digest': digest, 'sha256': hashes, 'node_sha256': hashes['node.txt']}
    with tempfile.TemporaryDirectory(prefix='.staging-', dir=parent) as temporary:
        staging = Path(temporary)
        for name, body in contents.items():
            atomic_write(staging / name, body)
        atomic_write(staging / 'manifest.json', json.dumps(metadata, ensure_ascii=False, indent=2) + '\n')
        os.rename(staging, parent / version)
        staging.mkdir()
    return metadata


def list_versions(config, identifier):
    parent = root(config, identifier)
    if not parent.exists():
        return []
    entries = []
    for path in parent.iterdir():
        if re.fullmatch(r'[0-9]+-[a-f0-9]{12}', path.name) and path.is_dir() and not path.is_symlink():
            m = json.loads((path / 'manifest.json').read_text())
            entries.append({k: m[k] for k in ('version', 'created_ns', 'reason', 'digest')})
    return sorted(entries, key=lambda m: m['created_ns'], reverse=True)


def read_version(config, identifier, version):
    if not re.fullmatch(r'[0-9]+-[a-f0-9]{12}', version):
        raise ValueError('Invalid version')
    path = root(config, identifier) / version
    if path.is_symlink() or not path.is_dir():
        raise ValueError('Version unavailable')
    if (path / 'manifest.json').is_symlink():
        raise ValueError('Unsafe version manifest')
    metadata = json.loads((path / 'manifest.json').read_text())
    if set(metadata['sha256']) != set(FILES) or metadata['version'] != version:
        raise ValueError('Invalid version manifest')
    contents = {}
    for name, expected in metadata['sha256'].items():
        if (path / name).is_symlink():
            raise ValueError('Unsafe version file')
        body = (path / name).read_bytes()
        if hashlib.sha256(body).hexdigest() != expected:
            raise ValueError('Version checksum mismatch')
        contents[name] = body
    digest = hashlib.sha256(json.dumps(metadata['sha256'], sort_keys=True).encode()).hexdigest()
    if digest != metadata['digest']:
        raise ValueError('Version digest mismatch')
    return metadata, contents


def package(config, identifier, version):
    metadata, contents = read_version(config, identifier, version)
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, body in contents.items():
            archive.writestr(name, body)
        archive.writestr('VERSION.json', json.dumps(metadata, ensure_ascii=False, indent=2))
    return output.getvalue()


def restore(config, record, identifier, version, atomic_write, regenerate):
    metadata, contents = read_version(config, identifier, version)
    if hashlib.sha256(Path(record['files']['node.txt']).read_bytes()).hexdigest() != metadata['node_sha256']:
        raise ValueError('Node credentials changed; old configuration cannot be restored')
    backup(config, record, identifier, atomic_write, 'before-rollback')
    target = Path(config['state_dir']) / 'profile-overrides' / identifier
    if target.is_symlink() or target.parent.is_symlink():
        raise ValueError('Unsafe override directory')
    target.mkdir(parents=True, mode=0o700, exist_ok=True)
    os.chmod(target, 0o700)
    os.chmod(target.parent, 0o700)
    existing = {name: (target / name).read_bytes() if (target / name).exists() else None for name in CONFIGS}
    try:
        for name in CONFIGS:
            atomic_write(target / name, contents[name])
        regenerate()
    except Exception:
        for name, body in existing.items():
            if body is None:
                (target / name).unlink(missing_ok=True)
            else:
                atomic_write(target / name, body)
        raise
