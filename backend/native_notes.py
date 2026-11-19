import json
import os
import pathlib
import queue
import subprocess
import threading
import atexit


class NativeNotes:
    background = True

    def __init__(self):
        self.process = None
        self.responses = queue.Queue()
        atexit.register(self.close)

    def _executable(self):
        override = os.environ.get('LINKINNOTES_BACKEND')
        if override and pathlib.Path(override).is_file():
            return pathlib.Path(override)
        import psutil
        candidates = []
        for process in psutil.process_iter(['name', 'exe', 'cmdline']):
            try:
                info = process.info
                if (info['name'] or '').lower() in ('linkinnotes.exe', 'linkin-notes.exe') and info['exe'] and '--watch-client' not in (info['cmdline'] or []):
                    executable = pathlib.Path(info['exe'])
                    source = executable.parents[3] / 'backend' / 'service.py' if executable.parent.name == 'debug' and executable.parent.parent.name == 'target' else None
                    candidates.append(source if source and source.is_file() else executable.parent / 'sidecar' / 'linkin-backend.exe')
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        existing = [path for path in candidates if path.is_file()]
        if not existing:
            raise ValueError('请先打开 LinkinNotes 和已登录的好用便签，再刷新个人工作台')
        return max(existing, key=lambda path: path.stat().st_mtime)

    def _start(self):
        self.responses = queue.Queue()
        executable = self._executable()
        command = ['python', '-X', 'utf8', '-u', str(executable)] if executable.suffix == '.py' else [str(executable)]
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, text=True, encoding='utf-8',
                                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        output, responses = self.process.stdout, self.responses
        def read():
            try:
                for line in output:
                    responses.put(json.loads(line))
            except (OSError, ValueError):
                pass
            finally:
                responses.put({'error': 'LinkinNotes 同步服务已退出，请刷新重试'})
        threading.Thread(target=read, daemon=True).start()

    def close(self):
        if self.process:
            try:
                if self.process.poll() is None:
                    self.process.terminate()
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
            finally:
                self.process = None

    def call(self, method, params=None):
        if method not in ('tasks', 'save', 'complete'):
            raise ValueError('个人工作台只允许读取、编辑、移动象限和完成独立待办')
        if not self.process or self.process.poll() is not None:
            self._start()
        try:
            self.process.stdin.write(json.dumps({'method': method, 'params': params or {}}, ensure_ascii=False) + '\n')
            self.process.stdin.flush()
            response = self.responses.get(timeout=40)
        except (OSError, queue.Empty) as error:
            self.close()
            raise ValueError('LinkinNotes 暂时无法响应，请刷新重试') from error
        if 'error' in response:
            raise ValueError(response['error'])
        return response['result']
