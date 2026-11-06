import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'backend'))
from workspace import Conflict, Workspace


class BatchLinkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.w = Workspace(pathlib.Path(self.temp.name) / 'db')
        self.a, self.b = [self.w.create(dict(project='p', title=title)) for title in ('A', 'B')]

    def tearDown(self):
        self.w.close()
        self.temp.cleanup()

    def selections(self):
        return [dict(id=t['id'], revision=t['revision']) for t in self.w.snapshot('p')['tasks']]

    def test_batch_links_share_original_tasks_and_are_idempotent(self):
        self.w.dependencies(self.b['id'], [self.a['id']], self.b['revision'])
        self.assertEqual(self.w.link_many('p', self.selections()), dict(linked=2, already_linked=0))
        linked = self.w.linkin_snapshot()['tasks']
        self.assertEqual({t['id'] for t in linked}, {self.a['id'], self.b['id']})
        self.assertEqual(self.w.get(self.b['id'])['upstream'], [self.a['id']])
        before = self.w.snapshot('p')
        self.assertEqual(self.w.link_many('p', self.selections()), dict(linked=0, already_linked=2))
        self.assertEqual(before, self.w.snapshot('p'))

    def test_invalid_cross_project_and_stale_batches_change_nothing(self):
        other = self.w.create(dict(project='q', title='Other'))
        selected = self.selections()
        before = self.w.snapshot()
        for batch in ([], [selected[0], selected[0]], [selected[0], dict(id=other['id'], revision=other['revision'])]):
            with self.assertRaises(ValueError): self.w.link_many('p', batch)
            self.assertEqual(before, self.w.snapshot())
        self.w.edit(self.b['id'], dict(title='Updated'), self.b['revision'])
        before = self.w.snapshot()
        with self.assertRaises(Conflict): self.w.link_many('p', selected)
        self.assertEqual(before, self.w.snapshot())
