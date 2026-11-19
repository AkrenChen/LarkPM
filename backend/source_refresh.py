import copy
import json
import pathlib
import threading
import time

from project_sources import refreshed_cache
from workspace import Workspace


def apply_cache(workspace, project_id, kind, source, result):
    with workspace.db:
        workspace.db.execute('BEGIN IMMEDIATE')
        row = workspace.db.execute('SELECT body FROM projects WHERE id=?', (project_id,)).fetchone()
        if not row:
            return
        current = json.loads(row[0])
        if current.get('archived') or current.get('sources', {}).get(kind) != source:
            return
        cache = current.setdefault('source_cache', {})
        cache[kind] = dict(cache.get(kind, {}), error=result['error']) if result.get('error') else result
        workspace.db.execute('UPDATE projects SET body=? WHERE id=?', (json.dumps(current, ensure_ascii=False), project_id))


class SourceRefresh:
    def __init__(self, path, remote):
        self.path = pathlib.Path(path)
        self.remote = remote
        self.lock = threading.Lock()
        self.jobs = {}
        self.workers = set()
        self.failures = {}

    def start(self, project, kinds=None):
        if project.get('archived') or project.get('demo'):
            return []
        sources = project.get('sources', {})
        for kind in kinds if kinds is not None else sources:
            if kind not in sources:
                continue
            key, source = (project['id'], kind), copy.deepcopy(sources[kind])
            with self.lock:
                previous = self.jobs.get(key)
                if previous and previous['source'] == source:
                    continue
                token = object()
                self.jobs[key] = dict(source=source, token=token)
                self.failures.pop(key, None)
                worker = threading.Thread(target=self._read, args=(key, source, token), daemon=True)
                self.workers.add(worker)
                worker.start()
        return self.view(project)['source_refresh']

    def _read(self, key, source, token):
        workspace = None
        try:
            try:
                result = refreshed_cache(self.remote, source, key[1])
            except Exception as error:
                result = dict(error=str(error))
            if not self.path.is_file():
                return
            workspace = Workspace(self.path)
            with self.lock:
                # A replaced connection may finish after a newer request for the same project.
                if self.jobs.get(key, {}).get('token') is token:
                    apply_cache(workspace, key[0], key[1], source, result)
        except Exception as error:
            with self.lock:
                if self.jobs.get(key, {}).get('token') is token:
                    self.failures[key] = (source, str(error))
        finally:
            if workspace:
                workspace.close()
            with self.lock:
                if self.jobs.get(key, {}).get('token') is token:
                    self.jobs.pop(key, None)
                self.workers.discard(threading.current_thread())

    def view(self, project):
        result = copy.deepcopy(project)
        with self.lock:
            result['source_refresh'] = [kind for (project_id, kind), job in self.jobs.items()
                                        if project_id == project['id'] and job['source'] == project.get('sources', {}).get(kind)]
            for (project_id, kind), (source, error) in self.failures.items():
                if project_id == project['id'] and source == project.get('sources', {}).get(kind):
                    cache = result.setdefault('source_cache', {})
                    cache[kind] = dict(cache.get(kind, {}), error=error)
        return result

    def wait(self, timeout):
        deadline = time.monotonic() + timeout
        while True:
            with self.lock:
                workers = list(self.workers)
            if not workers:
                return True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            workers[0].join(remaining)
