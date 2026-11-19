import copy
import json
import time
import uuid

from personal_board import QUADRANTS, settings

FIELDS = ('text', 'priority', 'completed')


class PersonalNotes:
    def __init__(self, workspace):
        self.w = workspace
        self.w.db.execute('CREATE TABLE IF NOT EXISTS personal_notes (id TEXT PRIMARY KEY, body TEXT NOT NULL)')
        self.w.db.commit()

    def all(self):
        return [json.loads(row[0]) for row in self.w.db.execute('SELECT body FROM personal_notes ORDER BY rowid DESC')]

    def put(self, note):
        with self.w.db:
            if not self.w.db.in_transaction:
                self.w.db.execute('BEGIN IMMEDIATE')
            previous = self.w.db.execute('SELECT body FROM personal_notes WHERE id=?', (note['id'],)).fetchone()
            if previous:
                current = json.loads(previous[0])
                if current == note:
                    return note
                if current['revision'] != note.get('revision'):
                    raise ValueError('待办在同步期间发生变化，保留本地修改，稍后重试')
            note['revision'] = str(int(note.get('revision', '0')) + 1)
            note['update_at'] = time.time_ns() // 1000
            self.w.db.execute('INSERT OR REPLACE INTO personal_notes VALUES (?,?)', (note['id'], json.dumps(note, ensure_ascii=False)))
        return note

    @staticmethod
    def values(note):
        return {key: note.get(key, False if key == 'completed' else '') for key in FIELDS}

    def mutate(self, action, params):
        if action not in ('save', 'move', 'complete', 'resolve'):
            raise ValueError('不支持的个人待办操作')
        with self.w.db:
            self.w.db.execute('BEGIN IMMEDIATE')
            if params.get('id'):
                note = next((n for n in self.all() if n['id'] == params['id']), None)
                if not note or note['revision'] != str(params.get('revision')):
                    raise ValueError('待办已变化，请刷新后重试；当前输入已保留')
                if note.get('completed') and not note.get('conflict'):
                    raise ValueError('待办已经完成')
            elif action == 'save':
                note = dict(id='local-' + str(uuid.uuid4()), text='', priority='nuni', completed=False, editable=True, recurring=False, revision='0', source=None)
            else:
                raise ValueError('缺少待办编号')
            if action == 'resolve':
                conflict = note.get('conflict')
                if not conflict or params.get('choice') not in ('local', 'remote'):
                    raise ValueError('请选择保留本地或采用 LinkinNotes')
                if params['choice'] == 'remote':
                    note.update(conflict)
                elif conflict['completed']:
                    raise ValueError('远端待办已完成或删除，请采用远端结果，再按需新建本地待办')
                note['source']['base'] = conflict
                note.pop('conflict', None)
            elif action == 'complete':
                if note.get('recurring'):
                    raise ValueError('重复待办请在 LinkinNotes 中完成')
                note['completed'] = True
            else:
                if action == 'save':
                    text = params.get('text', '')
                    if not isinstance(text, str) or not text.strip() or len(text) > 10000:
                        raise ValueError('请输入待办内容，最多 10000 字')
                    if not note.get('editable', True) and text.strip() != note['text']:
                        raise ValueError('富文本待办请在 LinkinNotes 中编辑')
                    note['text'] = text.strip()
                priority = params.get('priority', note['priority'])
                if priority not in QUADRANTS:
                    raise ValueError('无效的象限')
                note['priority'] = priority
            return self.put(note)

    def synchronize(self, bridge):
        result = bridge.call('tasks')
        account = result['account']
        remote = {row['id']: row for row in result['tasks']}
        linked = {(n['source']['account'], n['source']['id']): n for n in self.all() if n.get('source')}
        for row in result['tasks']:
            key = (account, row['id'])
            if key not in linked:
                note = dict(id='local-' + str(uuid.uuid4()), text=row['text'], priority=row['priority'], completed=False, editable=row['editable'], recurring=row['recurring'], revision='0', source=dict(account=account, id=row['id'], base=self.values(row)))
                self.put(note)
        writes = False
        for note in self.all():
            if not settings(self.w)['sync']:
                break
            source = note.get('source')
            if source and source['account'] != account:
                continue
            if note.get('create_uncertain'):
                continue
            if source:
                row = remote.get(source['id'])
                if row is None and (result.get('pending') or result.get('failed')):
                    continue
                incoming = self.values(row) if row else dict(source['base'], completed=True)
                desired, base = self.values(note), source['base']
                if note.get('conflict') and incoming == note['conflict']:
                    continue
                if any(desired[key] != base[key] and incoming[key] != base[key] and desired[key] != incoming[key] for key in FIELDS) or (incoming['completed'] and desired != base and not desired['completed']):
                    note['conflict'] = incoming
                    self.put(note)
                    continue
                for key in FIELDS:
                    if desired[key] == base[key]:
                        note[key] = incoming[key]
                source['base'] = incoming
                note.pop('conflict', None)
                if row:
                    note.update(editable=row['editable'], recurring=row['recurring'])
                self.put(note)
                desired = self.values(note)
                if desired == incoming or not row:
                    continue
                params = dict(row, account=account, text=note['text'], priority=note['priority'])
                bridge.call('complete' if note['completed'] else 'save', params)
                note['source']['base'] = desired
                self.put(note)
                writes = True
            elif not note['completed']:
                # A lost create response cannot be safely retried by this legacy API.
                note['create_uncertain'] = True
                self.put(note)
                response = bridge.call('save', dict(account=account, text=note['text'], priority=note['priority']))
                note['source'] = dict(account=account, id=response['id'], base=self.values(note))
                note.pop('create_uncertain', None)
                self.put(note)
                writes = True
        return result, writes

    def snapshot(self, bridge=None):
        error, pending, failed = '', 0, 0
        if settings(self.w)['sync'] and bridge:
            try:
                remote, _ = self.synchronize(bridge)
                pending, failed = remote.get('pending', 0), remote.get('failed', 0)
            except Exception:
                error = 'LinkinNotes 暂不可用，待办已保存在本地，恢复连接后继续同步'
        notes = self.all()
        uncertain = sum(bool(n.get('create_uncertain')) for n in notes)
        if uncertain:
            error = f'{uncertain} 项新增同步结果未确认，请先在 LinkinNotes 核对；本地内容已保留，暂不重复创建'
        return dict(account='local', tasks=[copy.deepcopy(n) for n in notes if not n['completed'] or n.get('conflict')], pending=pending, failed=failed, sync_error=error)
