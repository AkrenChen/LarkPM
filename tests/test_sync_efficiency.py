import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'backend'))
from workspace import Workspace
from remote import Remote


class SyncEfficiencyTests(unittest.TestCase):
    def test_one_schema_for_requirement_records_versions_and_departments(self):
        class Client:
            def __init__(self): self.reads = 0; self.mapping = dict(title='Title', version='Version')
            def schema(self):
                self.reads += 1
                return dict(fields=[dict(field_name='Title', type=1), dict(field_name='Version', type=3, property=dict(options=[dict(name='exact version')])),
                                    dict(field_name='Department', type=3, property=dict(options=[dict(id='d', name='UI', color=3)]))])
            def status(self): return dict(field_map=self.mapping)
            def configure(self, values): self.mapping = values.get('field_map', self.mapping)
            def records(self): return [dict(record_id='r', title='Requirement')]
        remote = Remote.__new__(Remote)
        remote.client = Client()
        remote.select = lambda project: None
        project = dict(fields=dict(version='Version', department='Department'))
        result = remote.read_requirements(project)
        self.assertEqual(remote.client.reads, 1)
        self.assertEqual(result['catalogs']['version_catalog']['options'], ['exact version'])
        self.assertEqual(result['catalogs']['department_catalog']['options'][0]['name'], 'UI')
        remote.versions(project)
        self.assertEqual(remote.client.reads, 2, 'Explicit refresh must still read a fresh schema')

    def test_merge_batches_transactions_and_skips_unchanged_revisions(self):
        with tempfile.TemporaryDirectory() as folder:
            w = Workspace(pathlib.Path(folder) / 'db')
            try:
                rows = [dict(record_id=str(i), title=str(i), state='todo') for i in range(60)]
                statements = []
                w.db.set_trace_callback(statements.append)
                w.merge_remote(rows, 'scope', 'p')
                w.db.set_trace_callback(None)
                self.assertEqual(sum(sql.startswith('BEGIN') for sql in statements), 1)
                before = w.snapshot('p')
                statements.clear()
                w.db.set_trace_callback(statements.append)
                w.merge_remote(rows, 'scope', 'p')
                w.db.set_trace_callback(None)
                self.assertEqual(w.snapshot('p'), before)
                self.assertFalse(any(sql.startswith(('INSERT', 'UPDATE')) for sql in statements))
                rows[0]['title'] = 'changed'
                w.merge_remote(rows, 'scope', 'p')
                after = {t['source']['record_id']: t for t in w.snapshot('p')['tasks']}
                self.assertEqual(after['0']['revision'], before['tasks'][0]['revision'] + 1)
                self.assertEqual(after['1']['revision'], before['tasks'][1]['revision'])
            finally: w.close()
