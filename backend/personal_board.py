import json
import os
import pathlib

QUADRANTS = ('ui', 'nui', 'uni', 'nuni')
DEFAULT_NAMES = dict(ui='重要且紧急', nui='重要不紧急', uni='紧急不重要', nuni='不重要不紧急')


def settings(workspace):
    workspace.db.execute('CREATE TABLE IF NOT EXISTS personal_board (id INTEGER PRIMARY KEY CHECK(id=1), body TEXT NOT NULL)')
    row = workspace.db.execute('SELECT body FROM personal_board WHERE id=1').fetchone()
    saved = json.loads(row[0]) if row else {}
    path = pathlib.Path(os.environ['LINKINNOTES_PREFERENCES']) if os.environ.get('LINKINNOTES_PREFERENCES') else pathlib.Path(os.environ.get('APPDATA', pathlib.Path.home() / 'AppData' / 'Roaming')) / 'local.linkin.notes' / 'preferences.json'
    names = dict(DEFAULT_NAMES)
    try:
        custom = json.loads(path.read_text(encoding='utf-8')).get('names', {})
        names.update({key: value for key, value in custom.items() if key in QUADRANTS and isinstance(value, str) and value.strip()})
    except (OSError, ValueError, AttributeError):
        pass
    legacy_sync = False
    if 'sync' not in saved:
        legacy_sync = any(task.get('linked') for task in workspace._all())
        if workspace.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='native_positions'").fetchone():
            legacy_sync = legacy_sync or bool(workspace.db.execute('SELECT 1 FROM native_positions LIMIT 1').fetchone())
        migrated = json.dumps({'sync': legacy_sync})
        if workspace.db.in_transaction:
            workspace.db.execute('INSERT OR IGNORE INTO personal_board VALUES (1,?)', (migrated,))
        else:
            with workspace.db:
                workspace.db.execute('INSERT OR IGNORE INTO personal_board VALUES (1,?)', (migrated,))
        saved = json.loads(workspace.db.execute('SELECT body FROM personal_board WHERE id=1').fetchone()[0])
    return dict(sync=saved.get('sync', legacy_sync), names=names)


def quadrant(task, side, config):
    value = task.get('shared_quadrant', task.get('pm_quadrant')) if config['sync'] and task.get('linked') else task.get(side + '_quadrant')
    return value if value in QUADRANTS else 'nuni'


def move(workspace, task_id, target, revision, side):
    if target not in QUADRANTS or side not in ('pm', 'linkin'):
        raise ValueError('无效的象限')
    config = settings(workspace)
    with workspace.db:
        workspace.db.execute('BEGIN IMMEDIATE')
        task = workspace._raw(task_id)
        workspace._check(task, revision)
        if task.get('locally_removed') or task.get('is_requirement'):
            raise ValueError('任务已从工作台移除')
        if side == 'linkin' and not task.get('linked'):
            raise ValueError('只能移动已关联的需求任务')
        task[side + '_quadrant'] = target
        if config['sync'] and task.get('linked'):
            task.update(pm_quadrant=target, linkin_quadrant=target, shared_quadrant=target)
        workspace._put(task)
    return dict(workspace.get(task_id), personal_quadrant=quadrant(task, side, config))


def set_sync(workspace, enabled):
    if not isinstance(enabled, bool):
        raise ValueError('同步开关必须为布尔值')
    previous = settings(workspace)
    with workspace.db:
        workspace.db.execute('BEGIN IMMEDIATE')
        if enabled and not previous['sync']:
            for task in workspace._all():
                if task.get('linked') and not task.get('locally_removed'):
                    value = task.get('pm_quadrant', 'nuni')
                    task.update(shared_quadrant=value, linkin_quadrant=value)
                    workspace._put(task)
        workspace.db.execute('INSERT OR REPLACE INTO personal_board VALUES (1,?)', (json.dumps({'sync': enabled}),))
    return dict(previous, sync=enabled)


def prepare(workspace, project_id):
    config = settings(workspace)
    owner = workspace._settings()['profile'].get('owner_id')
    count = 0
    if config['sync'] and owner:
        with workspace.db:
            workspace.db.execute('BEGIN IMMEDIATE')
            for task in workspace._all(project_id):
                if task.get('linked') or task.get('is_requirement') or task.get('locally_removed') or not any(person['id'] == owner for person in task['owners']):
                    continue
                value = task.get('pm_quadrant', 'nuni')
                task.update(linked=True, shared_quadrant=value, linkin_quadrant=value)
                workspace._put(task)
                count += 1
    return dict(config, linked=count)
