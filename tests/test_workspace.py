import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'backend'))
from workspace import Workspace, Conflict


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.w = Workspace(pathlib.Path(self.temp.name) / 'workspace.db')

    def tearDown(self):
        self.w.close()
        self.temp.cleanup()

    def task(self, title='任务', **kw):
        return self.w.create(dict(title=title, **kw))

    def test_remove_local_detaches_dependents_preserves_branches_and_notes(self):
        parent = self.task('旧任务')
        child = self.w.branch(parent['id'], {'title': '分支'})
        with self.w.db:
            self.w.db.execute('INSERT INTO notes VALUES (?,?,?)', (parent['id'], 'private note', 1))
        with self.assertRaises(Conflict):
            self.w.remove_local(parent['id'], parent['revision'] - 1)
        self.assertEqual(len(self.w.snapshot()['tasks']), 2)
        self.w.remove_local(parent['id'], parent['revision'])
        self.assertEqual([t['id'] for t in self.w.snapshot()['tasks']], [child['id']])
        current = self.w.get(child['id'])
        self.assertEqual(current['upstream'], [])
        self.assertIsNone(current['branch_of'])
        self.assertEqual(current['readiness'], 'ready')
        self.assertEqual(self.w.db.execute('SELECT text FROM notes WHERE id=?', (parent['id'],)).fetchone()[0], 'private note')
        self.assertTrue(self.w._raw(parent['id'])['locally_removed'])

    def test_removed_remote_task_is_not_reimported_and_survives_reopen(self):
        row = dict(record_id='rec-remove', title='旧记录', state='todo')
        self.w.merge_remote([row], 'scope')
        task = self.w.snapshot()['tasks'][0]
        self.w.remove_local(task['id'], task['revision'])
        self.w.merge_remote([], 'scope')
        self.w.merge_remote([dict(row, title='再次可见')], 'scope')
        self.assertEqual(self.w.snapshot()['tasks'], [])
        self.assertEqual(len(self.w._all(include_removed=True)), 1)
        self.w.close()
        self.w = Workspace(pathlib.Path(self.temp.name) / 'workspace.db')
        self.assertEqual(self.w.snapshot()['tasks'], [])

    def test_acceptance_refresh_does_not_write_back_or_complete_local_tasks(self):
        row = dict(record_id='rec1', title='任务', state='active', acceptance='验收通过')
        self.w.merge_remote([row], 'scope')
        task = self.w.snapshot()['tasks'][0]
        self.assertEqual(task['acceptance'], '验收通过')
        self.assertEqual(task['state'], 'active')
        self.assertNotIn('acceptance', task['pending'])
        row['acceptance'] = '验收未通过'
        self.w.merge_remote([row], 'scope')
        self.assertEqual(self.w.get(task['id'])['acceptance'], '验收未通过')
        row.pop('acceptance')
        self.w.merge_remote([row], 'scope')
        self.assertEqual(self.w.get(task['id'])['acceptance'], '')

    def test_completion_releases_dependency_and_reopen_blocks_without_resetting_downstream(self):
        a, b = self.task(), self.task('接入', state='active')
        self.w.dependencies(b['id'], [a['id']], b['revision'])
        self.assertEqual(self.w.get(b['id'])['readiness'], 'blocked')
        a = self.w.edit(a['id'], {'state': 'done'}, a['revision'])
        self.assertEqual(self.w.get(b['id'])['readiness'], 'ready')
        self.w.edit(a['id'], {'state': 'active'}, a['revision'])
        self.assertEqual(self.w.get(b['id'])['state'], 'active')
        self.assertEqual(self.w.get(b['id'])['readiness'], 'blocked')

    def test_cycle_is_rejected_and_original_graph_preserved(self):
        a, b = self.task(), self.task('另一个')
        b = self.w.dependencies(b['id'], [a['id']], b['revision'])
        with self.assertRaises(ValueError):
            self.w.dependencies(a['id'], [b['id']], a['revision'])
        self.assertEqual(self.w.get(a['id'])['upstream'], [])

    def test_stale_edit_returns_current_value_and_does_not_overwrite(self):
        task = self.task()
        self.w.edit(task['id'], {'title': '另一端修改'}, task['revision'])
        with self.assertRaises(Conflict):
            self.w.edit(task['id'], {'title': '我的输入'}, task['revision'])
        self.assertEqual(self.w.get(task['id'])['title'], '另一端修改')

    def test_linking_is_idempotent_and_notes_never_appear_in_larkpm_snapshot(self):
        task = self.task()
        linked = self.w.link(task['id'], task['revision'])
        self.w.link(task['id'], linked['revision'])
        self.w.note(task['id'], '私人笔记', 0)
        self.assertEqual(len(self.w.linkin_snapshot()['tasks']), 1)
        self.assertNotIn('私人笔记', str(self.w.snapshot()))
        self.assertEqual(self.w.linkin_snapshot()['tasks'][0]['note'], '私人笔记')

    def test_local_branch_has_no_remote_source_and_depends_on_origin(self):
        task = self.task(source={'record_id': 'rec1', 'base': {}})
        child = self.w.branch(task['id'], {'title': '补充工作'})
        self.assertIsNone(child['source'])
        self.assertEqual(child['upstream'], [task['id']])
        self.assertEqual(child['branch_of'], task['id'])

    def test_linkin_edit_is_restricted_to_explicitly_linked_tasks(self):
        task = self.task()
        with self.assertRaises(ValueError):
            self.w.linkin_edit(task['id'], {'state': 'done'}, task['revision'])
        linked = self.w.link(task['id'], task['revision'])
        self.w.linkin_edit(task['id'], {'state': 'done'}, linked['revision'])
        self.assertEqual(self.w.get(task['id'])['state'], 'done')

    def test_remote_merge_does_not_overwrite_local_edits_and_reports_conflict(self):
        remote = dict(record_id='rec1', title='原始标题', start='', end='', owners=[], state='todo', module='系统', version='v1')
        self.w.merge_remote([remote], 'base/table')
        task = self.w.snapshot()['tasks'][0]
        self.w.edit(task['id'], {'title': '本地标题'}, task['revision'])
        self.w.merge_remote([dict(remote, title='远端标题', end='2026-11-09')], 'base/table')
        current = self.w.get(task['id'])
        self.assertEqual(current['title'], '本地标题')
        self.assertEqual(current['end'], '2026-11-09')
        self.assertEqual(current['conflicts']['title']['remote'], '远端标题')

    def test_rule_candidates_allow_cutting_in_parallel_with_ui_when_prototypes_exist(self):
        doc = self.task('需求文档', module='新系统')
        ui = self.task('UI绘制', module='新系统')
        cut = self.task('切摆', module='新系统', prototypes=True)
        candidates = self.w.candidates()
        pairs = {(c['upstream'], c['downstream']) for c in candidates}
        self.assertIn((doc['id'], cut['id']), pairs)
        self.assertNotIn((ui['id'], cut['id']), pairs)

    def test_same_record_id_in_two_projects_never_shares_edits_or_dependencies(self):
        remote = dict(record_id='rec1', title='需求', state='todo', owners=[])
        self.w.merge_remote([remote], 'base/table', 'project1')
        self.w.merge_remote([remote], 'base/table', 'project2')
        a = self.w.snapshot('project1')['tasks'][0]
        b = self.w.snapshot('project2')['tasks'][0]
        self.assertNotEqual(a['id'], b['id'])
        self.w.edit(a['id'], {'state': 'done'}, a['revision'])
        self.assertEqual(self.w.get(b['id'])['state'], 'todo')
        with self.assertRaises(ValueError):
            self.w.dependencies(a['id'], [b['id']], self.w.get(a['id'])['revision'])

    def test_resolve_remote_conflict_retains_local_until_explicit_user_choice(self):
        remote = dict(record_id='rec1', title='原始', state='todo', owners=[])
        self.w.merge_remote([remote], 'base/table')
        t = self.w.snapshot()['tasks'][0]
        self.w.edit(t['id'], {'title': '本地'}, t['revision'])
        self.w.merge_remote([dict(remote, title='远端')], 'base/table')
        t = self.w.get(t['id'])
        result = self.w.resolve(t['id'], 'title', 'local', t['revision'])
        self.assertEqual(result['title'], '本地')
        self.assertEqual(result['pending']['title']['before'], '远端')
        self.assertFalse(result['conflicts'])

    def test_conflict_comparison_tracks_new_local_edits_and_clears_when_values_converge(self):
        remote = dict(record_id='rec1', title='原始', state='todo', owners=[])
        self.w.merge_remote([remote], 'base/table')
        t = self.w.snapshot()['tasks'][0]
        t = self.w.edit(t['id'], {'title': '本地'}, t['revision'])
        self.w.merge_remote([dict(remote, title='远端')], 'base/table')
        t = self.w.get(t['id'])
        t = self.w.edit(t['id'], {'title': '本地再次修改'}, t['revision'])
        self.assertEqual(t['conflicts']['title']['local'], '本地再次修改')
        self.w.merge_remote([dict(remote, title='本地再次修改')], 'base/table')
        self.assertFalse(self.w.get(t['id'])['conflicts'])
        self.assertFalse(self.w.get(t['id'])['pending'])

    def test_linkin_save_is_atomic_when_private_note_has_changed(self):
        t = self.task()
        t = self.w.link(t['id'], t['revision'])
        self.w.note(t['id'], '另一端笔记', 0)
        with self.assertRaises(Conflict):
            self.w.linkin_save(t['id'], {'title': '不应提交'}, t['revision'], '旧版笔记输入', 0)
        self.assertEqual(self.w.get(t['id'])['title'], '任务')
        result = self.w.linkin_save(t['id'], {'title': '选择后保存'}, t['revision'], '已比较的笔记', 1)
        self.assertEqual(result['note'], '已比较的笔记')
        self.assertNotIn('已比较的笔记', str(self.w.snapshot()))

    def test_remote_reverting_to_baseline_removes_stale_conflict(self):
        remote = dict(record_id='rec1', title='A', state='todo', owners=[])
        self.w.merge_remote([remote], 'base/table')
        t = self.w.snapshot()['tasks'][0]
        self.w.edit(t['id'], {'title': 'B'}, t['revision'])
        self.w.merge_remote([dict(remote, title='C')], 'base/table')
        self.w.merge_remote([remote], 'base/table')
        t = self.w.get(t['id'])
        self.assertFalse(t['conflicts'])
        self.assertEqual(t['pending']['title'], {'before': 'A', 'after': 'B'})

    def test_missing_remote_marker_cannot_overwrite_competing_edit(self):
        import sqlite3
        self.w.merge_remote([dict(record_id='rec1', title='A', state='todo', owners=[])], 'base/table')
        t = self.w.snapshot()['tasks'][0]
        other = Workspace(pathlib.Path(self.temp.name) / 'workspace.db')
        other.db.execute('PRAGMA busy_timeout=1')
        original = self.w._raw
        competed = []
        def interleaved(task_id):
            current = original(task_id)
            if not competed:
                competed.append(True)
                try:
                    other.edit(task_id, {'title': 'concurrent edit'}, current['revision'])
                except sqlite3.OperationalError:
                    competed[0] = False
            return current
        self.w._raw = interleaved
        try:
            self.w.merge_remote([], 'base/table')
            current = original(t['id'])
            if not competed[0]:
                other.edit(t['id'], {'title': 'concurrent edit'}, current['revision'])
            self.assertEqual(original(t['id'])['title'], 'concurrent edit')
        finally:
            self.w._raw = original
            other.close()


if __name__ == '__main__':
    unittest.main()
