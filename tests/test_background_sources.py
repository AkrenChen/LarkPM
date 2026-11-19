import pathlib
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'backend'))
from service import Service


class Remote:
    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()
        self.calls = []
        self.fail = False

    def status(self): return {}
    def records(self, project): return [dict(record_id='r', title='New requirement', state='todo')]
    def update(self, project, record_id, patch): pass
    def source_rows(self, source, kind):
        self.calls.append((source['table_id'], kind))
        self.started.set()
        if not self.release.wait(4): raise ValueError('test timeout')
        if self.fail: raise ValueError('source denied')
        if kind == 'tests': return [dict(id='t', project='P', title='Test', start='2026-11-19', end='2026-11-20')]
        return [dict(id=source['table_id'], platform='安卓', version='v2', status='已过审')]


class BackgroundSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.remote = Remote()
        self.s = Service(pathlib.Path(self.temp.name) / 'db', self.remote)
        self.source = dict(url='https://x.feishu.cn/base/b?table=v1')
        self.p = self.s.save_project(dict(name='P', base_token='b', table_id='r', sources={'versions': self.source}))

    def tearDown(self):
        self.remote.release.set()
        if hasattr(self.s, 'sources'): self.s.sources.wait(5)
        self.s.w.close()
        self.temp.cleanup()

    def snapshot_project(self):
        return next(p for p in self.s.call('snapshot', {})['projects'] if p['id'] == self.p['id'])

    def test_requirements_finish_without_waiting_for_sources_and_snapshot_stays_usable(self):
        with patch.object(self.s, 'sync_sources', side_effect=AssertionError('foreground source read')):
            result = self.s.call('sync', dict(project=self.p['id']))
        self.assertEqual(result['count'], 1)
        self.assertTrue(self.remote.started.wait(1))
        self.assertEqual(self.snapshot_project()['source_refresh'], ['versions'])
        self.assertEqual(self.s.w.snapshot()['tasks'][0]['title'], 'New requirement')
        self.s.w.create(dict(project=self.p['id'], title='Local during network wait'))
        self.remote.release.set()
        self.assertTrue(self.s.sources.wait(2))
        self.assertFalse(self.snapshot_project()['source_refresh'])
        self.assertEqual(self.s.project(self.p['id'])['source_cache']['versions']['online']['android']['version'], 'v2')

    def test_write_checks_requirements_but_never_reads_sources(self):
        self.s.w.merge_remote(self.remote.records(self.p), 'b/r', self.p['id'])
        task = self.s.w.snapshot()['tasks'][0]
        task = self.s.w.edit(task['id'], dict(title='Changed'), task['revision'])
        with patch.object(self.s, 'sync_sources', side_effect=AssertionError('unrelated source read')):
            self.s.write(self.p['id'], [dict(id=task['id'], revision=task['revision'], fields=['title'])])
        self.assertFalse(self.remote.calls)

    def test_save_refreshes_only_changed_source_and_old_result_cannot_replace_rebind(self):
        self.s.call('project_sources_refresh', dict(project=self.p['id']))
        self.assertTrue(self.remote.started.wait(1))
        changed = dict(self.s.project(self.p['id']))
        changed['sources'] = dict(versions=dict(url='https://x.feishu.cn/base/b?table=v2'))
        saved = self.s.call('project_save', changed)
        self.assertEqual(saved['sources']['versions']['table_id'], 'v2')
        self.remote.release.set()
        self.assertTrue(self.s.sources.wait(2))
        self.assertEqual(self.s.project(self.p['id'])['source_cache']['versions']['rows'][0]['id'], 'v2')
        count = len(self.remote.calls)
        self.s.call('project_save', dict(self.s.project(self.p['id']), name='Renamed'))
        self.s.sources.wait(2)
        self.assertEqual(len(self.remote.calls), count)

    def test_failure_preserves_cache_and_duplicate_refresh_is_coalesced(self):
        self.remote.release.set()
        self.s.sync_sources(self.p['id'])
        self.remote.release.clear()
        self.remote.fail = True
        self.s.call('project_sources_refresh', dict(project=self.p['id']))
        self.assertTrue(self.remote.started.wait(1))
        self.s.call('project_sources_refresh', dict(project=self.p['id']))
        self.remote.release.set()
        self.assertTrue(self.s.sources.wait(2))
        cache = self.s.project(self.p['id'])['source_cache']['versions']
        self.assertEqual(cache['online']['android']['version'], 'v2')
        self.assertIn('source denied', cache['error'])
        self.assertEqual(len(self.remote.calls), 2)

    def test_deleting_project_during_source_read_does_not_recreate_it(self):
        self.s.call('project_sources_refresh', dict(project=self.p['id']))
        self.assertTrue(self.remote.started.wait(1))
        self.s.w.delete_project(self.p['id'], True)
        self.remote.release.set()
        self.assertTrue(self.s.sources.wait(2))
        self.assertFalse(self.s.w.projects())
