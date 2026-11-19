import base64
import json
import sys
import tempfile
import time
import unittest
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.error import HTTPError
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from feishu import Feishu, FeishuError


class FakeTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, headers, body))
        if not self.responses:
            raise AssertionError('Unexpected HTTP request')
        return self.responses.pop(0)


class FeishuTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def test_http_ignores_unavailable_system_proxy(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"code":0}')

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.addCleanup(server.server_close)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.shutdown)
        client, _ = self.client()
        with patch('urllib.request.getproxies', return_value={'http': 'http://127.0.0.1:1'}), patch('urllib.request.proxy_bypass', return_value=False):
            result = client._http('GET', f'http://127.0.0.1:{server.server_port}/', {}, None)
        self.assertEqual(result, {'code': 0})

    def client(self, responses=(), **options):
        transport = FakeTransport(responses)
        client = Feishu(Path(self.temp.name), transport=transport,
                        protect=lambda b: base64.b64encode(b),
                        unprotect=lambda b: base64.b64decode(b), **options)
        client.configure({'app_id': 'cli_example', 'app_secret': 'private-example',
                          'base_token': 'base_example', 'table_id': 'tbl_example'})
        client._tokens = {'access_token': 'fake-token', 'expires_at': time.time() + 7200}
        return client, transport

    def test_paginates_records_and_maps_people_and_dates(self):
        client, http = self.client([
            {'code': 0, 'data': {'items': [{'record_id': 'rec1', 'fields': {
                '需求内容': [{'type': 'text', 'text': 'Title'}],
                '处理人': [{'id': 'ou_1', 'name': 'Person'}],
                '开发状态': '进行中', '开始时间': 1793808000000,
                '截止时间': 1793894400000, '父记录': ['recParent'], '版本': 'v1'}}],
                'has_more': True, 'page_token': 'next page'}},
            {'code': 0, 'data': {'items': [{'record_id': 'rec2', 'fields': {
                '需求内容': 'Second', '开发状态': '已完成'}}], 'has_more': False}}
        ])
        tasks = client.records()
        self.assertEqual(len(tasks), 2)
        self.assertEqual(tasks[0]['owners'], [{'id': 'ou_1', 'name': 'Person'}])
        self.assertEqual(tasks[0]['state'], 'active')
        self.assertEqual(tasks[0]['start'], '2026-11-05')
        self.assertEqual(tasks[0]['end'], '2026-11-06')
        self.assertEqual(tasks[0]['record_id'], 'rec1')
        self.assertEqual(tasks[0]['parents'], ['recParent'])
        self.assertEqual(tasks[1]['state'], 'done')
        query = parse_qs(urlparse(http.calls[1][1]).query)
        self.assertEqual(query['page_token'], ['next page'])
        self.assertEqual(query['user_id_type'], ['open_id'])

    def test_parent_lookup_cells_with_record_ids_and_empty_metadata(self):
        client, _ = self.client()
        for value, expected in [
            ([{'type': 'text', 'table_id': 'tbl1', 'record_ids': ['recParent'], 'text': 'Module'}], ['recParent']),
            ([{'type': 'text', 'table_id': 'tbl1', 'text_arr': []}], []),
            ({'record_ids': ['recParent', 'recOther']}, ['recParent', 'recOther']),
            ([{'record_id': 'recParent'}, {'id': 'recOther'}], ['recParent', 'recOther']),
            ([None, {}, {'record_ids': []}], []),
        ]:
            with self.subTest(value=value):
                result = client._normalize({'record_id': 'rec1', 'fields': {'父记录': value}})
                self.assertEqual(result['parents'], expected)
                self.assertEqual(result['module'], expected[0] if expected else '')

    def test_acceptance_is_read_separately_from_work_state(self):
        client, _ = self.client()
        task = client._normalize({'record_id': 'rec1', 'fields': {
            '开发状态': '进行中', '验收状态': '验收通过'}})
        self.assertEqual(task['acceptance'], '验收通过')
        self.assertEqual(task['state'], 'active')
        self.assertEqual(client._normalize({'record_id': 'rec2', 'fields': {}})['acceptance'], '')

    def test_remote_records_accepts_acceptance_mapping_end_to_end(self):
        from remote import Remote
        client, _ = self.client([
            {'code': 0, 'data': {'items': [
                {'field_id': 'fldTitle', 'field_name': '需求内容'},
                {'field_id': 'fldState', 'field_name': '开发状态'},
                {'field_id': 'fldAcceptance', 'field_name': '验收状态'},
                {'field_id': 'fldStart', 'field_name': '开始时间'},
                {'field_id': 'fldEnd', 'field_name': '截止时间'},
                {'field_id': 'fldOwners', 'field_name': '处理人'},
            ], 'has_more': False}},
            {'code': 0, 'data': {'items': [{'record_id': 'rec1', 'fields': {
                '需求内容': '需求', '开发状态': '已完成', '验收状态': '验收通过',
            }}], 'has_more': False}},
        ])
        remote = Remote.__new__(Remote)
        remote.client = client
        rows = remote.records(dict(base_token='base_example', table_id='tbl_example',
                                   fields=dict(title='需求内容', state='开发状态')))
        self.assertEqual(rows[0]['acceptance'], '验收通过')
        self.assertEqual(rows[0]['state'], 'done')

    def test_configurable_field_mapping_for_another_project(self):
        client, _ = self.client([{'code': 0, 'data': {'items': [
            {'record_id': 'recX', 'fields': {'Summary': 'Other', 'Status': 'Shipped'}}],
            'has_more': False}}])
        client.configure({'field_map': {'title': 'Summary', 'state': 'Status'},
                          'state_map': {'todo': 'Queued', 'active': 'Building',
                                        'done': 'Shipped', 'paused': 'Held', 'closed': 'Closed'}})
        self.assertEqual(client.records()[0]['state'], 'done')

    def test_write_only_selected_fields(self):
        client, http = self.client([{'code': 0, 'data': {'record': {
            'record_id': 'rec1', 'fields': {'需求内容': 'Changed', '开发状态': '已完成'}}}}])
        result = client.update('rec1', {'title': 'Changed', 'state': 'done'})
        self.assertEqual(http.calls[0][0], 'PUT')
        self.assertEqual(http.calls[0][3], {'fields': {'需求内容': 'Changed', '开发状态': '已完成'}})
        self.assertEqual(result['state'], 'done')

    def test_create_record_uses_uuid_idempotency_and_requires_record_id(self):
        token = 'fe599b60-450f-46ff-b2ef-9f6675625b97'
        client, http = self.client([{'code': 0, 'data': {'record': {'record_id': 'new', 'fields': {'需求内容': '新需求'}}}}, {'code': 0, 'data': {}}])
        result = client.create_record({'需求内容': '新需求'}, token)
        self.assertEqual(result['record_id'], 'new')
        self.assertEqual(http.calls[0][0], 'POST')
        self.assertIn('client_token=' + token, http.calls[0][1])
        self.assertEqual(http.calls[0][3], {'fields': {'需求内容': '新需求'}})
        with self.assertRaisesRegex(FeishuError, '记录ID'):
            client.create_record({'需求内容': '新需求'}, token)
        before = len(http.calls)
        with self.assertRaises(FeishuError):
            client.create_record({'需求内容': '新需求'}, 'invalid')
        self.assertEqual(len(http.calls), before)

    def test_creation_schema_maps_dates_people_version_department_and_parent(self):
        from remote import Remote
        fields = [dict(field_id='fld' + str(i), field_name=name, type=kind, property=prop) for i, (name, kind, prop) in enumerate([
            ('标题', 1, {}), ('开发状态', 3, {'options': [{'name': '进行中'}, {'name': '未开始'}]}),
            ('开始时间', 5, {}), ('截止时间', 5, {}), ('处理人', 11, {'multiple': True}),
            ('版本', 4, {'options': [{'name': 'v1'}]}), ('部门', 3, {'options': [{'name': '开发'}]}),
            ('父记录', 18, {'table_id': 'tbl_example'})])]
        client, http = self.client([{'code': 0, 'data': {'items': fields}}, {'code': 0, 'data': {'record': {'record_id': 'new', 'fields': {'标题': '任务'}}}}])
        remote = Remote.__new__(Remote)
        remote.client = client
        project = dict(base_token='base_example', table_id='tbl_example', fields=dict(title='fld0', state='开发状态', start='开始时间', end='截止时间', owners='处理人', parent='父记录', version='版本', department='部门'))
        values = dict(title='任务', state='active', start='2026-11-05', end='', owners=[{'id': 'ou_1', 'name': '人名'}], version='v1', departments=['开发'], parent_id='recParent')
        remote.prepare_create(project, [values])
        remote.create(project, values, 'fe599b60-450f-46ff-b2ef-9f6675625b97')
        self.assertEqual(http.calls[-1][3]['fields'], {'标题': '任务', '开发状态': '进行中', '开始时间': 1793808000000, '处理人': [{'id': 'ou_1'}], '版本': ['v1'], '部门': '开发', '父记录': ['recParent']})
        before = len(http.calls)
        for patch in [dict(version='unknown'), dict(departments=['开发', 'UI'])]:
            with self.assertRaises(ValueError):
                remote.create(project, dict(values, **patch), 'fe599b60-450f-46ff-b2ef-9f6675625b97')
        remote._creation_fields['parent_id']['type'] = 19
        with self.assertRaisesRegex(ValueError, 'parent_id'):
            remote.create(project, values, 'fe599b60-450f-46ff-b2ef-9f6675625b97')
        self.assertEqual(len(http.calls), before)

    def test_explicit_acceptance_write_uses_mapped_field_only(self):
        client, http = self.client([{'code': 0, 'data': {'record': {
            'record_id': 'rec1', 'fields': {'Review': '验收通过'}}}}])
        client.configure({'field_map': {'acceptance': 'Review'}})
        self.assertEqual(client.update('rec1', {'acceptance': '验收通过'})['acceptance'], '验收通过')
        self.assertEqual(http.calls[0][3], {'fields': {'Review': '验收通过'}})

    def test_write_people_and_date_clears_use_rest_shapes(self):
        client, http = self.client([{'code': 0, 'data': {'record': {'record_id': 'rec1', 'fields': {}}}}])
        client.update('rec1', {'start': '2026-11-05', 'end': '', 'owners': [{'id': 'ou_1', 'name': 'Name'}]})
        fields = http.calls[0][3]['fields']
        self.assertEqual(fields['开始时间'], 1793808000000)
        self.assertIsNone(fields['截止时间'])
        self.assertEqual(fields['处理人'], [{'id': 'ou_1'}])

    def test_rejects_unsupported_fields_bad_dates_and_owner_without_id(self):
        client, http = self.client()
        for changes in ({'acceptance': 'invented'}, {'description': 'private'}, {'end': '2026-02-30'},
                        {'owners': [{'name': 'Name'}]}, {'state': 'invented'}):
            with self.subTest(changes=changes), self.assertRaises(FeishuError):
                client.update('rec1', changes)
        self.assertEqual(http.calls, [])

    def test_missing_pagination_token_is_error_not_partial_success(self):
        client, _ = self.client([{'code': 0, 'data': {'items': [], 'has_more': True}}])
        with self.assertRaisesRegex(FeishuError, '分页'):
            client.records()

    def test_expired_token_refreshes_before_read(self):
        client, http = self.client([
            {'code': 0, 'access_token': 'renewed', 'refresh_token': 'new-refresh', 'expires_in': 7200},
            {'code': 0, 'data': {'items': [], 'has_more': False}}
        ])
        client._tokens = {'access_token': 'old', 'refresh_token': 'refresh', 'expires_at': 0}
        self.assertEqual(client.records(), [])
        self.assertEqual(http.calls[0][3]['grant_type'], 'refresh_token')
        self.assertEqual(http.calls[1][2]['Authorization'], 'Bearer renewed')
        self.assertNotIn('renewed', json.dumps(client.status()))

    def test_schema_paginates(self):
        client, http = self.client([
            {'code': 0, 'data': {'items': [{'field_name': 'One', 'field_id': 'fld1'}],
                                'has_more': True, 'page_token': 'two'}},
            {'code': 0, 'data': {'items': [{'field_name': 'Two', 'field_id': 'fld2'}], 'has_more': False}}
        ])
        self.assertEqual(len(client.schema()['fields']), 2)
        self.assertIn('page_token=two', http.calls[1][1])

    def test_secrets_are_not_in_plain_configuration_or_status(self):
        client, _ = self.client()
        self.assertNotIn('private-example', (Path(self.temp.name) / 'config.json').read_text(encoding='utf-8'))
        self.assertNotIn('private-example', json.dumps(client.status()))
        self.assertTrue((Path(self.temp.name) / 'credentials.bin').exists())

    def test_auth_rejects_non_loopback_callback_before_listening(self):
        client, _ = self.client()
        with self.assertRaises(FeishuError):
            client.configure({'redirect_uri': 'http://example.com/callback'})

    def test_unknown_remote_state_is_not_misrepresented_as_todo(self):
        client, _ = self.client([{'code': 0, 'data': {'items': [
            {'record_id': 'rec1', 'fields': {'需求内容': 'Task', '开发状态': 'New Custom State'}}],
            'has_more': False}}])
        task = client.records()[0]
        self.assertEqual(task['remote_state'], 'New Custom State')
        self.assertTrue(task['state_unmapped'])
        self.assertEqual(task['state'], 'paused')

    def test_api_error_redacts_token_and_secret(self):
        client, _ = self.client([{'code': 999, 'msg': 'fake-token private-example broken'}])
        with self.assertRaises(FeishuError) as error:
            client.records()
        self.assertNotIn('fake-token', str(error.exception))
        self.assertNotIn('private-example', str(error.exception))

    def test_loopback_authorization_uses_pkce_and_saves_token(self):
        client, http = self.client([{'code': 0, 'access_token': 'authorized-token',
                                    'refresh_token': 'authorized-refresh', 'expires_in': 7200}])
        client._tokens = {}
        with socket.socket() as reserve:
            reserve.bind(('127.0.0.1', 0))
            port = reserve.getsockname()[1]
        client.configure({'redirect_uri': f'http://127.0.0.1:{port}/callback'})
        self.addCleanup(client.close)
        authorization = client.begin_auth()
        query = parse_qs(urlparse(authorization['url']).query)
        self.assertEqual(query['code_challenge_method'], ['S256'])
        self.assertNotIn('private-example', authorization['url'])
        self.assertEqual(client.finish_auth()['state'], 'waiting')
        with self.assertRaises(HTTPError):
            urlopen(f'http://127.0.0.1:{port}/callback?code=fake-code&state=wrong', timeout=5)
        self.assertEqual(client.finish_auth()['state'], 'waiting')
        with urlopen(f'http://127.0.0.1:{port}/callback?code=fake-code&state={query["state"][0]}', timeout=5) as response:
            self.assertEqual(response.status, 200)
        self.assertEqual(client.finish_auth()['state'], 'authorized')
        self.assertEqual(http.calls[0][3]['grant_type'], 'authorization_code')
        self.assertIn('code_verifier', http.calls[0][3])

    def test_projects_have_separate_configuration_and_credentials(self):
        a, _ = self.client()
        with tempfile.TemporaryDirectory() as other:
            b = Feishu(other, protect=base64.b64encode, unprotect=base64.b64decode)
            self.assertFalse(b.status()['configured'])
            b.configure({'app_id': 'cli_other', 'app_secret': 'other-secret',
                         'base_token': 'other_base', 'table_id': 'tbl_other'})
            self.assertEqual(a.status()['app_id'], 'cli_example')
            self.assertEqual(b.status()['app_id'], 'cli_other')


if __name__ == '__main__':
    unittest.main()
