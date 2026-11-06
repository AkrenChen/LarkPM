import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'backend'))
from remote import Remote
from service import Service


class DepartmentTests(unittest.TestCase):
    def test_failed_refresh_keeps_cache_and_changed_field_invalidates_it(self):
        class Table:
            def status(self): return {}
            def departments(self, p):
                if getattr(self, 'fail', False): raise ValueError('offline')
                return {'field': '部门', 'options': [{'id': 'x', 'name': 'UI', 'color': 13}], 'error': ''}
        with tempfile.TemporaryDirectory() as folder:
            remote = Table()
            s = Service(pathlib.Path(folder) / 'workspace.db', remote)
            try:
                p = s.save_project({'name': 'A', 'base_token': 'base', 'table_id': 'one'})
                cached = s.sync_departments(p['id'])
                remote.fail = True
                with self.assertRaisesRegex(ValueError, 'offline'):
                    s.sync_departments(p['id'])
                self.assertEqual(s.project(p['id'])['department_catalog'], cached)
                changed = s.save_project(dict(s.project(p['id']), fields={'department': 'Other'}))
                self.assertNotIn('department_catalog', changed)
                s.w.save_project(dict(p, department_catalog=cached))
                changed = s.save_project(dict(s.project(p['id']), table_id='two'))
                self.assertNotIn('department_catalog', changed)
            finally:
                s.w.close()

    def test_schema_options_preserve_order_ids_and_color_and_support_field_id(self):
        class Client:
            def schema(self):
                return {'fields': [{'field_id': 'fldD', 'field_name': '部门', 'type': 3,
                                    'property': {'options': [{'id': 'b', 'name': '开发', 'color': 17},
                                                             {'id': 'a', 'name': 'UI', 'color': 13}]}}]}
        remote = Remote.__new__(Remote)
        remote.client = Client()
        remote.select = lambda p: None
        expected = [{'id': 'b', 'name': '开发', 'color': 17}, {'id': 'a', 'name': 'UI', 'color': 13}]
        for field in ('部门', 'fldD'):
            self.assertEqual(remote.departments({'fields': {'department': field}})['options'], expected)
        self.assertIn('不存在', remote.departments({'fields': {'department': 'wrong'}})['error'])

    def test_project_cache_survives_reopen_and_is_not_overwritten_by_old_project_form(self):
        class Table:
            options = [{'id': 'a', 'name': 'UI', 'color': 13}]
            def status(self): return {}
            def departments(self, p): return {'field': '部门', 'options': self.options, 'error': ''}
        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder) / 'workspace.db'
            remote = Table()
            s = Service(path, remote)
            p = s.save_project({'name': 'A', 'base_token': 'base', 'table_id': 'one'})
            other = s.save_project({'name': 'B', 'base_token': 'base', 'table_id': 'two'})
            result = s.call('departments_sync', {'project': p['id']})
            self.assertEqual(result['options'], remote.options)
            s.save_project(dict(p, name='Renamed'))
            cached = s.project(p['id'])['department_catalog']
            self.assertEqual(cached['options'], remote.options)
            self.assertNotIn('department_catalog', s.project(other['id']))
            remote.options = []
            s.call('departments_sync', {'project': p['id']})
            self.assertEqual(s.project(p['id'])['department_catalog']['options'], [])
            s.w.close()
            s = Service(path, remote)
            self.assertEqual(s.project(p['id'])['department_catalog']['options'], [])
            s.w.close()

    def test_non_select_field_is_reported_without_guessing_options(self):
        class Client:
            def schema(self):
                return {'fields': [{'field_name': '部门', 'type': 1, 'property': {}}]}
        remote = Remote.__new__(Remote)
        remote.client = Client()
        remote.select = lambda p: None
        result = remote.departments({'fields': {}})
        self.assertEqual(result['options'], [])
        self.assertIn('单选或多选', result['error'])
