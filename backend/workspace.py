import copy
import json
import os
import pathlib
import re
import sqlite3
import uuid
import time

FIELDS = ('title', 'start', 'end', 'owners', 'state', 'priority')
STATES = ('todo', 'active', 'done', 'paused', 'closed')


def data_dir():
    return pathlib.Path(os.environ.get('LARKPM_DATA_DIR') or pathlib.Path(os.environ.get('LOCALAPPDATA', pathlib.Path.home())) / 'LarkPM')


class Conflict(ValueError):
    def __init__(self, current):
        super().__init__('任务已被另一端修改，请比较最新内容后选择。')
        self.current = current


class Workspace:
    def __init__(self, path=None):
        path = pathlib.Path(path) if path else data_dir() / 'workspace.db'
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=10)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, project TEXT NOT NULL, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS notes (id TEXT PRIMARY KEY, text TEXT NOT NULL, revision INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS projects (id TEXT PRIMARY KEY, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS preferences (id INTEGER PRIMARY KEY CHECK(id=1), body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS publication_jobs (
                project TEXT NOT NULL, scope TEXT NOT NULL, kind TEXT NOT NULL, entity_id TEXT NOT NULL,
                token TEXT NOT NULL, payload TEXT NOT NULL, module TEXT NOT NULL, response TEXT,
                PRIMARY KEY(project,scope,kind,entity_id));
            CREATE TABLE IF NOT EXISTS publication_ignored (
                project TEXT NOT NULL, scope TEXT NOT NULL, kind TEXT NOT NULL, entity_id TEXT NOT NULL,
                PRIMARY KEY(project,scope,kind,entity_id));
        ''')
        self.db.commit()

    def close(self):
        self.db.close()

    def _all(self, project=None, include_removed=False):
        sql, args = ('SELECT body FROM tasks', ()) if project is None else ('SELECT body FROM tasks WHERE project=?', (project,))
        tasks = [json.loads(row[0]) for row in self.db.execute(sql, args)]
        return tasks if include_removed else [t for t in tasks if not t.get('locally_removed')]

    def _raw(self, task_id):
        row = self.db.execute('SELECT body FROM tasks WHERE id=?', (task_id,)).fetchone()
        if not row:
            raise ValueError('任务不存在')
        task = json.loads(row[0])
        task.setdefault('department_override', None)
        task.setdefault('workflow_stage', None)
        task.setdefault('module_local', False)
        task.setdefault('priority', '')
        return task

    def _put(self, task):
        task['revision'] = task.get('revision', 0) + 1
        self.db.execute('INSERT OR REPLACE INTO tasks VALUES (?,?,?)', (task['id'], task['project'], json.dumps(task, ensure_ascii=False)))
        return task

    def _check(self, task, revision):
        if task['revision'] != revision:
            raise Conflict(self.get(task['id']))

    def remove_local(self, task_id, revision):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            task = self._raw(task_id)
            self._check(task, revision)
            task['locally_removed'] = True
            self._put(task)
            for other in self._all(task['project']):
                if task_id in other['upstream'] or other.get('branch_of') == task_id:
                    other['upstream'] = [i for i in other['upstream'] if i != task_id]
                    if other.get('branch_of') == task_id:
                        other['branch_of'] = None
                    self._put(other)
        return {'removed': task_id}

    def _validate(self, task):
        if not isinstance(task['title'], str) or not task['title'].strip() or len(task['title']) > 10000:
            raise ValueError('标题不能为空且最多 10000 字')
        if task['state'] not in STATES:
            raise ValueError('未知工作状态')
        if not isinstance(task.get('priority', ''), str) or len(task.get('priority', '')) > 100:
            raise ValueError('优先级必须是最多100字的选项名称')
        for field in ('start', 'end'):
            if task[field]:
                import datetime
                datetime.date.fromisoformat(task[field])
        if task['start'] and task['end'] and task['end'] < task['start']:
            raise ValueError('截止时间不能早于开始时间')
        if not isinstance(task['owners'], list) or any(not isinstance(o, dict) or not o.get('id') for o in task['owners']):
            raise ValueError('处理人必须包含稳定 ID，可同时提供姓名')
        override = task.get('department_override')
        if override is not None:
            if not isinstance(override, list) or any(not isinstance(d, str) or len(d) > 100 for d in override):
                raise ValueError('部门必须是名称列表，或使用人员默认部门')
            task['department_override'] = list(dict.fromkeys(d.strip() for d in override if d.strip()))

    def create(self, values, upstream=None):
        task = self._new_task(values, upstream)
        with self.db:
            self._put(task)
        return self.get(task['id'])

    def _new_task(self, values, upstream=None):
        task = dict(id=str(uuid.uuid4()), project='default', title='', start='', end='', owners=[], state='todo', module='', version='',
                    source=None, linked=False, upstream=[], branch_of=None, prototypes=False, conflicts={}, revision=0, department_override=None, workflow_stage=None, module_local=False, acceptance='', is_requirement=False, priority='')
        task.update({k: copy.deepcopy(v) for k, v in values.items() if k in task and k not in ('id', 'revision', 'conflicts')})
        task['created_at'] = time.time_ns()
        if upstream is not None and (not isinstance(upstream, list) or any(not isinstance(task_id, str) for task_id in upstream)):
            raise ValueError('前置任务必须为任务ID列表')
        available = {t['id'] for t in self._all(task['project']) if not t.get('is_requirement')} if upstream else set()
        if upstream and any(task_id not in available for task_id in upstream):
            raise ValueError('前置必须是同项目现有任务')
        task['upstream'] = list(dict.fromkeys(upstream or []))
        self._validate(task)
        if task['state'] == 'active' and any(self._raw(task_id)['state'] != 'done' for task_id in task['upstream']):
            raise ValueError('上游尚未完成，请先完成上游或调整依赖')
        return task

    def get(self, task_id):
        task = self._raw(task_id)
        all_tasks = {t['id']: t for t in self._all(task['project'])}
        directory = {p['id']: p.get('department', '') for p in self._settings()['people']}
        return self._task_view(task, all_tasks, directory)

    def _task_view(self, task, all_tasks, directory):
        task = dict(task)
        task.setdefault('department_override', None)
        task.setdefault('workflow_stage', None)
        task.setdefault('module_local', False)
        task.setdefault('priority', '')
        task['blocked_by'] = [i for i in task['upstream'] if i not in all_tasks or all_tasks[i]['state'] != 'done']
        task['readiness'] = 'blocked' if task['blocked_by'] else 'ready'
        task['pending'] = self.pending(task)
        if task['department_override'] is None:
            task['departments'] = list(dict.fromkeys(directory[o['id']] for o in task['owners'] if directory.get(o['id'])))
        else:
            task['departments'] = task['department_override']
        return task

    def task_views(self, project=None, tasks=None):
        tasks = self._all(project) if tasks is None else tasks
        directory = {p['id']: p.get('department', '') for p in self._settings()['people']}
        by_project = {}
        for task in tasks:
            by_project.setdefault(task['project'], {})[task['id']] = task
        return [self._task_view(task, by_project[task['project']], directory) for task in tasks]

    def snapshot(self, project=None):
        from personal_board import settings, quadrant
        config = settings(self)
        return {'tasks': [dict(t, personal_quadrant=quadrant(t, 'pm', config)) for t in self.task_views(project) if not t.get('is_requirement')], 'projects': self.projects(), 'personal_board': config}

    def _guard_start(self, task, state):
        if state == 'active' and task['state'] != 'active':
            tasks = {t['id']: t for t in self._all(task['project'])}
            if any(i not in tasks or tasks[i]['state'] != 'done' for i in task['upstream']):
                raise ValueError('上游尚未完成，请先完成上游或调整依赖')

    def edit(self, task_id, patch, revision):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            task = self._raw(task_id)
            self._check(task, revision)
            self._guard_start(task, patch.get('state'))
            if 'module' in patch:
                task['module_local'] = True
                if patch['module'] != task['module']:
                    task['workflow_stage'] = None
            if 'version' in patch:
                task['version_local'] = True
            for k, v in patch.items():
                if k not in (*FIELDS, 'module', 'version', 'prototypes', 'department_override'):
                    raise ValueError('不允许修改字段：' + k)
                task[k] = copy.deepcopy(v)
                if k in task['conflicts']:
                    task['conflicts'][k]['local'] = copy.deepcopy(v)
            self._validate(task)
            self._put(task)
        return self.get(task_id)

    def dependencies(self, task_id, upstream, revision):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            task = self._raw(task_id)
            self._check(task, revision)
            graph = {t['id']: t['upstream'] for t in self._all(task['project'])}
            if any(i not in graph for i in upstream):
                raise ValueError('上游必须是同项目现有任务')
            graph[task_id] = list(dict.fromkeys(upstream))
            def visit(node, path):
                if node in path:
                    raise ValueError('依赖形成循环，请调整')
                for parent in graph[node]:
                    visit(parent, path | {node})
            visit(task_id, set())
            task['upstream'] = graph[task_id]
            self._put(task)
        return self.get(task_id)

    def branch(self, task_id, values):
        parent = self._raw(task_id)
        child = self.create(dict(title=values.get('title', ''), project=parent['project'], module=parent['module'], version=parent['version'],
                                 owners=values.get('owners', parent['owners']), branch_of=task_id, linked=parent['linked']))
        return self.dependencies(child['id'], [task_id], child['revision'])

    def link(self, task_id, revision):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            task = self._raw(task_id)
            self._check(task, revision)
            if not task['linked']:
                task['linked'] = True
                self._put(task)
        return self.get(task_id)

    def link_many(self, project, selections):
        if not isinstance(selections, list) or not selections:
            raise ValueError('请选择要转为个人待办的任务')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            ids = [selection['id'] for selection in selections]
            if len(ids) != len(set(ids)):
                raise ValueError('同一任务不能重复选择')
            tasks = []
            for selection in selections:
                task = self._raw(selection['id'])
                if task['project'] != project:
                    raise ValueError('只能转换当前项目的任务')
                self._check(task, selection['revision'])
                tasks.append(task)
            already_linked = sum(bool(task['linked']) for task in tasks)
            for task in tasks:
                if not task['linked']:
                    task['linked'] = True
                    self._put(task)
        return dict(linked=len(tasks) - already_linked, already_linked=already_linked)

    def linkin_snapshot(self):
        from personal_board import settings, quadrant
        config = settings(self)
        tasks = []
        for raw in self._all():
            if not raw['linked'] or raw.get('is_requirement'):
                continue
            task = self.get(raw['id'])
            note = self.db.execute('SELECT text,revision FROM notes WHERE id=?', (raw['id'],)).fetchone()
            task.update(note=note[0] if note else '', note_revision=note[1] if note else 0, personal_quadrant=quadrant(raw, 'linkin', config))
            tasks.append(task)
        return {'tasks': tasks, 'projects': self.projects()}

    def linkin_edit(self, task_id, patch, revision):
        if not self._raw(task_id)['linked']:
            raise ValueError('只能编辑已关联的个人待办')
        if any(k not in FIELDS for k in patch):
            raise ValueError('只允许联动标题、起止时间、处理人和完成状态')
        return self.edit(task_id, patch, revision)

    def linkin_save(self, task_id, patch, revision, note, note_revision):
        if any(k not in FIELDS for k in patch):
            raise ValueError('只允许联动标题、起止时间、处理人和完成状态')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            task = self._raw(task_id)
            if not task['linked']:
                raise ValueError('只能编辑已关联的个人待办')
            self._check(task, revision)
            old = self.db.execute('SELECT text,revision FROM notes WHERE id=?', (task_id,)).fetchone()
            if note_revision != (old[1] if old else 0):
                raise Conflict(dict(self.get(task_id), note=old[0] if old else '', note_revision=old[1] if old else 0))
            self._guard_start(task, patch.get('state'))
            for key, value in patch.items():
                task[key] = copy.deepcopy(value)
                if key in task['conflicts']:
                    task['conflicts'][key]['local'] = copy.deepcopy(value)
            self._validate(task)
            self._put(task)
            self.db.execute('INSERT OR REPLACE INTO notes VALUES (?,?,?)', (task_id, str(note), note_revision + 1))
        return dict(self.get(task_id), note=str(note), note_revision=note_revision + 1)

    def note(self, task_id, text, revision):
        if not self._raw(task_id)['linked']:
            raise ValueError('只能为关联待办保存笔记')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            old = self.db.execute('SELECT text,revision FROM notes WHERE id=?', (task_id,)).fetchone()
            if revision != (old[1] if old else 0):
                raise ValueError('笔记已变化，请刷新后比较再保存')
            self.db.execute('INSERT OR REPLACE INTO notes VALUES (?,?,?)', (task_id, str(text), revision + 1))
        return {'revision': revision + 1}

    def projects(self):
        return [json.loads(row[0]) for row in self.db.execute('SELECT body FROM projects')]

    @staticmethod
    def require_delivered(task):
        if task['state'] != 'done':
            raise ValueError('请先将任务标记为“交付就绪”，再标记验收通过')

    def set_acceptance(self, task_id, revision):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            task = self._raw(task_id)
            self._check(task, revision)
            self.require_delivered(task)
            task['acceptance'] = '验收通过'
            self._put(task)
        return self.get(task_id)

    def archive_project(self, project_id, archived):
        if not isinstance(archived, bool):
            raise ValueError('无效的归档状态')
        project = next((p for p in self.projects() if p['id'] == project_id), None)
        if not project:
            raise ValueError('项目不存在')
        return self.save_project(dict(project, archived=archived))

    def delete_project(self, project_id, confirmed):
        if confirmed is not True:
            raise ValueError('请确认删除本地项目及其任务、依赖和笔记')
        with self.db:
            self.db.execute('DELETE FROM notes WHERE id IN (SELECT id FROM tasks WHERE project=?)', (project_id,))
            self.db.execute('DELETE FROM tasks WHERE project=?', (project_id,))
            self.db.execute('DELETE FROM projects WHERE id=?', (project_id,))
            self.db.execute('DELETE FROM publication_jobs WHERE project=?', (project_id,))
            self.db.execute('DELETE FROM publication_ignored WHERE project=?', (project_id,))
        return {'deleted': project_id}

    def _settings(self):
        row = self.db.execute('SELECT body FROM preferences WHERE id=1').fetchone()
        return json.loads(row[0]) if row else {'revision': 0, 'profile': {'name': '', 'owner_id': ''}, 'people': []}

    def settings(self):
        settings = self._settings()
        people = {}
        demo_projects = {p['id'] for p in self.projects() if p.get('demo')}
        demo_people = {owner['id'] for task in self._all() if task['project'] in demo_projects for owner in task['owners']}
        real_people = {owner['id'] for task in self._all() if task['project'] not in demo_projects for owner in task['owners']}
        for task in self._all():
            if task['project'] in demo_projects:
                continue
            for owner in task['owners']:
                people[owner['id']] = dict(id=owner['id'], name=owner.get('name') or owner['id'], department='')
        for person in settings['people']:
            if person['id'] in demo_people - real_people and person.get('name') == person['id']:
                continue
            people[person['id']] = dict(person)
        for person in people.values():
            person.setdefault('employment_status', 'unknown')
        settings['people'] = sorted(people.values(), key=lambda p: (p['name'], p['id']))
        return settings

    def save_settings(self, values):
        profile, people = values.get('profile'), values.get('people')
        if not isinstance(profile, dict) or any(not isinstance(profile.get(k), str) or len(profile[k]) > 200 for k in ('name', 'owner_id')):
            raise ValueError('请填写有效的使用者名称和人员 ID')
        if not isinstance(people, list):
            raise ValueError('人员配置必须是列表')
        normalized, seen = [], set()
        for person in people:
            if not isinstance(person, dict) or any(not isinstance(person.get(k, ''), str) or len(person.get(k, '')) > 200 for k in ('id', 'name', 'department')):
                raise ValueError('人员 ID、姓名和部门必须为文本且不超过 200 字')
            pid = person.get('id', '').strip()
            if not pid or pid in seen:
                raise ValueError('人员必须有唯一的稳定 ID')
            seen.add(pid)
            department = person.get('department', '').strip()
            if len(department) > 100:
                raise ValueError('部门名称不能超过 100 字')
            value = dict(id=pid, name=person.get('name', '').strip() or pid, department=department)
            if 'employment_status' in person:
                if person['employment_status'] not in ('active', 'resigned', 'unused', 'unknown'):
                    raise ValueError('人员状态必须为在职、离职、暂不使用或待确认')
                value['employment_status'] = person['employment_status']
            normalized.append(value)
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            current = self._settings()
            if values.get('revision') != current['revision']:
                raise ValueError('设置已在另一处修改，当前输入保留；请重新载入设置后再保存')
            existing = {p['id']: p for p in current['people']}
            for person in normalized:
                person.setdefault('employment_status', existing.get(person['id'], {}).get('employment_status', 'unknown'))
            updated = dict(revision=current['revision'] + 1,
                           profile={k: profile[k].strip() for k in ('name', 'owner_id')}, people=normalized)
            self.db.execute('INSERT OR REPLACE INTO preferences VALUES (1,?)', (json.dumps(updated, ensure_ascii=False),))
        return self.settings()

    def save_project(self, values):
        values = copy.deepcopy(values)
        values['id'] = values.get('id') or str(uuid.uuid4())
        previous = next((p for p in self.projects() if p['id'] == values['id']), None)
        if previous and any(values.get(k, '') != previous.get(k, '') for k in ('base_token', 'table_id')) and self._all(values['id']):
            raise ValueError('已有任务的项目不能换绑其他表，请新建项目连接')
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO projects VALUES (?,?)', (values['id'], json.dumps(values, ensure_ascii=False)))
        return values

    @staticmethod
    def pending(task):
        if not task.get('source'):
            return {}
        base = task['source'].get('base', {})
        return {k: {'before': base.get(k, '' if k == 'priority' else None), 'after': task.get(k, '')} for k in FIELDS if task.get(k, '') != base.get(k, '' if k == 'priority' else None)}

    def merge_remote(self, records, scope, project='default'):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            existing = {t['source']['record_id']: t for t in self._all(project, include_removed=True) if t.get('source') and t['source'].get('scope') == scope}
            seen = set()
            for record in records:
                record = copy.deepcopy(record)
                rid = record.pop('record_id')
                seen.add(rid)
                remote = {k: record.get(k, [] if k == 'owners' else 'todo' if k == 'state' else '') for k in FIELDS}
                if rid not in existing:
                    task = self._new_task(dict(**remote, project=project, module=record.get('module', ''), version=record.get('version', ''),
                                              acceptance=record.get('acceptance', ''), is_requirement=record.get('is_requirement', False),
                                              source={'record_id': rid, 'scope': scope, 'base': remote, 'missing': False}))
                    self._put(task)
                    existing[rid] = task
                    continue
                task = self._raw(existing[rid]['id'])
                before = copy.deepcopy(task)
                base = task['source']['base']
                for key in FIELDS:
                    local, old, new = task[key], base.get(key, '' if key == 'priority' else None), remote[key]
                    if local == new:
                        task['conflicts'].pop(key, None)
                        base[key] = new
                    elif new == old:
                        task['conflicts'].pop(key, None)
                    elif local != old and new != old:
                        task['conflicts'][key] = {'base': old, 'local': local, 'remote': new}
                    elif key not in task['conflicts']:
                        if local == old:
                            task[key] = new
                        base[key] = new
                if not task.get('module_local'):
                    task['module'] = record.get('module', task['module'])
                if not task.get('version_local'):
                    task['version'] = record.get('version', task['version'])
                task['acceptance'] = record.get('acceptance', '')
                task['is_requirement'] = task.get('published_requirement', False) or record.get('is_requirement', False)
                task['source']['missing'] = False
                if task != before:
                    self._put(task)
            for rid, task in existing.items():
                if rid not in seen:
                    current = self._raw(task['id'])
                    if not current['source'].get('missing'):
                        current['source']['missing'] = True
                        self._put(current)

    def resolve(self, task_id, field, choice, revision):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            task = self._raw(task_id)
            self._check(task, revision)
            if field not in task['conflicts'] or choice not in ('local', 'remote'):
                raise ValueError('无效的冲突选择')
            conflict = task['conflicts'].pop(field)
            if choice == 'remote':
                if field == 'state':
                    self._guard_start(task, conflict['remote'])
                task[field] = conflict['remote']
            task['source']['base'][field] = conflict['remote']
            self._put(task)
        return self.get(task_id)

    def acknowledge(self, task_id, sent):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            task = self._raw(task_id)
            task['source']['base'].update(sent)
            self._put(task)

    def candidates(self, project=None):
        tasks = [t for t in self._all(project) if not t.get('is_requirement')]
        def stage(t):
            text = t['title'].lower()
            for name, pattern in [('integrate', r'接入'), ('motion', r'动效|动画'), ('cut', r'切摆|切图|摆放'),
                                  ('ui', r'ui|效果图|界面绘制'), ('doc', r'需求文档|原型图|流程图|策划文档'), ('dev', r'逻辑|功能开发')]:
                if re.search(pattern, text):
                    return name
            return None
        result = []
        for target in tasks:
            target_stage = stage(target)
            wanted = {'dev': ['doc'], 'ui': ['doc'], 'cut': ['doc'] if target['prototypes'] else ['ui'],
                      'motion': ['cut'], 'integrate': ['dev', 'motion']}.get(target_stage, [])
            if not target['module']:
                continue
            for upstream in tasks:
                if (upstream['project'], upstream['module'], upstream['version']) != (target['project'], target['module'], target['version']):
                    continue
                if stage(upstream) not in wanted or upstream['id'] in target['upstream'] or upstream['state'] == 'closed':
                    continue
                reason = '同模块/版本，标题匹配常见交付流程；需人工确认'
                if target_stage == 'cut' and target['prototypes']:
                    reason = '已标记原型图与流程图可用，切摆可与 UI/功能开发并行，仅建议关联策划资料'
                result.append(dict(upstream=upstream['id'], downstream=target['id'], reason=reason))
        return result
