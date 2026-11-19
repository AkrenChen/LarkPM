import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'backend'))
from service import Service
from test_service import Remote


class PriorityTests(unittest.TestCase):
    def test_priority_encoder_uses_exact_option_and_null_to_clear(self):
        from test_feishu import FakeTransport
        from feishu import Feishu
        with tempfile.TemporaryDirectory() as folder:
            transport = FakeTransport([dict(data=dict(record=dict(record_id='r', fields={'优先级': '高'}))), dict(data=dict(record=dict(record_id='r', fields={})) )])
            client = Feishu(folder, transport=transport, protect=lambda value:value, unprotect=lambda value:value)
            client._config.update(base_token='b', table_id='t')
            client._tokens = dict(access_token='fake', expires_at=9999999999)
            self.assertEqual(client.update('r', dict(priority='高'))['priority'], '高')
            client.update('r', dict(priority=''))
            self.assertEqual(transport.calls[0][3], {'fields': {'优先级': '高'}})
            self.assertEqual(transport.calls[1][3], {'fields': {'优先级': None}})

    def test_priority_read_edit_conflict_and_explicit_write(self):
        with tempfile.TemporaryDirectory() as folder:
            remote = Remote()
            remote.rows[0]['priority'] = '高'
            s = Service(pathlib.Path(folder) / 'db', remote)
            try:
                p = s.save_project(dict(name='P', base_token='b', table_id='t'))
                s.sync(p['id'])
                task = s.w.snapshot()['tasks'][0]
                self.assertEqual(task['priority'], '高')
                task = s.w.edit(task['id'], dict(priority='中'), task['revision'])
                self.assertEqual(set(task['pending']), {'priority'})
                s.sync(p['id'])
                task = s.w.get(task['id'])
                self.assertEqual(task['priority'], '中')
                self.assertFalse(task['conflicts'])
                s.write(p['id'], [dict(id=task['id'], revision=task['revision'], fields=['priority'])])
                self.assertEqual(remote.writes[-1][2], dict(priority='中'))
                self.assertFalse(s.w.get(task['id'])['pending'])
                task = s.w.edit(task['id'], dict(priority='低'), s.w.get(task['id'])['revision'])
                remote.rows[0]['priority'] = '高'
                s.sync(p['id'])
                self.assertIn('priority', s.w.get(task['id'])['conflicts'])
            finally: s.w.close()

    def test_legacy_remote_baseline_does_not_make_empty_priority_pending(self):
        from workspace import Workspace
        with tempfile.TemporaryDirectory() as folder:
            w = Workspace(pathlib.Path(folder) / 'db')
            try:
                task = w.create(dict(title='old', source=dict(record_id='r', scope='s', base=dict(title='old', start='', end='', owners=[], state='todo'))))
                self.assertFalse(w.get(task['id'])['pending'])
            finally: w.close()
