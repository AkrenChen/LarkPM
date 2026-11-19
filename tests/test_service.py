import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'backend'))
from service import Service


class Remote:
    def __init__(self):
        self.rows = [dict(record_id='rec1', title='需求', start='', end='', owners=[], state='todo', module='系统', version='v1')]
        self.writes = []

    def status(self):
        return {'configured': True, 'authorized': True}

    def records(self, config):
        return self.rows

    def update(self, config, record_id, patch):
        self.writes.append((config['table_id'], record_id, patch))
        self.rows[0].update(patch)

    def accept(self, config, record_id):
        self.update(config, record_id, {'acceptance': '验收通过'})


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.remote = Remote()
        self.s = Service(pathlib.Path(self.temp.name) / 'workspace.db', self.remote)
        self.p = self.s.call('project_save', dict(name='测试', url='https://example.feishu.cn/base/baseABC?table=tblABC'))
        self.s.call('sync', {'project': self.p['id']})

    def tearDown(self):
        self.s.w.close()
        self.temp.cleanup()

    def test_project_settings_save_preserves_local_columns(self):
        column = self.s.call('workflow_column_save', dict(project=self.p['id'], name='新系统', priority='high'))
        self.s.call('project_save', dict(self.p, name='新项目名称'))
        self.assertEqual(self.s.project(self.p['id'])['workflow_columns'], [column])
        self.assertEqual(self.remote.writes, [])

    def test_accept_writes_only_acceptance_then_sync_preserves_it(self):
        task = self.s.w.snapshot(self.p['id'])['tasks'][0]
        task = self.s.w.edit(task['id'], {'title': 'local title'}, task['revision'])
        accepted = self.s.call('task_accept', dict(id=task['id'], revision=task['revision']))
        self.assertEqual(accepted['acceptance'], '验收通过')
        self.assertEqual(self.remote.writes, [('tblABC', 'rec1', {'acceptance': '验收通过'})])
        self.assertEqual(set(accepted['pending']), {'title'})
        self.s.sync(self.p['id'])
        self.assertEqual(self.s.w.get(task['id'])['acceptance'], '验收通过')

    def test_accept_failure_stale_revision_and_missing_source_do_not_mark_local(self):
        task = self.s.w.snapshot(self.p['id'])['tasks'][0]
        with self.assertRaises(ValueError):
            self.s.call('task_accept', dict(id=task['id'], revision=task['revision'] - 1))
        self.assertFalse(self.remote.writes)
        def fail(*args):
            raise ValueError('write denied')
        self.remote.accept = fail
        with self.assertRaisesRegex(ValueError, 'write denied'):
            self.s.call('task_accept', dict(id=task['id'], revision=task['revision']))
        self.assertNotEqual(self.s.w.get(task['id']).get('acceptance'), '验收通过')
        self.remote.rows = []
        self.s.sync(self.p['id'])
        task = self.s.w.get(task['id'])
        with self.assertRaisesRegex(ValueError, '来源记录不可用'):
            self.s.call('task_accept', dict(id=task['id'], revision=task['revision']))

    def test_local_task_accept_never_calls_remote(self):
        task = self.s.w.create(dict(project=self.p['id'], title='local'))
        accepted = self.s.call('task_accept', dict(id=task['id'], revision=task['revision']))
        self.assertEqual(accepted['acceptance'], '验收通过')
        self.assertFalse(self.remote.writes)

    def test_archive_restore_and_delete_project_are_local_and_isolated(self):
        task = self.s.w.snapshot(self.p['id'])['tasks'][0]
        task = self.s.w.link(task['id'], task['revision'])
        self.s.w.note(task['id'], 'private', 0)
        other = self.s.save_project(dict(name='other', base_token='base2', table_id='tbl2'))
        retained = self.s.w.create(dict(title='keep', project=other['id']))
        retained = self.s.w.link(retained['id'], retained['revision'])
        self.s.w.note(retained['id'], 'keep note', 0)
        self.s.call('project_archive', dict(project=self.p['id'], archived=True))
        self.assertTrue(self.s.project(self.p['id'])['archived'])
        self.assertEqual(self.s.w.get(task['id'])['title'], task['title'])
        self.s.call('project_archive', dict(project=self.p['id'], archived=False))
        self.assertFalse(self.s.project(self.p['id'])['archived'])
        with self.assertRaises(ValueError):
            self.s.call('project_delete', dict(project=self.p['id']))
        self.s.w.remove_local(task['id'], task['revision'])
        self.s.call('project_delete', dict(project=self.p['id'], confirmed=True))
        self.assertFalse(self.s.w._all(self.p['id'], include_removed=True))
        self.assertIsNone(self.s.w.db.execute('SELECT id FROM notes WHERE id=?', (task['id'],)).fetchone())
        self.assertEqual(self.s.w.get(retained['id'])['title'], 'keep')
        self.assertIsNotNone(self.s.w.db.execute('SELECT id FROM notes WHERE id=?', (retained['id'],)).fetchone())
        self.assertEqual([p['id'] for p in self.s.w.projects()], [other['id']])
        self.assertFalse(self.remote.writes)

    def test_only_selected_fields_written_and_unselected_changes_remain_pending(self):
        t = self.s.call('snapshot', {'project': self.p['id']})['tasks'][0]
        t = self.s.call('edit', dict(id=t['id'], patch={'title': '新需求', 'end': '2026-12-01'}, revision=t['revision']))
        self.assertEqual(self.remote.writes, [])
        result = self.s.call('write', dict(project=self.p['id'], selections=[dict(id=t['id'], fields=['title'], revision=t['revision'])]))
        self.assertEqual(result['written'], 1)
        self.assertEqual(self.remote.writes[0][2], {'title': '新需求'})
        self.assertEqual(set(self.s.w.get(t['id'])['pending']), {'end'})

    def test_global_settings_route_and_department_override_never_write_remote(self):
        settings = self.s.call('snapshot', {'project': self.p['id']})['settings']
        self.s.call('settings_save', dict(revision=settings['revision'], profile={'name': 'Me', 'owner_id': 'ou_1'},
                                         people=[{'id': 'ou_1', 'name': 'Me', 'department': 'UI'}]))
        task = self.s.w.snapshot(self.p['id'])['tasks'][0]
        task = self.s.call('edit', dict(id=task['id'], revision=task['revision'], patch={'department_override': ['Special']}))
        self.assertEqual(task['pending'], {})
        self.s.call('sync', {'project': self.p['id']})
        self.assertEqual(self.s.w.get(task['id'])['departments'], ['Special'])
        self.assertEqual(self.remote.writes, [])
        self.assertEqual(self.s.call('snapshot', {})['settings']['profile']['owner_id'], 'ou_1')

    def test_contact_endpoints_closed_and_table_sync_does_not_query_contacts(self):
        calls = []
        self.remote.contacts = lambda ids: calls.append(ids)
        for method in ('contacts_sync', 'contacts_authorize'):
            with self.subTest(method=method), self.assertRaisesRegex(ValueError, '已关闭'):
                self.s.call(method, {})
        self.s.call('sync', {'project': self.p['id']})
        self.assertEqual(calls, [])

    def test_remote_conflict_blocks_write_and_preserves_both_values(self):
        t = self.s.w.snapshot()['tasks'][0]
        t = self.s.w.edit(t['id'], {'title': '本地'}, t['revision'])
        self.remote.rows[0]['title'] = '远端'
        with self.assertRaises(ValueError):
            self.s.call('write', dict(project=self.p['id'], selections=[dict(id=t['id'], fields=['title'], revision=t['revision'])]))
        self.assertEqual(self.remote.writes, [])
        self.assertIn('title', self.s.w.get(t['id'])['conflicts'])

    def test_wrong_project_and_local_task_cannot_be_written(self):
        local = self.s.w.create(dict(title='私人分支', project=self.p['id']))
        with self.assertRaises(ValueError):
            self.s.call('write', dict(project=self.p['id'], selections=[dict(id=local['id'], fields=['title'], revision=local['revision'])]))
        other = self.s.call('project_save', dict(name='另一个', base_token='base2', table_id='tbl2'))
        t = next(t for t in self.s.w.snapshot()['tasks'] if t['source'])
        with self.assertRaises(ValueError):
            self.s.call('write', dict(project=other['id'], selections=[dict(id=t['id'], fields=['title'], revision=t['revision'])]))
        self.assertFalse(self.remote.writes)

    def test_project_connection_can_be_configured_but_not_rebound_with_tasks(self):
        self.assertEqual(self.p['base_token'], 'baseABC')
        self.assertEqual(self.p['table_id'], 'tblABC')
        with self.assertRaises(ValueError):
            self.s.call('project_save', dict(self.p, table_id='tblOTHER'))

    def test_unassigned_parent_is_requirement_and_children_are_tasks(self):
        self.remote.rows = [dict(record_id='parent', title='活动模块', state='todo', owners=[]),
                            dict(record_id='child', title='切摆', state='todo', owners=[], parents=['parent'])]
        self.s.call('sync', {'project': self.p['id']})
        tasks = {t['source']['record_id']: t for t in self.s.w.snapshot(self.p['id'])['tasks']}
        self.assertNotIn('parent', tasks)
        self.assertEqual(tasks['child']['module'], '活动模块')
        self.assertFalse(tasks['child']['upstream'])
        child = tasks['child']
        self.s.call('workflow_arrange', dict(project=self.p['id'], systems=[dict(module='活动模块', stages=[[child['id']]])],
                                            revisions={child['id']: child['revision']}))
        raw_parent = next(t for t in self.s.w._all(self.p['id']) if t['source']['record_id'] == 'parent')
        self.assertTrue(raw_parent['is_requirement'])
        self.assertEqual(self.remote.writes, [])

    def test_parent_classification_updates_existing_tasks_and_preserves_standalone_unassigned(self):
        self.remote.rows = [dict(record_id='parent', title='系统', owners=[dict(id='owner')], state='todo'),
                            dict(record_id='child', title='子任务', owners=[], state='todo', parents=['parent']),
                            dict(record_id='standalone', title='待分配', owners=[], state='todo')]
        self.s.sync(self.p['id'])
        def visible():
            return {t['source']['record_id']: t for t in self.s.w.snapshot(self.p['id'])['tasks'] if not t['source']['missing']}
        parent_id = visible()['parent']['id']
        self.remote.rows[0]['owners'] = []
        self.s.sync(self.p['id'])
        self.assertNotIn('parent', visible())
        self.assertIn('standalone', visible())
        self.remote.rows[0]['owners'] = [dict(id='owner')]
        self.s.sync(self.p['id'])
        self.assertEqual(visible()['parent']['id'], parent_id)


if __name__ == '__main__':
    unittest.main()
