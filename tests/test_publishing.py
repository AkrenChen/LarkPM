import copy
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'backend'))
from service import Service
from workflow import save_column


class Remote:
    def __init__(self):
        self.rows = []
        self.sent = {}
        self.calls = []
        self.timeout_once = False
        self.fail_title = ''

    def status(self):
        return {}

    def records(self, project):
        return copy.deepcopy(self.rows)

    def prepare_create(self, project, values):
        pass

    def create(self, project, values, token):
        self.calls.append((copy.deepcopy(values), token))
        if values['title'] == self.fail_title:
            raise ValueError('拒绝创建')
        if token not in self.sent:
            row = dict(record_id='rec' + str(len(self.rows)), **copy.deepcopy(values))
            row['parents'] = [values['parent_id']] if values.get('parent_id') else []
            self.sent[token] = row
            self.rows.append(row)
        if self.timeout_once:
            self.timeout_once = False
            raise TimeoutError('响应超时')
        return copy.deepcopy(self.sent[token])


class PublishingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.remote = Remote()
        self.service = Service(pathlib.Path(self.temp.name) / 'db', self.remote)
        self.p = self.service.save_project(dict(name='项目', base_token='base', table_id='table'))
        self.column = save_column(self.service.w, self.p['id'], '本地需求')
        self.task = self.service.w.create(dict(project=self.p['id'], module='本地需求', title='本地任务', version='V1'))

    def tearDown(self):
        self.service.w.close()
        self.temp.cleanup()

    def submit(self, include_parent=False, task=None):
        task = task or self.service.w.get(self.task['id'])
        creations = [dict(kind='task', id=task['id'], revision=task['revision'])]
        if include_parent:
            creations.append(dict(kind='requirement', id=self.column['id'], name='本地需求'))
        return self.service.call('publish', dict(project=self.p['id'], creations=creations))

    def test_task_only_keeps_local_requirement_without_remote_parent(self):
        self.submit()
        self.assertEqual(len(self.remote.rows), 1)
        self.assertFalse(self.remote.rows[0].get('parent_id'))
        linked = self.service.w.get(self.task['id'])
        self.assertEqual(linked['module'], '本地需求')
        self.assertEqual(linked['source']['record_id'], 'rec0')
        self.assertFalse(linked['pending'])
        self.service.sync(self.p['id'])
        self.assertEqual(self.service.w.get(linked['id'])['module'], '本地需求')
        self.assertEqual(len(self.service.w.snapshot(self.p['id'])['tasks']), 1)

    def test_selected_parent_created_first_and_reused_for_later_tasks(self):
        self.submit(True)
        self.assertEqual([r['title'] for r in self.remote.rows], ['本地需求', '本地任务'])
        self.assertEqual(self.remote.rows[1]['parent_id'], self.remote.rows[0]['record_id'])
        self.assertFalse(self.remote.rows[0]['owners'])
        next_task = self.service.w.create(dict(project=self.p['id'], module='本地需求', title='后续任务'))
        self.submit(task=next_task)
        self.assertEqual(len(self.remote.rows), 3)
        self.assertEqual(self.remote.rows[2]['parent_id'], 'rec0')
        self.service.sync(self.p['id'])
        self.assertEqual(len(self.service.w.snapshot(self.p['id'])['tasks']), 2)

    def test_parent_only_remains_requirement_when_empty_after_read(self):
        self.service.call('publish', dict(project=self.p['id'], creations=[dict(kind='requirement', id=self.column['id'], name='本地需求')]))
        self.service.sync(self.p['id'])
        self.assertEqual([t['title'] for t in self.service.w.snapshot(self.p['id'])['tasks']], ['本地任务'])

    def test_timeout_retry_uses_persisted_token_and_original_payload(self):
        self.remote.timeout_once = True
        with self.assertRaisesRegex(ValueError, '超时'):
            self.submit()
        self.service.w.edit(self.task['id'], {'title': '修改后标题'}, self.service.w.get(self.task['id'])['revision'])
        self.submit()
        self.assertEqual(len(self.remote.rows), 1)
        self.assertEqual(self.remote.calls[0], self.remote.calls[1])
        linked = self.service.w.get(self.task['id'])
        self.assertEqual(linked['title'], '修改后标题')
        self.assertEqual(linked['pending']['title']['before'], '本地任务')

    def test_partial_success_does_not_repeat_parent(self):
        self.remote.fail_title = '本地任务'
        with self.assertRaisesRegex(ValueError, '已创建 1'):
            self.submit(True)
        self.remote.fail_title = ''
        self.submit()
        self.assertEqual(len(self.remote.rows), 2)
        self.assertEqual(self.remote.rows[1]['parent_id'], 'rec0')

    def test_stale_and_foreign_tasks_rejected_before_remote_call(self):
        with self.assertRaises(ValueError):
            self.submit(task=dict(self.task, revision=-1))
        other = self.service.save_project(dict(name='其他', base_token='base2', table_id='table2'))
        foreign = self.service.w.create(dict(project=other['id'], title='跨项目'))
        with self.assertRaises(ValueError):
            self.submit(task=foreign)
        self.assertFalse(self.remote.calls)

    def test_successful_task_cannot_be_created_again(self):
        self.submit()
        with self.assertRaises(ValueError):
            self.submit()
        self.assertEqual(len(self.remote.rows), 1)

    def test_timeout_then_remote_read_then_retry_keeps_one_local_task(self):
        self.remote.timeout_once = True
        with self.assertRaises(ValueError):
            self.submit()
        self.service.sync(self.p['id'])
        self.assertEqual(len(self.service.w.snapshot(self.p['id'])['tasks']), 2)
        self.submit()
        self.assertEqual(len(self.remote.rows), 1)
        self.assertEqual([t['id'] for t in self.service.w.snapshot(self.p['id'])['tasks']], [self.task['id']])

    def test_preflight_failure_creates_no_parent_or_job(self):
        def fail(*args):
            raise ValueError('字段不可写')
        self.remote.prepare_create = fail
        with self.assertRaisesRegex(ValueError, '字段不可写'):
            self.submit(True)
        self.assertFalse(self.remote.calls)
        self.assertEqual(self.service.w.db.execute('SELECT count(*) FROM publication_jobs').fetchone()[0], 0)

    def test_private_notes_and_workflow_not_in_creation_payload(self):
        linked = self.service.w.link(self.task['id'], self.task['revision'])
        self.service.w.note(linked['id'], 'private text', 0)
        self.submit()
        values = self.remote.calls[0][0]
        self.assertNotIn('note', values)
        self.assertNotIn('upstream', values)
        self.assertEqual(self.service.w.get(linked['id'])['linked'], True)
        self.assertEqual(self.service.w.db.execute('SELECT text FROM notes WHERE id=?', (linked['id'],)).fetchone()[0], 'private text')

    def test_duplicate_parents_require_choice_and_local_only_is_allowed(self):
        for number in range(2):
            self.remote.rows.extend([
                dict(record_id='parent' + str(number), title='本地需求', module='本地需求', owners=[], start='', end='', state='todo'),
                dict(record_id='existing-child' + str(number), title='已有子任务', parents=['parent' + str(number)], owners=[], start='', end='', state='todo'),
            ])
            self.service.w.create(dict(project=self.p['id'], title='本地需求', module='本地需求', is_requirement=True,
                                       source=dict(record_id='parent' + str(number), scope='base/table', base={})))
        with self.assertRaisesRegex(ValueError, '同名父需求'):
            self.submit()
        self.assertFalse(self.remote.calls)
        choice = dict(kind='task', id=self.task['id'], revision=self.task['revision'], parent_id='parent1')
        self.service.call('publish', dict(project=self.p['id'], creations=[choice]))
        self.assertEqual(self.remote.rows[-1]['parent_id'], 'parent1')
        local = self.service.w.create(dict(project=self.p['id'], title='只本地归类', module='本地需求'))
        self.service.call('publish', dict(project=self.p['id'], creations=[dict(kind='task', id=local['id'], revision=local['revision'], parent_id='')]))
        self.assertFalse(self.remote.rows[-1].get('parent_id'))
        self.assertEqual(self.service.w.get(local['id'])['module'], '本地需求')

    def test_ignore_requirement_does_not_ignore_tasks_and_is_persistent(self):
        params = dict(project=self.p['id'], kind='requirement', id=self.column['id'], ignored=True)
        self.service.call('creation_ignore', params)
        path = pathlib.Path(self.temp.name) / 'db'
        self.service.w.close()
        self.service = Service(path, self.remote)
        snapshot = self.service.call('snapshot', dict(project=self.p['id']))
        self.assertEqual([item['id'] for item in snapshot['ignored_creations']], [self.column['id']])
        self.assertEqual([item['id'] for item in snapshot['creations']], [self.task['id']])
        self.assertFalse(self.remote.calls)
        self.submit()
        self.assertFalse(self.remote.rows[0].get('parent_id'))
        self.service.call('creation_ignore', dict(params, ignored=False))
        snapshot = self.service.call('snapshot', dict(project=self.p['id']))
        self.assertEqual([item['id'] for item in snapshot['creations']], [self.column['id']])
        self.assertFalse(snapshot['ignored_creations'])

    def test_candidates_newest_first_even_after_editing_older_task(self):
        newer = self.service.w.create(dict(project=self.p['id'], title='新任务'))
        self.service.w.edit(self.task['id'], {'title': '旧任务改名'}, self.task['revision'])
        items = self.service.call('snapshot', dict(project=self.p['id']))['creations']
        self.assertEqual([item['id'] for item in items], [newer['id'], self.task['id'], self.column['id']])

    def test_retry_token_survives_backend_restart(self):
        self.remote.timeout_once = True
        with self.assertRaises(ValueError):
            self.submit()
        self.service.w.close()
        self.service = Service(pathlib.Path(self.temp.name) / 'db', self.remote)
        self.submit()
        self.assertEqual(len(self.remote.rows), 1)
        self.assertEqual(self.remote.calls[0], self.remote.calls[1])


if __name__ == '__main__':
    unittest.main()
