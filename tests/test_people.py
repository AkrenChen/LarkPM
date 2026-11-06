import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'backend'))
from workspace import Workspace
from remote import Remote


class PeopleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.w = Workspace(pathlib.Path(self.temp.name) / 'workspace.db')

    def tearDown(self):
        self.w.close()
        self.temp.cleanup()

    def test_local_status_and_department_survive_table_merge_and_reopen(self):
        row = dict(record_id='r', title='History', owners=[{'id': 'ou_old', 'name': 'Old'}], state='todo')
        self.w.merge_remote([row], 'scope')
        draft = self.w.settings()
        self.w.save_settings(dict(draft, people=[dict(id='ou_old', name='Old', department='UI', employment_status='resigned')]))
        self.w.merge_remote([dict(row, owners=row['owners'] + [{'id': 'ou_new', 'name': 'New'}])], 'scope')
        self.w.close()
        self.w = Workspace(pathlib.Path(self.temp.name) / 'workspace.db')
        people = {p['id']: p for p in self.w.settings()['people']}
        self.assertEqual(people['ou_old']['employment_status'], 'resigned')
        self.assertEqual(people['ou_old']['department'], 'UI')
        self.assertEqual(people['ou_new']['employment_status'], 'unknown')
        self.assertEqual(len(self.w.snapshot()['tasks'][0]['owners']), 2)

    def test_status_updates_can_be_batched_and_bad_values_do_not_partially_save(self):
        people = [dict(id='a', name='A', department='Dev', employment_status='active'),
                  dict(id='b', name='B', department='Dev', employment_status='unused')]
        saved = self.w.save_settings(dict(self.w.settings(), people=people))
        self.assertEqual([p['employment_status'] for p in saved['people']], ['active', 'unused'])
        with self.assertRaises(ValueError):
            self.w.save_settings(dict(saved, people=[dict(people[0], employment_status='active'), dict(people[1], employment_status='invalid')]))
        self.assertEqual(self.w.settings()['revision'], saved['revision'])
        self.assertEqual(self.w.settings()['people'][1]['employment_status'], 'unused')

    def test_missing_status_on_department_only_save_keeps_previous_local_status(self):
        draft = self.w.settings()
        self.w.save_settings(dict(draft, people=[dict(id='a', name='A', department='', employment_status='resigned')]))
        self.w.save_settings(dict(self.w.settings(), people=[dict(id='a', name='A', department='New')]))
        self.assertEqual(self.w.settings()['people'][0]['employment_status'], 'resigned')

    def test_table_authorization_strips_contact_scopes_and_keeps_table_access(self):
        class Client:
            def __init__(self): self.scope = 'bitable:app offline_access contact:contact.base:readonly contact:user.employee:readonly'
            def status(self): return {'scope': self.scope}
            def configure(self, params): self.scope = params['scope']
            def begin_auth(self): return {'url': 'table-auth'}
        remote = Remote.__new__(Remote)
        remote.client = Client()
        self.assertEqual(remote.begin_auth()['url'], 'table-auth')
        self.assertEqual(remote.client.scope, 'bitable:app offline_access')
