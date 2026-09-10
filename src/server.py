"""Loopback-only development application. No external publishing endpoint."""
import argparse
import json
import mimetypes
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, unquote
from .store import Store
from .collector import Collector

ROOT = Path(__file__).resolve().parents[1]

def create_server(root=ROOT, port=8765):
    store = Store(root)
    from .studio import Studio,reel_info
    studio=Studio(store)
    class Handler(BaseHTTPRequestHandler):
        def send(self, code, data, content_type='application/json; charset=utf-8'):
            self.send_response(code)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self'; style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(data)

        def allowed(self):
            return self.headers.get('Host') in (f'localhost:{self.server.server_port}', f'127.0.0.1:{self.server.server_port}')

        def do_GET(self):
            if not self.allowed():
                return self.send(403, b'{}')
            path = unquote(urlparse(self.path).path)
            if path == '/api/state':
                data=store.snapshot();data['studio']=studio.status;data['studio_posts']=studio.posts()
                data['studio_mode']='manual-v1'
                for item in data['items']:
                    reel=reel_info(root,item);item['reel']={k:v for k,v in reel.items() if k!='path'} if reel else None
                return self.send(200, json.dumps(data, ensure_ascii=False).encode())
            if path.startswith('/video/'):
                base=Path(root)/'assets/videos/generated'
                target=(base/path.removeprefix('/video/')).resolve()
            elif path.startswith('/media/'):
                base = Path(root) / 'assets/images/generated'
                target = (base / path.removeprefix('/media/')).resolve()
            else:
                base = ROOT / 'src/web'
                target = (base / ('index.html' if path == '/' else path.lstrip('/'))).resolve()
            if not target.is_relative_to(base.resolve()) or not target.is_file():
                return self.send(404, b'{}')
            self.send(200, target.read_bytes(), mimetypes.guess_type(target)[0] or 'application/octet-stream')

        def do_POST(self):
            origin = self.headers.get('Origin')
            expected = f'http://{self.headers.get("Host")}'
            if not self.allowed() or origin != expected or self.headers.get('Content-Type') != 'application/json':
                return self.send(403, b'{}')
            try:
                length = int(self.headers.get('Content-Length', 0))
                if not 0 < length <= 16000:
                    raise ValueError('요청 크기가 올바르지 않습니다.')
                payload = json.loads(self.rfile.read(length))
                if studio.status['busy']:raise ValueError('작업이 진행 중입니다. 완료 후 다시 시도해 주세요.')
                if self.path == '/api/produce':
                    studio.start(studio.produce)
                elif self.path == '/api/publish-formats':
                    studio.request_publish(payload['id'],payload['version'],payload['formats'],payload.get('sha'))
                elif self.path == '/api/settings':
                    store.settings(payload['review'], payload['revision'])
                elif self.path == '/api/operations':
                    from .operations import update
                    update(root,payload['values'],payload['revision'])
                elif self.path == '/api/action':
                    store.action(payload['id'], payload['version'], payload['action'], payload.get('caption'))
                else:
                    return self.send(404, b'{}')
                self.send(200, b'{"ok":true}')
            except (ValueError, KeyError, TypeError) as e:
                self.send(400, json.dumps({'error': str(e)}, ensure_ascii=False).encode())

        def log_message(self, *_):
            pass

    return ThreadingHTTPServer(('127.0.0.1', port), Handler), store

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    server, store = create_server(port=args.port)
    stop = threading.Event()
    print(f'Local preview: http://127.0.0.1:{server.server_port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.server_close()

if __name__ == '__main__':
    main()
