#!/usr/bin/env python3
"""Private loopback-only configuration editor, reached through an SSH tunnel."""
import argparse
import contextlib
import fcntl
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import mimetypes
from pathlib import Path
import re
import sys
import threading
from urllib.parse import quote, unquote, urlsplit
import zipfile

import distribute as d

MAX_EDIT = 2 * 1024 * 1024


class ConsoleError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


class Console:
    def __init__(self, config, assets):
        self.config, self.assets = config, Path(assets).resolve()
        self.state = Path(config['state_dir'])
        self.mutex = threading.RLock()

    @contextlib.contextmanager
    def lock(self):
        with self.mutex, (self.state / 'sync.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            yield

    def records(self):
        return json.loads((self.state / 'profiles.json').read_text())['accounts']

    def identity(self, record):
        return Path(record['files']['surge.conf']).parent.name

    def account(self, identifier):
        if not re.fullmatch(r'[a-f0-9]{24}', identifier):
            raise ConsoleError(404, '账号不存在')
        for record in self.records():
            if self.identity(record) == identifier:
                return record
        raise ConsoleError(404, '账号不存在或已停用')

    def file(self, identifier, name):
        record = self.account(identifier)
        if name not in d.PROFILE_FILES or name not in record['files']:
            raise ConsoleError(404, '配置不存在')
        path = Path(record['files'][name])
        expected = self.state / 'profiles/current' / identifier / name
        if path != expected:
            raise ConsoleError(500, '配置路径异常')
        resolved = path.resolve()
        if not resolved.is_relative_to((self.state / 'profiles/generations').resolve()):
            raise ConsoleError(500, '配置路径异常')
        content = path.read_text()
        return {'name': name, 'content': content,
                'etag': hashlib.sha256(content.encode()).hexdigest(),
                'edited': name in record.get('edited', [])}

    def list_accounts(self):
        return [{'id': self.identity(r), 'label': r['label'],
                 'businessRules': r['business_rules'], 'nodes': r['nodes'],
                 'edited': r.get('edited', []), 'files': list(r['files'])} for r in self.records()]

    def regenerate(self):
        with contextlib.redirect_stdout(sys.stderr):
            d.generate(self.config)

    def edit(self, identifier, name, content, etag, reset=False):
        existing = self.file(identifier, name)
        if etag != existing['etag']:
            raise ConsoleError(409, '服务器配置已变化，请重新加载后编辑')
        if not reset:
            if not isinstance(content, str) or len(content.encode()) > MAX_EDIT or '\x00' in content:
                raise ConsoleError(400, '内容格式不正确或超过 2 MB')
            if re.search(r'(?mi)^\s*(?:#!MANAGED-CONFIG|update-url\s*=)', content):
                raise ConsoleError(400, 'SSH 离线配置不能添加自动更新地址')
        root = self.state / 'profile-overrides'
        folder = root / identifier
        if root.is_symlink() or folder.is_symlink():
            raise ConsoleError(500, '覆盖目录异常')
        root.mkdir(mode=0o700, exist_ok=True)
        folder.mkdir(mode=0o700, exist_ok=True)
        path = folder / name
        previous = path.read_bytes() if path.exists() else None
        if reset:
            path.unlink(missing_ok=True)
        else:
            d.atomic_write(path, content)
        try:
            self.regenerate()
        except Exception:
            if previous is None:
                path.unlink(missing_ok=True)
            else:
                d.atomic_write(path, previous)
            raise ConsoleError(503, '生成失败，编辑未保存，请稍后重试') from None
        return self.file(identifier, name)

    def package(self, identifier):
        record = self.account(identifier)
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for name in record['files']:
                content = self.file(identifier, name)['content']
                archive.writestr(name, content)
            archive.writestr('README.txt',
                'Surge：导入 surge.conf。\nMihomo：导入 mihomo.yaml。\n'
                'Shadowrocket：复制 node.txt 的 vmess 地址导入节点，然后导入并启用 shadowrocket.conf。\n'
                '仅分享本人的文件包。新规则版本需要重新通过 SSH 下载并导入完整配置。\n')
        return output.getvalue(), record['label'] + '.zip'


class Handler(BaseHTTPRequestHandler):
    server_version = 'PrivateConsole'

    def log_message(self, *args):
        pass  # Do not log names, paths, or configuration contents.

    def send(self, status, body, mime='application/json; charset=utf-8', filename=None):
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; worker-src 'self' blob:; style-src 'self' 'unsafe-inline'; font-src 'self' data:; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        if filename:
            self.send_header('Content-Disposition', "attachment; filename=account.zip; filename*=UTF-8''" + quote(filename))
        self.end_headers()
        self.wfile.write(body)

    def json(self, value):
        self.send(200, json.dumps(value, ensure_ascii=False).encode())

    def request_body(self):
        if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            raise ConsoleError(415, '需要 JSON 内容')
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if length < 1 or length > MAX_EDIT + 65536:
                raise ConsoleError(413, '文件过大')
            result = json.loads(self.rfile.read(length))
            if not isinstance(result, dict):
                raise ValueError()
            return result
        except (ValueError, UnicodeError):
            raise ConsoleError(400, '请求内容不正确') from None

    def dispatch(self, method):
        try:
            host = self.headers.get('Host', '')
            if not re.fullmatch(r'(?:127\.0\.0\.1|localhost)(?::[0-9]{1,5})?', host):
                raise ConsoleError(403, '请通过本机 SSH 隧道访问')
            origin = self.headers.get('Origin')
            if origin and origin != 'http://' + host or self.headers.get('Sec-Fetch-Site') == 'cross-site':
                raise ConsoleError(403, '仅允许本站请求')
            path = unquote(urlsplit(self.path).path)
            app = self.server.console
            if path.startswith('/api/'):
                with app.lock():
                    if path == '/api/accounts' and method == 'GET':
                        return self.json({'accounts': app.list_accounts()})
                    if path == '/api/refresh' and method == 'POST':
                        self.request_body()
                        app.regenerate()
                        return self.json({'accounts': app.list_accounts()})
                    match = re.fullmatch(r'/api/accounts/([a-f0-9]{24})/(files/([^/]+)|download)', path)
                    if not match:
                        raise ConsoleError(404, '接口不存在')
                    identifier, action, name = match.groups()
                    if action == 'download' and method == 'GET':
                        body, filename = app.package(identifier)
                        return self.send(200, body, 'application/zip', filename)
                    if name and method == 'GET':
                        return self.json(app.file(identifier, name))
                    if name and method in ('PUT', 'DELETE'):
                        body = self.request_body()
                        return self.json(app.edit(identifier, name, body.get('content'), body.get('etag'), reset=method == 'DELETE'))
                    raise ConsoleError(405, '操作不支持')
            if method != 'GET':
                raise ConsoleError(405, '操作不支持')
            candidate = app.assets / ('index.html' if path == '/' else path.lstrip('/'))
            resolved = candidate.resolve()
            if not resolved.is_relative_to(app.assets) or not resolved.is_file():
                raise ConsoleError(404, '页面不存在')
            mime = mimetypes.guess_type(str(resolved))[0] or 'application/octet-stream'
            return self.send(200, resolved.read_bytes(), mime)
        except ConsoleError as error:
            self.send(error.status, json.dumps({'error': error.message}, ensure_ascii=False).encode())
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            self.send(503, json.dumps({'error': '服务暂时不可用，请稍后重试'}, ensure_ascii=False).encode())

    def do_GET(self):
        self.dispatch('GET')

    def do_PUT(self):
        self.dispatch('PUT')

    def do_DELETE(self):
        self.dispatch('DELETE')

    def do_POST(self):
        self.dispatch('POST')


def serve(config, assets, port=8765):
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.console = Console(config, assets)
    return server


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=Path('/etc/proxy-distribution/config.json'))
    parser.add_argument('--assets', type=Path, default=Path('/opt/proxy-distribution/console/dist'))
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    serve(json.loads(args.config.read_text()), args.assets, args.port).serve_forever()
