import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'backend'))
from service import Service
from project_sources import summarize_versions, test_windows
from remote import Remote


class ProjectSourceTests(unittest.TestCase):
    def test_submission_date_is_separate_and_optional(self):
        class Client:
            def __init__(self, include_submission=True): self.include_submission = include_submission
            def _pages(self, resource, size, url):
                if resource == 'fields':
                    return [dict(field_id='f1', field_name='过审时间')] + ([dict(field_id='f2', field_name='提审时间')] if self.include_submission else [])
                return [dict(record_id='a', fields={'过审时间': 1793750400000, '提审时间': 1793577600000})]
        remote = Remote.__new__(Remote)
        source = dict(base_token='b', table_id='t', fields={'released': '过审时间'})
        remote.client = Client()
        row = remote.source_rows(source, 'versions')[0]
        self.assertEqual(row['submitted'], '2026-11-02')
        self.assertTrue(row['released'].startswith('2026-11-04'))
        remote.client = Client(False)
        self.assertNotIn('submitted', remote.source_rows(source, 'versions')[0])

    def test_source_read_does_not_switch_requirement_connection(self):
        class Client:
            def __init__(self): self.calls = []
            def _pages(self, resource, size, url):
                self.calls.append((resource, url))
                if resource == 'fields':
                    return [dict(field_id='f1', field_name='平台'), dict(field_id='f2', field_name='版本')]
                return [dict(record_id='a', fields={'平台': '安卓', '版本': [{'text': 'v1.2'}]})]
        remote = Remote.__new__(Remote)
        remote.client = Client()
        rows = remote.source_rows(dict(base_token='baseV', table_id='tblV', fields={'platform': 'f1', 'version': '版本'}), 'versions')
        self.assertEqual(rows[0]['version'], 'v1.2')
        self.assertTrue(all('/baseV/tables/tblV' in url for _, url in remote.client.calls))
        with self.assertRaisesRegex(ValueError, '字段不存在'):
            remote.source_rows(dict(base_token='baseV', table_id='tblV', fields={'version': 'missing'}), 'versions')

    def test_online_is_per_platform_and_excludes_unapproved(self):
        rows = [dict(id='a', platform='安卓', version='v1.9', status='已过审', released='2026-10-01'),
                dict(id='b', platform='Android', version='v1.10', status='已过审', released='2026-10-02'),
                dict(id='c', platform='iOS', version='v9.0', status='已提审', released=''),
                dict(id='d', platform='安卓', version='v2.0', status='拒审', released='2026-11-01')]
        result = summarize_versions(rows, '已过审')
        self.assertEqual(result['android']['version'], 'v1.10')
        self.assertIsNone(result['ios'])

    def test_testing_uses_exact_project_and_preserves_missing_dates(self):
        rows = [dict(id='a', project='SolitairePuzzle', title='A', start='2026-10-23', end='2026-10-26'),
                dict(id='b', project='Solitaire', title='B', start='2026-10-23', end='2026-10-26'),
                dict(id='c', project='SolitairePuzzle', title='C', start='2026-11-01', end='')]
        self.assertEqual([r['id'] for r in test_windows(rows, 'SolitairePuzzle')], ['a', 'c'])
        self.assertEqual(test_windows(rows, ''), [])

    def test_cache_is_read_only_preserved_on_failure_and_invalidated_on_rebind(self):
        class Remote:
            fail = False
            def status(self): return {}
            def source_rows(self, source, kind):
                if self.fail: raise ValueError('无读取权限')
                return [dict(id='a', platform='安卓', version='v1.0', status='已过审', released='2026-10-27')]
        with tempfile.TemporaryDirectory() as directory:
            remote = Remote()
            s = Service(pathlib.Path(directory) / 'db', remote)
            try:
                source = dict(url='https://x.feishu.cn/base/base1?table=tbl1')
                p = s.save_project(dict(name='P', base_token='baseP', table_id='tblP', sources={'versions': source}))
                s.call('project_sources_sync', {'project': p['id']})
                remote.fail = True
                s.call('project_sources_sync', {'project': p['id']})
                p = s.project(p['id'])
                self.assertEqual(p['source_cache']['versions']['online']['android']['version'], 'v1.0')
                self.assertEqual(p['source_cache']['versions']['rows'], [dict(id='a', platform='安卓', version='v1.0', status='已过审', released='2026-10-27')])
                self.assertIn('无读取权限', p['source_cache']['versions']['error'])
                stale = dict(p)
                stale['source_cache'] = {}
                self.assertIn('versions', s.save_project(stale)['source_cache'])
                p['sources']['versions']['url'] = 'https://x.feishu.cn/base/base2?table=tbl2'
                self.assertNotIn('versions', s.save_project(p)['source_cache'])
                p['url'] = 'https://new.feishu.cn/base/newBase?table=newTable&view=newView'
                rebound = s.save_project(p)
                self.assertEqual(rebound['url'], p['url'])
                self.assertEqual(rebound['table_id'], 'newTable')
                self.assertEqual(s.w.snapshot()['tasks'], [])
            finally:
                s.w.close()


if __name__ == '__main__':
    unittest.main()
