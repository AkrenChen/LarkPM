import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'backend'))
from remote import Remote
from service import Service


class VersionCatalogTests(unittest.TestCase):
    def test_reads_unused_options_with_exact_source_names_and_order(self):
        class Client:
            def schema(self):
                return {'fields': [{'field_id': 'fldV', 'field_name': '版本', 'type': 3, 'property': {'options': [
                    {'name': 'v1.0.2（安卓）'}, {'name': 'v1.0.2 (iOS)'}, {'name': '研发/初审版本'}]}}]}
        remote = Remote.__new__(Remote)
        remote.client = Client()
        remote.select = lambda p: None
        for mapping in ('版本', 'fldV'):
            result = remote.versions({'fields': {'version': mapping}})
            self.assertTrue(result['selectable'])
            self.assertEqual(result['options'], ['v1.0.2（安卓）', 'v1.0.2 (iOS)', '研发/初审版本'])
        with self.assertRaises(ValueError):
            remote.versions({'fields': {'version': 'wrong'}})

    def test_cache_preserved_on_form_save_and_invalidated_on_mapping_change(self):
        class Table:
            def status(self): return {}
            def versions(self, p): return dict(field='版本', selectable=True, options=['v1.0.2（安卓）'])
        with tempfile.TemporaryDirectory() as folder:
            s = Service(pathlib.Path(folder) / 'workspace.db', Table())
            try:
                project = s.save_project(dict(name='test', base_token='base', table_id='table'))
                s.call('versions_sync', {'project': project['id']})
                saved = s.save_project(dict(project, name='renamed'))
                self.assertEqual(saved['version_catalog']['options'], ['v1.0.2（安卓）'])
                saved = s.save_project(dict(saved, fields=dict(saved['fields'], version='other')))
                self.assertNotIn('version_catalog', saved)
            finally:
                s.w.close()
