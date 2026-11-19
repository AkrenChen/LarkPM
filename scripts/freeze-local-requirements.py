import argparse
import datetime
import json
import os
import pathlib
import sqlite3
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from workspace import Workspace


def freeze(connection):
    counts = {'projects': 0, 'tasks_locked': 0, 'containers_locked': 0}
    projects = {pid for pid, body in connection.execute('SELECT id,body FROM projects') if not json.loads(body).get('demo')}
    touched = set()
    for task_id, project, body in connection.execute('SELECT id,project,body FROM tasks').fetchall():
        if project not in projects:
            continue
        task = json.loads(body)
        if task.get('locally_removed'):
            continue
        changed = not task.get('module_local')
        task['module_local'] = True
        if task.get('is_requirement') and not task.get('published_requirement'):
            task['published_requirement'] = True
            counts['containers_locked'] += 1
            changed = True
        if changed:
            task['revision'] = task.get('revision', 0) + 1
            connection.execute('UPDATE tasks SET body=? WHERE id=?', (json.dumps(task, ensure_ascii=False), task_id))
            counts['tasks_locked'] += 1
            touched.add(project)
    counts['projects'] = len(touched)
    return counts


def verify(path):
    workspace = Workspace(path)
    try:
        before = workspace._all()
        projects = {p['id'] for p in workspace.projects() if not p.get('demo')}
        expected = {t['id']: (t.get('module', ''), bool(t.get('is_requirement'))) for t in before if t['project'] in projects}
        for project in projects:
            tasks = [t for t in before if t['project'] == project and t.get('source')]
            scopes = {t['source']['scope'] for t in tasks}
            for scope in scopes:
                scoped = [t for t in tasks if t['source']['scope'] == scope]
                records = [dict(t['source']['base'], record_id=t['source']['record_id'], module='', is_requirement=False, acceptance=t.get('acceptance', ''), version=t.get('version', '')) for t in scoped]
                workspace.merge_remote(records, scope, project)
                workspace.merge_remote([r for r, t in zip(records, scoped) if not t.get('is_requirement')], scope, project)
        for task in workspace._all():
            if task['id'] in expected:
                assert (task.get('module', ''), bool(task.get('is_requirement'))) == expected[task['id']], task['id']
        return len(expected)
    finally:
        workspace.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--database', type=pathlib.Path, default=pathlib.Path(os.environ.get('LOCALAPPDATA', pathlib.Path.home())) / 'LarkPM' / 'workspace.db')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    path = args.database.resolve(strict=True)
    connection = sqlite3.connect(str(path), timeout=30)
    try:
        with tempfile.TemporaryDirectory(prefix='larkpm-freeze-') as directory:
            trial_path = pathlib.Path(directory) / 'workspace.db'
            trial = sqlite3.connect(trial_path)
            connection.backup(trial)
            with trial:
                expected = freeze(trial)
            trial.close()
            checked = verify(trial_path)
        print(json.dumps({'preflight': expected, 'verified_records': checked}))
        if not args.apply:
            return
        backup_dir = path.parent / 'backups'
        backup_dir.mkdir(exist_ok=True)
        timestamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        backup_path = backup_dir / f'workspace-before-local-freeze-{timestamp}.db'
        with connection:
            connection.execute('BEGIN IMMEDIATE')
            backup_source = sqlite3.connect(str(path), timeout=30)
            backup = sqlite3.connect(backup_path)
            try:
                backup_source.backup(backup)
            finally:
                backup.close()
                backup_source.close()
            actual = freeze(connection)
            if actual != expected:
                raise RuntimeError('Data changed since preflight; transaction rolled back. Retry after refreshing.')
        assert connection.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        print(json.dumps({'applied': actual, 'backup': str(backup_path)}))
    finally:
        connection.close()


if __name__ == '__main__':
    main()
