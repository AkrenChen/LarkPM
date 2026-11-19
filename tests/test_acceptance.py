import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'backend'))
from remote import Remote


class Client:
    def __init__(self):
        self.config = {'field_map': {}}
        self.fields = [{'field_id': 'fldReview', 'field_name': 'Review', 'type': 3,
                        'property': {'options': [{'name': '验收通过'}]}}]
        self.writes = []

    def configure(self, patch):
        for key, value in patch.items():
            if key == 'field_map':
                self.config[key].update(value)
            else:
                self.config[key] = value

    def status(self):
        return self.config

    def schema(self):
        return {'fields': self.fields}

    def update(self, record_id, patch):
        self.writes.append((self.config['table_id'], self.config['field_map']['acceptance'], record_id, patch))
        return {'acceptance': '验收通过'}


class AcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.remote = Remote.__new__(Remote)
        self.remote.client = Client()
        self.project = {'base_token': 'base1', 'table_id': 'table1', 'fields': {'acceptance': 'fldReview'}}

    def test_switches_to_requested_project_and_resolves_field_id_before_write(self):
        self.remote.client.config.update(base_token='other', table_id='other')
        self.remote.accept(self.project, 'rec1')
        self.assertEqual(self.remote.client.writes, [('table1', 'Review', 'rec1', {'acceptance': '验收通过'})])

    def test_missing_field_wrong_type_and_absent_option_never_write(self):
        for fields in ([], [{'field_id': 'fldReview', 'field_name': 'Review', 'type': 1}],
                       [{'field_id': 'fldReview', 'field_name': 'Review', 'type': 3, 'property': {'options': []}}]):
            with self.subTest(fields=fields):
                self.remote.client.fields = fields
                with self.assertRaises(ValueError):
                    self.remote.accept(self.project, 'rec1')
        self.assertEqual(self.remote.client.writes, [])
