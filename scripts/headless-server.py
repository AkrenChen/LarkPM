"""Serve the built UI against an isolated local workspace for headless checks."""
import functools
import json
import pathlib
import sys
import tempfile
from http.server import HTTPServer, SimpleHTTPRequestHandler

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from service import Service
from workspace import Conflict


class OfflineRemote:
    def status(self):
        return {'configured': True, 'authorized': True}

    def source_rows(self, source, kind):
        if kind == 'versions':
            return [dict(id='android-live', platform='安卓', version='v1.0.9', status='已过审', released='2026-10-27'),
                    dict(id='android-new', platform='安卓', version='v1.0.10', status='已提审', released=''),
                    dict(id='ios-new', platform='iOS', version='v1.0.0', status='已提审', released='')]
        return [dict(id='test-a', project='SolitairePuzzle', title='安卓测试', start='2026-11-01', end='2026-11-03', version='Android v1.0.0'),
                dict(id='test-b', project='SolitairePuzzle', title='iOS测试', start='2026-11-02', end='2026-11-04', version='iOS v1.0.0'),
                dict(id='other', project='Solitaire', title='其他项目测试', start='2026-11-01', end='2026-11-03')]

    def departments(self, project):
        options = [('other', '测试部', 0)] if project['table_id'] == 'other' else [('plan', '策划', 14), ('art', '美术', 19), ('ui', 'UI', 13), ('dev', '开发', 17), ('motion', '动效', 16)]
        if project['table_id'] == 'tags':
            options.append(('3d', '3D', 15))
        return {'field': '部门', 'options': [dict(id=i, name=n, color=c) for i, n, c in options], 'error': ''}


def main():
    with tempfile.TemporaryDirectory(prefix='larkpm-ui-') as directory:
        service = Service(pathlib.Path(directory) / 'workspace.db', OfflineRemote())

        class Handler(SimpleHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                if self.path in ('/', '/index.html'):
                    content = (ROOT / 'dist' / 'index.html').read_text(encoding='utf-8')
                    bridge = '''<script>window.__TAURI_INTERNALS__={invoke:async(command,args)=>{
                        if(command!=='rpc')throw 'Only task RPC allowed in headless checks';
                        if(args.method==='open_project_table'){window.__openedProjectTable=args.params;return {opened:true};}
                        const response=await fetch('/rpc',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(args)});
                        const value=await response.json();if(value.error)throw value.error;return value.result;
                    }};</script>'''
                    body = content.replace('<head>', '<head>' + bridge).encode('utf-8')
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/html; charset=utf-8')
                    self.send_header('Content-Length', str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    super().do_GET()

            def do_POST(self):
                try:
                    request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                    if request['method'] not in ('snapshot', 'demo', 'create', 'edit', 'link', 'link_many', 'branch', 'dependencies', 'project_save', 'resolve', 'settings_save', 'departments_sync', 'project_sources_sync', 'workflow_arrange', 'workflow_column_save'):
                        raise ValueError('Headless verification does not perform external operations')
                    result = {'result': service.call(request['method'], request.get('params') or {})}
                except Conflict as error:
                    result = {'error': json.dumps({'kind': 'conflict', 'current': error.current, 'message': str(error)}, ensure_ascii=False)}
                except Exception as error:
                    result = {'error': str(error)}
                body = json.dumps(result, ensure_ascii=False).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        server = HTTPServer(('127.0.0.1', 0), functools.partial(Handler, directory=str(ROOT / 'dist')))
        print(f'http://127.0.0.1:{server.server_port}', flush=True)
        try:
            server.serve_forever()
        finally:
            server.server_close()
            service.w.close()


if __name__ == '__main__':
    main()
