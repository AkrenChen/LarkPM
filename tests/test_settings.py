import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'backend'))
from workspace import Workspace


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = pathlib.Path(self.temp.name) / 'workspace.db'
        self.w = Workspace(self.path)

    def tearDown(self):
        self.w.close()
        self.temp.cleanup()

    def test_settings_persist_and_collect_people_across_projects_by_id(self):
        self.w.create(dict(title='One', project='one', owners=[{'id': 'a', 'name': 'Same'}]))
        self.w.create(dict(title='Two', project='two', owners=[{'id': 'b', 'name': 'Same'}]))
        saved = self.w.save_settings(dict(revision=0, profile={'name': 'Me', 'owner_id': 'a'},
                                         people=[{'id': 'a', 'name': 'Same', 'department': 'UI'}]))
        self.assertEqual({p['id'] for p in saved['people']}, {'a', 'b'})
        self.w.close()
        self.w = Workspace(self.path)
        self.assertEqual(self.w.settings()['profile'], {'name': 'Me', 'owner_id': 'a'})
        self.assertEqual(next(p for p in self.w.settings()['people'] if p['id'] == 'a')['department'], 'UI')

    def test_departments_follow_people_with_explicit_override_and_no_remote_pending(self):
        self.w.save_settings(dict(revision=0, profile={'name': '', 'owner_id': ''}, people=[
            {'id': 'a', 'name': 'A', 'department': 'UI'}, {'id': 'b', 'name': 'B', 'department': 'UI'},
            {'id': 'c', 'name': 'C', 'department': 'Dev'}]))
        task = self.w.create(dict(title='One', owners=[{'id': 'a'}, {'id': 'b'}]))
        self.assertEqual(task['departments'], ['UI'])
        task = self.w.edit(task['id'], {'owners': [{'id': 'c'}]}, task['revision'])
        self.assertEqual(task['departments'], ['Dev'])
        task = self.w.edit(task['id'], {'department_override': ['Special']}, task['revision'])
        self.assertEqual(task['departments'], ['Special'])
        self.assertEqual(task['pending'], {})
        settings = self.w.settings()
        self.w.save_settings(dict(revision=settings['revision'], profile=settings['profile'], people=[
            {'id': 'c', 'name': 'C', 'department': 'New'}]))
        self.assertEqual(self.w.get(task['id'])['departments'], ['Special'])
        task = self.w.edit(task['id'], {'department_override': None}, task['revision'])
        self.assertEqual(task['departments'], ['New'])

    def test_settings_reject_stale_save_duplicate_ids_and_invalid_values(self):
        valid = dict(revision=0, profile={'name': 'Me', 'owner_id': ''}, people=[])
        self.w.save_settings(valid)
        with self.assertRaisesRegex(ValueError, '设置已'):
            self.w.save_settings(valid)
        for people in ([{'id': '', 'name': 'X', 'department': 'UI'}],
                       [{'id': 'a'}, {'id': 'a'}], [{'id': 'a', 'department': ['UI']}]):
            with self.subTest(people=people), self.assertRaises(ValueError):
                self.w.save_settings(dict(valid, revision=1, people=people))
        self.assertEqual(self.w.settings()['revision'], 1)

    def test_department_override_validates_and_old_tasks_without_field_still_load(self):
        task = self.w.create(dict(title='Legacy'))
        with self.assertRaises(ValueError):
            self.w.edit(task['id'], {'department_override': 'UI'}, task['revision'])
        raw = self.w._raw(task['id'])
        raw.pop('department_override', None)
        with self.w.db:
            self.w._put(raw)
        self.assertIsNone(self.w.get(task['id'])['department_override'])
        self.assertEqual(self.w.get(task['id'])['departments'], [])
