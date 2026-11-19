import copy
import pathlib
import sys
import tempfile
import unittest
import threading
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'backend'))
from service import Service


class Bridge:
    def __init__(self):
        self.account = 'a'
        self.rows = []
        self.calls = []
        self.offline = False

    def call(self, method, params=None):
        self.calls.append((method, copy.deepcopy(params)))
        if self.offline:
            raise ValueError('LinkinNotes unavailable')
        if method == 'tasks':
            return dict(account=self.account, tasks=copy.deepcopy(self.rows), pending=0, failed=0)
        assert params['account'] == self.account
        if not params.get('id'):
            row = dict(id='remote-' + str(len(self.rows)), text=params['text'], priority=params['priority'], revision='1', update_at=1, editable=True, recurring=False)
            self.rows.append(row)
            return dict(id=row['id'])
        row = next(r for r in self.rows if r['id'] == params['id'])
        assert row['revision'] == params['revision']
        if method == 'complete':
            self.rows.remove(row)
        else:
            row.update(text=params['text'], priority=params['priority'], revision=str(int(row['revision']) + 1), update_at=row['update_at'] + 1)
        return dict(id=row['id'])


class StandaloneNotesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = pathlib.Path(self.temp.name) / 'workspace.db'
        self.bridge = Bridge()
        self.service = Service(self.path, object(), self.bridge)

    def tearDown(self):
        self.service.w.close()
        self.temp.cleanup()

    def call(self, action='snapshot', **params):
        return self.service.call('personal_native', dict(action=action, **params))

    def create(self, text='local', priority='nuni'):
        return self.call('save', text=text, priority=priority)

    def test_clean_install_create_edit_move_restart_complete_without_bridge_or_project(self):
        self.assertFalse(self.service.w.snapshot()['personal_board']['sync'])
        note = self.create()
        note = self.call('save', **dict(note, text='edited'))
        note = self.call('move', **dict(note, priority='ui'))
        self.service.w.close()
        self.service = Service(self.path, object(), self.bridge)
        self.assertEqual([(n['text'], n['priority']) for n in self.call()['tasks']], [('edited', 'ui')])
        self.call('complete', **note)
        self.assertEqual(self.call()['tasks'], [])
        self.assertEqual(self.bridge.calls, [])
        self.assertEqual(self.service.w.snapshot()['tasks'], [])
        self.assertEqual(self.service.w.projects(), [])

    def test_enabled_but_offline_saves_locally_and_reconnects_without_duplicate(self):
        self.service.call('personal_sync', {'enabled': True})
        self.bridge.offline = True
        note = self.create()
        self.assertEqual(self.call()['tasks'][0]['id'], note['id'])
        self.bridge.offline = False
        self.assertEqual(len(self.call()['tasks']), 1)
        self.assertEqual(len(self.call()['tasks']), 1)
        self.assertEqual(len(self.bridge.rows), 1)
        self.bridge.rows[0].update(text='from linkin', revision='8')
        current = self.call()['tasks'][0]
        self.assertEqual(current['text'], 'from linkin')
        self.call('complete', **current)
        self.call()
        self.assertEqual(self.bridge.rows, [])

    def test_import_stable_id_sync_off_no_calls_then_nonoverlapping_merge(self):
        self.bridge.rows = [dict(id='old', text='old', priority='nuni', revision='1', update_at=1, editable=True, recurring=False)]
        self.service.call('personal_sync', {'enabled': True})
        first = self.call()['tasks'][0]
        self.service.call('personal_sync', {'enabled': False})
        self.call('move', **dict(first, priority='ui'))
        calls = len(self.bridge.calls)
        self.assertEqual(self.call()['tasks'][0]['priority'], 'ui')
        self.assertEqual(len(self.bridge.calls), calls)
        self.bridge.rows[0].update(text='external', revision='2')
        self.service.call('personal_sync', {'enabled': True})
        merged = self.call()['tasks'][0]
        self.assertEqual((merged['id'], merged['text'], merged['priority']), (first['id'], 'external', 'ui'))
        self.assertEqual(self.bridge.rows[0]['priority'], 'ui')

    def test_conflicts_preserve_both_and_resolve_explicitly(self):
        self.service.call('personal_sync', {'enabled': True})
        self.create()
        first = self.call()['tasks'][0]
        local = self.call('save', **dict(first, text='local edit'))
        self.bridge.rows[0].update(text='remote edit', revision='2')
        conflicted = self.call()['tasks'][0]
        self.assertEqual(conflicted['text'], 'local edit')
        self.assertTrue(conflicted['conflict'])
        self.assertEqual(self.bridge.rows[0]['text'], 'remote edit')
        self.call('resolve', **dict(conflicted, choice='local'))
        self.call()
        self.assertEqual(self.bridge.rows[0]['text'], 'local edit')
        with self.assertRaises(ValueError):
            self.call('save', **dict(local, text='stale edit'))

    def test_account_change_never_exports_other_accounts_private_notes(self):
        self.service.call('personal_sync', {'enabled': True})
        self.create()
        first = self.call()['tasks'][0]
        self.call('save', **dict(first, text='private edit'))
        self.bridge.account = 'b'
        self.bridge.rows = []
        self.call()
        self.assertEqual(self.bridge.rows, [])

    def test_completion_in_linkin_reflects_locally(self):
        self.service.call('personal_sync', {'enabled': True})
        self.create()
        self.call()
        self.bridge.rows.clear()
        self.assertEqual(self.call()['tasks'], [])

    def test_invalid_inputs_and_stale_revisions_do_not_change_notes(self):
        first = self.create()
        with self.assertRaises(ValueError):
            self.call('move', **dict(first, priority='invalid'))
        self.call('save', **dict(first, text='updated'))
        with self.assertRaises(ValueError):
            self.call('complete', **first)
        self.assertEqual(self.call()['tasks'][0]['text'], 'updated')

    def test_background_bridge_does_not_block_local_crud(self):
        self.service.call('personal_sync', {'enabled': True})
        started, release = threading.Event(), threading.Event()
        original = self.bridge.call
        def delayed(method, params=None):
            started.set()
            release.wait(5)
            return original(method, params)
        self.bridge.background = True
        self.bridge.call = delayed
        began = time.monotonic()
        self.call()
        self.assertLess(time.monotonic() - began, 1)
        self.assertTrue(started.wait(1))
        try:
            note = self.create('while synchronizing')
            note = self.call('save', **dict(note, text='local remains usable'))
            self.assertEqual(note['text'], 'local remains usable')
            self.assertLess(time.monotonic() - began, 2)
        finally:
            release.set()
            self.service._notes_worker.join(3)

    def test_sync_cannot_overwrite_edit_made_during_remote_request(self):
        from standalone_notes import PersonalNotes
        note = self.create()
        stale = copy.deepcopy(note)
        self.call('save', **dict(note, text='newer edit'))
        stale['text'] = 'stale background result'
        with self.assertRaises(ValueError):
            PersonalNotes(self.service.w).put(stale)
        self.assertEqual(self.call()['tasks'][0]['text'], 'newer edit')

    def test_existing_implicit_sync_is_migrated_once(self):
        from personal_board import settings
        task = self.service.w.create(dict(title='existing linked task', linked=True))
        self.assertTrue(settings(self.service.w)['sync'])
        with self.service.w.db:
            raw = self.service.w._raw(task['id'])
            raw['linked'] = False
            self.service.w._put(raw)
        self.assertTrue(settings(self.service.w)['sync'])

    def test_create_response_loss_never_blindly_creates_again(self):
        self.service.call('personal_sync', {'enabled': True})
        self.create()
        original = self.bridge.call
        def lose_response(method, params=None):
            result = original(method, params)
            if method == 'save' and not params.get('id'):
                raise TimeoutError('Lost acknowledgement')
            return result
        self.bridge.call = lose_response
        first = self.call()
        self.assertTrue(first['sync_error'])
        self.bridge.call = original
        self.call()
        self.call()
        self.assertEqual(len(self.bridge.rows), 1)
        self.assertEqual(len([1 for method, params in self.bridge.calls if method == 'save' and not params.get('id')]), 1)


if __name__ == '__main__':
    unittest.main()
