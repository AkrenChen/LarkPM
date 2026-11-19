import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'backend'))
from workspace import Workspace, Conflict
from workflow import arrange, save_column, archive_column


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = pathlib.Path(self.temp.name) / 'db'
        self.w = Workspace(self.path)
        self.tasks = [self.w.create(dict(project='p', module='S', title=name)) for name in ['文档', '开发', 'UI', '接入']]

    def tearDown(self):
        self.w.close()
        self.temp.cleanup()

    def test_unclassified_auto_stages_do_not_link_other_versions(self):
        old = self.w.create(dict(project='p', title='Old', version='v1'))
        first = self.w.create(dict(project='p', title='First', version='v2'))
        last = self.w.create(dict(project='p', title='Last', version='v2'))
        arrange(self.w, 'p', [dict(module='', stages=[[old['id']], [first['id']], [last['id']]])], {t['id']: t['revision'] for t in (old, first, last)})
        self.assertEqual(self.w.get(first['id'])['upstream'], [])
        self.assertEqual(self.w.get(last['id'])['upstream'], [first['id']])

    def test_version_scoped_arrangement_keeps_hidden_tasks_and_explicit_external_edges(self):
        old = self.w.create(dict(project='p', title='Old', version='v1'))
        first = self.w.create(dict(project='p', title='First', version='v2'))
        last = self.w.create(dict(project='p', title='Last', version='v2'), upstream=[old['id']])
        arrange(self.w, 'p', [dict(module='', stages=[[first['id']], [last['id']]])], {t['id']: t['revision'] for t in (first, last)}, version='v2')
        self.assertEqual(self.w.get(old['id'])['revision'], old['revision'])
        self.assertEqual(self.w.get(last['id'])['upstream'], [old['id'], first['id']])

    def save(self, stages, systems=None, revisions=None):
        return arrange(self.w, 'p', systems or [dict(module='S', stages=stages)], revisions or {t['id']: t['revision'] for t in self.w.snapshot('p')['tasks']})

    def test_serial_parallel_atomic_and_persistent(self):
        a, b, c, d = [t['id'] for t in self.tasks]
        self.save([[a], [b, c], [d]])
        self.assertEqual(self.w.get(b)['upstream'], [a])
        self.assertEqual(self.w.get(c)['upstream'], [a])
        self.assertEqual(self.w.get(d)['upstream'], [b, c])
        self.assertEqual(self.w.get(c)['workflow_stage'], 1)
        with self.assertRaisesRegex(ValueError, '上游'):
            self.w.edit(b, {'state': 'active'}, self.w.get(b)['revision'])
        self.w.edit(a, {'state': 'done'}, self.w.get(a)['revision'])
        self.w.edit(b, {'state': 'active'}, self.w.get(b)['revision'])
        self.w.edit(a, {'state': 'todo'}, self.w.get(a)['revision'])
        self.assertEqual(self.w.get(b)['state'], 'active')
        self.assertEqual(self.w.get(b)['readiness'], 'blocked')
        self.w.close()
        self.w = Workspace(self.path)
        self.assertEqual(self.w.get(d)['upstream'], [b, c])

    def test_cross_system_and_external_dependency_preserved(self):
        a, b, c, d = [t['id'] for t in self.tasks]
        external = self.w.create(dict(project='p', module='X', title='外部'))
        self.w.dependencies(a, [external['id']], self.w.get(a)['revision'])
        self.save([], systems=[dict(module='S', stages=[[a], [b, c]]), dict(module='T', stages=[[d]])])
        self.assertEqual(self.w.get(a)['upstream'], [external['id']])
        self.assertEqual(self.w.get(d)['module'], 'T')
        self.assertEqual(self.w.get(d)['upstream'], [])

    def test_partial_duplicate_cycle_and_stale_changes_are_atomic(self):
        a, b, c, d = [t['id'] for t in self.tasks]
        before = self.w.snapshot('p')
        for stages in [[[a], [b]], [[a, b], [c, d, d]]]:
            with self.assertRaises(ValueError): self.save(stages)
            self.assertEqual(self.w.snapshot('p'), before)
        ext = self.w.create(dict(project='p', module='X', title='外部'))
        self.w.dependencies(ext['id'], [d], ext['revision'])
        self.w.dependencies(a, [ext['id']], self.w.get(a)['revision'])
        before = self.w.snapshot('p')
        with self.assertRaisesRegex(ValueError, '循环'): self.save([[a], [b, c], [d]])
        self.assertEqual(self.w.snapshot('p'), before)
        revisions = {t['id']: t['revision'] for t in before['tasks']}
        self.w.edit(b, {'title': '新内容'}, self.w.get(b)['revision'])
        with self.assertRaises(Conflict): self.save([[a], [b, c], [d]], revisions=revisions)
        self.assertIsNone(self.w.get(d)['workflow_stage'])

    def test_manual_system_survives_remote_refresh(self):
        self.w.merge_remote([dict(record_id='r', title='需求', module='源模块', state='todo')], 'scope', 'remote')
        t = self.w.snapshot('remote')['tasks'][0]
        self.w.edit(t['id'], {'module': '本地系统'}, t['revision'])
        self.w.merge_remote([dict(record_id='r', title='需求', module='新的源模块', state='todo')], 'scope', 'remote')
        self.assertEqual(self.w.get(t['id'])['module'], '本地系统')

    def test_empty_column_rename_and_priority_persist(self):
        self.w.save_project(dict(id='p', name='项目'))
        column = save_column(self.w, 'p', '新需求', 'high')
        self.assertEqual(self.w.projects()[0]['workflow_columns'][0]['priority'], 'high')
        a, b, c, d = [t['id'] for t in self.tasks]
        self.save([], systems=[dict(module='S', stages=[[b, c, d]]), dict(module='新需求', stages=[[a]])])
        save_column(self.w, 'p', '重命名', 'low', column['id'])
        self.assertEqual(self.w.get(a)['module'], '重命名')
        self.assertTrue(self.w.get(a)['module_local'])
        self.w.close()
        self.w = Workspace(self.path)
        self.assertEqual(self.w.projects()[0]['workflow_columns'][0]['name'], '重命名')
        with self.assertRaises(ValueError): save_column(self.w, 'p', 'S')
        with self.assertRaises(ValueError): save_column(self.w, 'p', '未归类')

    def test_manual_archive_requires_completion_and_records_exact_tasks(self):
        self.w.save_project(dict(id='p', name='项目'))
        with self.assertRaisesRegex(ValueError, '所有任务完成'):
            archive_column(self.w, 'p', 'S')
        for task in self.tasks:
            self.w.edit(task['id'], {'state': 'done'}, self.w.get(task['id'])['revision'])
        self.assertFalse(self.w.projects()[0].get('workflow_columns'))
        archived = archive_column(self.w, 'p', 'S')
        self.assertEqual(set(archived['archived_tasks']), {t['id'] for t in self.tasks})
        save_column(self.w, 'p', '更名', 'high', archived['id'])
        self.w.close()
        self.w = Workspace(self.path)
        saved = self.w.projects()[0]['workflow_columns'][0]
        self.assertEqual(saved['archived_tasks'], archived['archived_tasks'])
        added = self.w.create(dict(project='p', module='更名', title='追加任务'))
        self.assertNotIn(added['id'], saved['archived_tasks'])
        with self.assertRaisesRegex(ValueError, '所有任务完成'):
            archive_column(self.w, 'p', '更名')

    def test_empty_requirement_can_archive_but_unknown_requirement_cannot(self):
        self.w.save_project(dict(id='p', name='项目'))
        column = save_column(self.w, 'p', '空需求')
        archived = archive_column(self.w, 'p', '空需求')
        self.assertEqual(archived['id'], column['id'])
        self.assertEqual(archived['archived_tasks'], [])
        self.w.close()
        self.w = Workspace(self.path)
        self.assertEqual(self.w.projects()[0]['workflow_columns'][0]['archived_tasks'], [])
        with self.assertRaisesRegex(ValueError, '需求不存在'):
            archive_column(self.w, 'p', '不存在')
        task = self.w.create(dict(project='p', module='空需求', title='新任务'))
        with self.assertRaisesRegex(ValueError, '所有任务完成'):
            archive_column(self.w, 'p', '空需求')
        self.assertEqual(self.w.get(task['id'])['state'], 'todo')

    def test_linkin_and_conflict_cannot_bypass_start_guard(self):
        a, b, c, d = [t['id'] for t in self.tasks]
        self.save([[a], [b, c], [d]])
        task = self.w.link(b, self.w.get(b)['revision'])
        with self.assertRaisesRegex(ValueError, '上游'):
            self.w.linkin_save(b, {'state': 'active'}, task['revision'], '笔记', 0)
        self.assertIsNone(self.w.db.execute('SELECT * FROM notes WHERE id=?', (b,)).fetchone())
        raw = self.w._raw(b)
        raw['source'] = {'base': {'state': 'todo'}}
        raw['conflicts']['state'] = {'base': 'todo', 'local': 'todo', 'remote': 'active'}
        with self.w.db: self.w._put(raw)
        with self.assertRaisesRegex(ValueError, '上游'):
            self.w.resolve(b, 'state', 'remote', self.w.get(b)['revision'])
        self.assertIn('state', self.w.get(b)['conflicts'])

    def test_private_branch_does_not_gate_common_downstream(self):
        a, b, c, d = [t['id'] for t in self.tasks]
        branch = self.w.branch(b, {'title': '开发单独下游'})
        later = self.w.create(dict(project='p', module='S', title='下下游'))
        system = dict(module='S', stages=[[a, b, c], [d], [later['id']]], branches={b: [branch['id']]})
        self.save([], systems=[system])
        self.assertEqual(self.w.get(branch['id'])['upstream'], [b])
        self.assertEqual(self.w.get(branch['id'])['workflow_parent'], b)
        self.assertEqual(self.w.get(d)['upstream'], [a, b, c])
        self.assertEqual(self.w.get(later['id'])['upstream'], [d])
        self.w.edit(b, {'state': 'done'}, self.w.get(b)['revision'])
        self.assertEqual(self.w.get(branch['id'])['readiness'], 'ready')
        with self.assertRaisesRegex(ValueError, '上游'):
            self.w.edit(d, {'state': 'active'}, self.w.get(d)['revision'])
        for task_id in (a, c):
            self.w.edit(task_id, {'state': 'done'}, self.w.get(task_id)['revision'])
        self.w.edit(d, {'state': 'active'}, self.w.get(d)['revision'])
        self.assertEqual(self.w.get(branch['id'])['state'], 'todo')
        self.w.close()
        self.w = Workspace(self.path)
        self.assertEqual(self.w.get(branch['id'])['workflow_parent'], b)
        self.assertEqual(self.w.get(d)['state'], 'active')

    def test_nested_branch_invalid_layout_and_stale_write_are_atomic(self):
        a, b, c, d = [t['id'] for t in self.tasks]
        branches = {b: [c], c: [d]}
        system = dict(module='S', stages=[[a, b]], branches=branches)
        self.save([], systems=[system])
        self.assertEqual(self.w.get(d)['upstream'], [c])
        before = self.w.snapshot('p')
        for invalid in ({b: [c], c: [b, d]}, {'missing': [c, d]}, {b: [c, c, d]}, {b: 'bad'}):
            with self.assertRaises(ValueError):
                self.save([], systems=[dict(module='S', stages=[[a, b]], branches=invalid)])
            self.assertEqual(self.w.snapshot('p'), before)
        stale = {t['id']: t['revision'] for t in before['tasks']}
        self.w.edit(c, {'title': '分支被另一端改过'}, self.w.get(c)['revision'])
        with self.assertRaises(Conflict):
            self.save([], systems=[system], revisions=stale)


if __name__ == '__main__': unittest.main()
