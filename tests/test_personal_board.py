import copy
import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from service import Service
from workspace import Conflict
from personal_board import move, quadrant, settings


class Native:
    def __init__(self):
        self.calls = []
        self.account = 'account-a'
        self.rows = [dict(id='private', text='私人待办', priority='nuni', revision='v1', update_at=1, editable=True, recurring=False)]

    def call(self, method, params=None):
        self.calls.append((method, copy.deepcopy(params)))
        if method == 'tasks':
            return copy.deepcopy(dict(account=self.account, tasks=self.rows, pending=0, failed=0))
        if params['account'] != self.account:
            raise ValueError('账号变化')
        if method == 'save' and not params.get('id'):
            self.rows.append(dict(id='new-private', text=params['text'], priority=params['priority'], revision='v1', update_at=1, editable=True, recurring=False))
            return dict(id='new-private')
        row = next(row for row in self.rows if row['id'] == params['id'])
        if params['revision'] != row['revision']:
            raise ValueError('冲突')
        if method == 'complete':
            self.rows.remove(row)
        else:
            row.update(text=params['text'], priority=params['priority'], revision='v2', update_at=2)
        return dict(id=params['id'])


class PersonalBoardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.native = Native()
        self.s = Service(pathlib.Path(self.temp.name) / 'db', object(), self.native)
        self.s.w.save_project(dict(id='p', name='项目'))

    def tearDown(self):
        self.s.w.close()
        self.temp.cleanup()

    def test_private_read_edit_move_complete_never_enters_project_or_pending(self):
        self.s.call('personal_sync', {'enabled': True})
        before = self.s.w.snapshot()
        data = self.s.call('personal_native', {})
        note = data['tasks'][0]
        note = self.s.call('personal_native', dict(note, action='save', text='changed'))
        self.s.call('personal_native', {})
        note = self.s.call('personal_native', {})['tasks'][0]
        note = self.s.call('personal_native', dict(note, action='move', priority='ui'))
        self.s.call('personal_native', {})
        note = self.s.call('personal_native', {})['tasks'][0]
        self.s.call('personal_native', dict(note, action='complete'))
        self.s.call('personal_native', {})
        self.assertEqual(self.s.w.snapshot(), before)
        self.assertEqual(self.native.rows, [])
        with self.assertRaises(ValueError):
            self.s.call('personal_native', {'action': 'delete'})

    def test_sync_off_preserves_local_content_without_remote_calls(self):
        self.s.call('personal_sync', {'enabled': True})
        note = self.s.call('personal_native', {})['tasks'][0]
        self.s.call('personal_sync', {'enabled': False})
        calls = len(self.native.calls)
        note = self.s.call('personal_native', dict(note, action='move', priority='ui'))
        self.s.call('personal_native', dict(note, action='save', text='offline title'))
        data = self.s.call('personal_native', {})
        self.assertEqual(data['tasks'][0]['priority'], 'ui')
        self.assertEqual(data['tasks'][0]['text'], 'offline title')
        self.assertEqual(len(self.native.calls), calls)
        self.assertEqual(self.native.rows[0]['priority'], 'nuni')

    def test_create_private_native_never_enters_project_with_sync_on_or_off(self):
        before = self.s.w.snapshot()
        first = self.s.call('personal_native', dict(action='save', text='private local', priority='ui'))
        self.assertEqual(self.native.calls, [])
        self.s.call('personal_sync', {'enabled': True})
        snapshot = self.s.call('personal_native', {})
        self.assertIn(first['id'], [n['id'] for n in snapshot['tasks']])
        self.assertEqual(self.native.rows[-1]['priority'], 'ui')
        self.s.call('personal_sync', {'enabled': False})
        self.s.call('personal_native', dict(action='save', text='second local', priority='nui'))
        self.assertEqual(self.s.call('personal_native', {})['tasks'][0]['priority'], 'nui')
        self.assertEqual(self.s.w.snapshot()['tasks'], before['tasks'])

    def test_native_positions_are_per_account_and_revision_conflicts_propagate(self):
        self.s.call('personal_sync', {'enabled': True})
        first = self.s.call('personal_native', {})['tasks'][0]
        self.native.account = 'account-b'
        second = next(n for n in self.s.call('personal_native', {})['tasks'] if n['source']['account'] == 'account-b')
        self.assertNotEqual(first['id'], second['id'])
        self.s.call('personal_native', dict(first, action='move', priority='ui'))
        self.s.call('personal_native', {})
        self.assertEqual(self.native.rows[0]['priority'], 'nuni')
        with self.assertRaises(ValueError):
            self.s.call('personal_native', dict(first, action='save', text='stale'))

    def test_owner_only_auto_link_and_bidirectional_quadrants(self):
        self.s.call('personal_sync', {'enabled': True})
        self.s.w.save_settings(dict(self.s.w.settings(), profile={'name': '我', 'owner_id': 'me'}))
        own = self.s.w.create(dict(project='p', title='我的任务', owners=[dict(id='me', name='我')]))
        other = self.s.w.create(dict(project='p', title='他人任务', owners=[dict(id='other', name='别人')]))
        self.s.call('personal_prepare', {'project': 'p'})
        self.assertTrue(self.s.w.get(own['id'])['linked'])
        self.assertFalse(self.s.w.get(other['id'])['linked'])
        self.assertEqual(self.s.w.snapshot('p')['tasks'][0]['personal_quadrant'], 'nuni')
        task = self.s.w.get(own['id'])
        moved = self.s.call('personal_move', dict(id=task['id'], revision=task['revision'], quadrant='ui'))
        self.assertEqual(quadrant(self.s.w._raw(task['id']), 'linkin', settings(self.s.w)), 'ui')
        moved = move(self.s.w, task['id'], 'nui', moved['revision'], 'linkin')
        self.assertEqual(self.s.w.get(task['id'])['shared_quadrant'], 'nui')
        with self.assertRaises(Conflict):
            move(self.s.w, task['id'], 'ui', task['revision'], 'linkin')
        self.s.call('personal_sync', {'enabled': False})
        moved = move(self.s.w, task['id'], 'uni', moved['revision'], 'pm')
        move(self.s.w, task['id'], 'ui', moved['revision'], 'linkin')
        self.assertEqual(quadrant(self.s.w._raw(task['id']), 'pm', settings(self.s.w)), 'uni')
        self.s.call('personal_sync', {'enabled': True})
        self.assertEqual(quadrant(self.s.w._raw(task['id']), 'linkin', settings(self.s.w)), 'uni')

    def test_custom_names_and_shared_helper_match_companion(self):
        path = pathlib.Path(self.temp.name) / 'preferences.json'
        path.write_text(json.dumps({'names': {'ui': '立即做', 'nuni': '以后做'}}), encoding='utf-8')
        with patch.dict(os.environ, LINKINNOTES_PREFERENCES=str(path)):
            self.assertEqual(settings(self.s.w)['names']['ui'], '立即做')
        self.assertEqual((ROOT / 'backend/personal_board.py').read_bytes(), (ROOT.parent / 'LinkinNotes/backend/personal_board.py').read_bytes())

    def test_new_task_upstream_is_atomic_and_blocks_start(self):
        upstream = self.s.w.create(dict(project='p', module='需求', title='开发', state='active'))
        task = self.s.call('create', dict(project='p', module='需求', title='后续任务', upstream=[upstream['id']]))
        self.assertEqual(task['upstream'], [upstream['id']])
        with self.assertRaisesRegex(ValueError, '上游'):
            self.s.w.edit(task['id'], {'state': 'active'}, task['revision'])
        before = self.s.w.snapshot('p')
        with self.assertRaises(ValueError):
            self.s.call('create', dict(project='p', title='无效', upstream=['missing']))
        self.assertEqual(self.s.w.snapshot('p'), before)


if __name__ == '__main__':
    unittest.main()
