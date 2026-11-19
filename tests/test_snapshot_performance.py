import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'backend'))
from workspace import Workspace
from service import Service
from personal_board import settings, quadrant
from publishing import candidates


class SnapshotPerformanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.w = Workspace(pathlib.Path(self.temp.name) / 'db')

    def tearDown(self):
        self.w.close()
        self.temp.cleanup()

    def test_snapshot_matches_individual_reads_with_linear_query_count(self):
        parent = self.w.create(dict(project='p', title='parent', is_requirement=True))
        upstream = self.w.create(dict(project='p', title='upstream', state='done'))
        removed = self.w.create(dict(project='p', title='removed'))
        for index in range(80):
            task = self.w.create(dict(project='p' if index % 2 else 'q', title=str(index),
                                      owners=[dict(id='person')], department_override=['Override'] if index % 3 else None,
                                      acceptance='验收通过' if index % 4 else '', linked=True))
            raw = self.w._raw(task['id'])
            raw['upstream'] = [upstream['id'], removed['id'], parent['id'], 'missing']
            with self.w.db:
                self.w._put(raw)
        with self.w.db:
            raw = self.w._raw(removed['id'])
            raw['locally_removed'] = True
            self.w._put(raw)
        self.w.save_settings(dict(revision=0, profile=dict(name='', owner_id=''), people=[dict(id='person', name='User', department='Design')]))
        config = settings(self.w)
        for project in (None, 'p', 'q'):
            expected = [dict(self.w.get(t['id']), personal_quadrant=quadrant(t, 'pm', config))
                        for t in self.w._all(project) if not t.get('is_requirement')]
            queries = []
            self.w.db.set_trace_callback(queries.append)
            actual = self.w.snapshot(project)
            self.w.db.set_trace_callback(None)
            self.assertEqual(actual['tasks'], expected)
            self.assertLess(len(queries), 15, 'snapshot should read task/settings data in batches')

    def test_local_publication_candidates_do_not_scan_project_per_task(self):
        project = self.w.save_project(dict(id='p', name='p', base_token='offline', table_id='offline'))
        for index in range(40):
            self.w.create(dict(project='p', title=str(index)))
        with patch.object(self.w, '_all', wraps=self.w._all) as reads:
            result = candidates(self.w, project)
        self.assertEqual(len(result), 40)
        self.assertLess(reads.call_count, 5)

    def test_service_arrange_does_not_build_unused_snapshot(self):
        self.w.save_project(dict(id='p', name='p'))
        first = self.w.create(dict(project='p', module='S', title='a'))
        second = self.w.create(dict(project='p', module='S', title='b'))
        service = object.__new__(Service)
        service.w = self.w
        with patch.object(self.w, 'snapshot', side_effect=AssertionError('duplicate snapshot')):
            service.call('workflow_arrange', dict(project='p', systems=[dict(module='S', stages=[[first['id']], [second['id']]])],
                                                  revisions={t['id']: t['revision'] for t in (first, second)}))
        self.assertEqual(self.w.get(second['id'])['upstream'], [first['id']])
