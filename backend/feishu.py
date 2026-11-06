import base64
import ctypes
import hashlib
import json
import os
import re
import secrets
import threading
import time
from ctypes import wintypes
from datetime import date, datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlencode, urlparse
from urllib.request import Request, urlopen


API = 'https://open.feishu.cn/open-apis'
AUTHORIZE = 'https://accounts.feishu.cn/open-apis/authen/v1/authorize'
TOKEN = API + '/authen/v2/oauth/token'
LOCAL_TIMEZONE = timezone(timedelta(hours=8))
DEFAULT_FIELDS = {'title': '需求内容', 'start': '开始时间', 'end': '截止时间',
                  'owners': '处理人', 'state': '开发状态', 'parent_id': '父记录',
                  'version': '版本', 'description': '需求描述及反馈', 'acceptance': '验收状态'}
DEFAULT_STATES = {'todo': '未开始', 'active': '进行中', 'done': '已完成',
                  'paused': '暂停', 'closed': '关闭需求'}


class FeishuError(ValueError):
    pass


def _dpapi(data, encrypt):
    if os.name != 'nt':
        raise FeishuError('飞书凭证加密需要 Windows DPAPI，当前系统不支持。')

    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]

    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    crypt32 = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    if encrypt:
        function = crypt32.CryptProtectData
        function.argtypes = [ctypes.POINTER(Blob), wintypes.LPCWSTR, ctypes.c_void_p,
                             ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        success = function(ctypes.byref(source), 'LarkPM', None, None, None, 1, ctypes.byref(target))
    else:
        function = crypt32.CryptUnprotectData
        function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                             ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        success = function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target))
    if not success:
        raise FeishuError('无法加密或解密本机飞书凭证，请在原 Windows 用户下使用或重新配置授权。')
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        kernel32.LocalFree(target.data)


def _atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + secrets.token_hex(6) + '.tmp')
    try:
        temporary.write_bytes(data)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _text(value):
    if value is None:
        return ''
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return ''.join(str(item.get('text', item.get('name', ''))) if isinstance(item, dict)
                       else str(item) for item in value)
    if isinstance(value, dict):
        return str(value.get('text', value.get('name', '')))
    return str(value)


def _date(value):
    if value is None or value == '':
        return ''
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000, LOCAL_TIMEZONE).date().isoformat()
    text = _text(value)
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        raise FeishuError('飞书日期无法解析，请检查日期字段映射。') from None


class Feishu:
    def __init__(self, config_dir=None, *, transport=None, protect=None, unprotect=None, clock=None):
        self.directory = Path(config_dir) if config_dir else Path(
            os.environ.get('LOCALAPPDATA', Path.home() / '.local' / 'share')) / 'LarkPM' / 'feishu'
        self._transport = transport or self._http
        self._protect = protect or (lambda value: _dpapi(value, True))
        self._unprotect = unprotect or (lambda value: _dpapi(value, False))
        self._clock = clock or time.time
        self._lock = threading.RLock()
        self._server = None
        self._timer = None
        self._auth = {'state': 'idle', 'message': ''}
        self._config = {'redirect_uri': 'http://127.0.0.1:18765/callback',
                        'scope': 'bitable:app offline_access', 'field_map': dict(DEFAULT_FIELDS),
                        'state_map': dict(DEFAULT_STATES)}
        self._secrets = {}
        self._tokens = {}
        try:
            config_file = self.directory / 'config.json'
            if config_file.exists():
                self._config.update(json.loads(config_file.read_text(encoding='utf-8')))
            credentials = self.directory / 'credentials.bin'
            if credentials.exists():
                self._secrets = json.loads(self._unprotect(credentials.read_bytes()).decode('utf-8'))
                self._tokens = self._secrets.get('tokens', {})
        except (OSError, ValueError) as error:
            raise FeishuError('飞书本地配置或加密凭证无法读取，请恢复备份或重新配置。') from error

    def _redact(self, message):
        result = str(message)
        sensitive = [self._secrets.get('app_secret'), self._tokens.get('access_token'),
                     self._tokens.get('refresh_token'), self._auth.get('code_verifier'),
                     self._auth.get('oauth_state')]
        for value in sensitive:
            if value:
                result = result.replace(str(value), '[已隐藏]')
        return result[:600]

    def _save_credentials(self):
        payload = dict(self._secrets, tokens=self._tokens)
        _atomic(self.directory / 'credentials.bin', self._protect(
            json.dumps(payload, ensure_ascii=False).encode('utf-8')))

    def status(self):
        with self._lock:
            public = {key: self._config.get(key) for key in (
                'app_id', 'base_token', 'table_id', 'redirect_uri', 'scope', 'field_map', 'state_map')}
            public.update(configured=bool(self._config.get('app_id') and self._secrets.get('app_secret')
                                          and self._config.get('base_token') and self._config.get('table_id')),
                          authorized=bool(self._tokens.get('access_token')),
                          app_secret_configured=bool(self._secrets.get('app_secret')),
                          expires_at=self._tokens.get('expires_at', 0))
            return public

    def configure(self, params):
        if not isinstance(params, dict):
            raise FeishuError('配置必须是对象。')
        with self._lock:
            updated = dict(self._config)
            for key in ('app_id', 'base_token', 'table_id', 'redirect_uri', 'scope'):
                if key in params:
                    updated[key] = str(params[key]).strip()
            for key in ('app_id', 'base_token', 'table_id'):
                if updated.get(key) and not re.fullmatch(r'[A-Za-z0-9_-]+', updated[key]):
                    raise FeishuError('应用、需求表标识只接受字母、数字、下划线和连字符。')
            parsed = urlparse(updated['redirect_uri'])
            if (parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or
                    not parsed.port or parsed.username or parsed.query or parsed.fragment or
                    parsed.path != '/callback'):
                raise FeishuError('授权回调必须是 http://127.0.0.1:端口/callback。')
            for key, alias, defaults in (('field_map', 'fields', DEFAULT_FIELDS), ('state_map', 'state_map', DEFAULT_STATES)):
                mapping = params.get(key, params.get(alias))
                if mapping is not None:
                    if not isinstance(mapping, dict) or any(k not in defaults for k in mapping):
                        raise FeishuError('字段或状态映射包含不支持的键。')
                    if any(not isinstance(v, str) for v in mapping.values()):
                        raise FeishuError('字段或状态映射值必须是字符串。')
                    updated[key] = dict(updated.get(key, defaults), **mapping)
            if not updated['field_map'].get('title') or not updated['field_map'].get('state'):
                raise FeishuError('标题与工作状态字段必须配置。')
            states = updated['state_map']
            if any(not value for value in states.values()) or len(set(states.values())) != len(states):
                raise FeishuError('工作状态映射必须非空且不能重复。')
            app_changed = self._config.get('app_id') != updated.get('app_id')
            if app_changed:
                self.close()
                self._tokens = {}
                self._secrets = {}
            if params.get('app_secret'):
                self._secrets['app_secret'] = str(params['app_secret']).strip()
            self._config = updated
            self._save_credentials()
            _atomic(self.directory / 'config.json', json.dumps(updated, ensure_ascii=False, indent=2).encode('utf-8'))
            return self.status()

    def _http(self, method, url, headers, body):
        data = None if body is None else json.dumps(body, ensure_ascii=False).encode('utf-8')
        request = Request(url, data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode('utf-8'))
        except HTTPError as error:
            try:
                payload = json.loads(error.read().decode('utf-8'))
                message = payload.get('msg') or payload.get('error_description') or '请求被拒绝'
            except (ValueError, OSError):
                message = '请求被拒绝'
            raise FeishuError(self._redact(f'飞书 HTTP {error.code}：{message}')) from None
        except (URLError, TimeoutError, ValueError, OSError):
            raise FeishuError('无法连接飞书服务或响应格式不正确，请检查网络后重试。') from None

    def _request(self, method, url, body=None, authenticated=True):
        headers = {'Content-Type': 'application/json; charset=utf-8', 'Accept': 'application/json'}
        if authenticated:
            headers['Authorization'] = 'Bearer ' + self._access_token()
        payload = self._transport(method, url, headers, body)
        if not isinstance(payload, dict):
            raise FeishuError('飞书响应格式不正确。')
        if payload.get('code', 0) != 0 or payload.get('error'):
            code = payload.get('code', payload.get('error'))
            message = payload.get('msg') or payload.get('error_description') or '请求失败'
            raise FeishuError(self._redact(f'飞书错误 {code}：{message}'))
        return payload

    def _save_tokens(self, payload):
        token = payload.get('access_token') or payload.get('user_access_token')
        if not token:
            raise FeishuError('飞书授权响应缺少用户凭证，请重新登录。')
        self._tokens = {
            'access_token': token,
            'refresh_token': payload.get('refresh_token', self._tokens.get('refresh_token', '')),
            'expires_at': self._clock() + int(payload.get('expires_in', 7200)),
        }
        self._save_credentials()

    def _access_token(self):
        with self._lock:
            if self._tokens.get('access_token') and self._tokens.get('expires_at', 0) > self._clock() + 90:
                return self._tokens['access_token']
            refresh = self._tokens.get('refresh_token')
            if not refresh:
                raise FeishuError('请先在设置中使用飞书账号授权登录。')
            payload = self._request('POST', TOKEN, {
                'grant_type': 'refresh_token', 'client_id': self._config.get('app_id'),
                'client_secret': self._secrets.get('app_secret'), 'refresh_token': refresh,
            }, authenticated=False)
            self._save_tokens(payload.get('data', payload))
            return self._tokens['access_token']

    def begin_auth(self):
        with self._lock:
            if not self.status()['configured']:
                raise FeishuError('请先配置飞书自建应用与需求表。')
            self.close()
            self._auth = {'state': 'waiting', 'message': '等待浏览器授权',
                          'oauth_state': secrets.token_urlsafe(32),
                          'code_verifier': secrets.token_urlsafe(48),
                          'expires_at': self._clock() + 300}
            client = self

            class Callback(BaseHTTPRequestHandler):
                def log_message(self, *args):
                    pass

                def do_GET(self):
                    parsed = urlparse(self.path)
                    if parsed.path != '/callback':
                        self.send_error(404)
                        return
                    query = parse_qs(parsed.query)
                    try:
                        client._finish_callback(query)
                        message = '授权成功，可以关闭此页面并返回 LarkPM。'
                        status = 200
                    except FeishuError:
                        message = '授权未完成，请返回 LarkPM 查看状态并重新授权。'
                        status = 400
                    content = ('<!doctype html><meta charset="utf-8"><title>LarkPM</title><p>' + message + '</p>').encode('utf-8')
                    self.send_response(status)
                    self.send_header('Content-Type', 'text/html; charset=utf-8')
                    self.send_header('Cache-Control', 'no-store')
                    self.send_header('Content-Security-Policy', "default-src 'none'")
                    self.send_header('Content-Length', str(len(content)))
                    self.end_headers()
                    self.wfile.write(content)

            parsed = urlparse(self._config['redirect_uri'])
            try:
                self._server = ThreadingHTTPServer(('127.0.0.1', parsed.port), Callback)
            except OSError:
                self._auth = {'state': 'error', 'message': '本地授权回调端口已占用，请关闭旧授权或更换端口。'}
                raise FeishuError(self._auth['message']) from None
            self._server.daemon_threads = True
            threading.Thread(target=self._server.serve_forever, kwargs={'poll_interval': 0.2}, daemon=True).start()
            self._timer = threading.Timer(300, self._expire_auth)
            self._timer.daemon = True
            self._timer.start()
            challenge = base64.urlsafe_b64encode(hashlib.sha256(
                self._auth['code_verifier'].encode('ascii')).digest()).rstrip(b'=').decode('ascii')
            query = {'client_id': self._config['app_id'], 'response_type': 'code',
                     'redirect_uri': self._config['redirect_uri'], 'scope': self._config['scope'],
                     'state': self._auth['oauth_state'], 'code_challenge': challenge,
                     'code_challenge_method': 'S256'}
            return {'url': AUTHORIZE + '?' + urlencode(query), 'expires_at': self._auth['expires_at']}

    def _finish_callback(self, query):
        with self._lock:
            state = query.get('state', [''])[0]
            if (self._auth.get('state') != 'waiting' or self._clock() >= self._auth.get('expires_at', 0)
                    or not secrets.compare_digest(state, self._auth.get('oauth_state', ''))):
                raise FeishuError('授权状态校验失败或已过期。')
            if query.get('error') or not query.get('code'):
                self._auth = {'state': 'error', 'message': '授权被取消或未取得授权码。'}
                raise FeishuError(self._auth['message'])
            try:
                result = self._request('POST', TOKEN, {
                    'grant_type': 'authorization_code', 'client_id': self._config['app_id'],
                    'client_secret': self._secrets['app_secret'], 'code': query['code'][0],
                    'redirect_uri': self._config['redirect_uri'], 'code_verifier': self._auth['code_verifier'],
                }, authenticated=False)
                self._save_tokens(result.get('data', result))
                self._auth = {'state': 'authorized', 'message': '飞书账号已授权'}
            except FeishuError as error:
                self._auth = {'state': 'error', 'message': self._redact(error)}
                raise
            finally:
                threading.Thread(target=self.close, daemon=True).start()

    def _expire_auth(self):
        with self._lock:
            if self._auth.get('state') == 'waiting':
                self._auth = {'state': 'expired', 'message': '授权已超时，请重新登录。'}
        self.close()

    def finish_auth(self):
        with self._lock:
            return {'state': self._auth.get('state'), 'message': self._auth.get('message', ''),
                    'authorized': bool(self._tokens.get('access_token')) and
                                  self._auth.get('state') in ('idle', 'authorized')}

    def close(self):
        if self._timer:
            self._timer.cancel()
            self._timer = None
        server, self._server = self._server, None
        if server:
            server.shutdown()
            server.server_close()

    def _table_url(self):
        base, table = self._config.get('base_token'), self._config.get('table_id')
        if not base or not table:
            raise FeishuError('请先配置需求表的 Base token 和 Table ID。')
        return API + '/bitable/v1/apps/' + quote(base, safe='') + '/tables/' + quote(table, safe='')

    def _pages(self, resource, page_size, table_url=None):
        items, page_token, seen = [], '', set()
        while True:
            query = {'page_size': page_size}
            if resource == 'records':
                query['user_id_type'] = 'open_id'
            if page_token:
                query['page_token'] = page_token
            response = self._request('GET', (table_url or self._table_url()) + '/' + resource + '?' + urlencode(query))
            data = response.get('data')
            if not isinstance(data, dict) or not isinstance(data.get('items', []), list):
                raise FeishuError('飞书分页响应格式不正确。')
            items.extend(data.get('items', []))
            if not data.get('has_more'):
                return items
            page_token = data.get('page_token')
            if not page_token or page_token in seen:
                raise FeishuError('飞书分页标记缺失或重复，未将部分数据当作完整结果。')
            seen.add(page_token)

    def schema(self):
        return {'fields': self._pages('fields', 100), 'field_map': self._config['field_map'],
                'state_map': self._config['state_map']}

    def _normalize(self, record):
        record_id = record.get('record_id')
        if not record_id:
            raise FeishuError('飞书记录缺少 record_id。')
        fields, mapping = record.get('fields', {}), self._config['field_map']

        def cell(key):
            return fields.get(mapping.get(key, ''))

        owners = cell('owners') or []
        if isinstance(owners, dict):
            owners = [owners]
        people = [{'id': str(person['id']), 'name': str(person.get('name') or person['id'])}
                  for person in owners if isinstance(person, dict) and person.get('id')]
        parent_value = cell('parent_id') or []
        if isinstance(parent_value, (dict, str)):
            parent_value = [parent_value]
        parents = []
        for item in parent_value:
            if isinstance(item, dict):
                ids = item.get('record_ids') or [item.get('record_id') or item.get('id')]
            else:
                ids = [item]
            for parent_id in ids:
                if isinstance(parent_id, str) and parent_id and parent_id not in parents:
                    parents.append(parent_id)
        remote_state = _text(cell('state'))
        states = {value: key for key, value in self._config['state_map'].items()}
        state = states.get(remote_state, 'paused' if remote_state else 'todo')
        return {'id': 'fs:' + record_id, 'record_id': record_id,
                'title': _text(cell('title')), 'start': _date(cell('start')), 'end': _date(cell('end')),
                'owners': people, 'state': state, 'remote_state': remote_state,
                'state_unmapped': bool(remote_state and remote_state not in states),
                'module': parents[0] if parents else '', 'parent_id': parents[0] if parents else '',
                'parents': parents, 'version': _text(cell('version')),
                'description': _text(cell('description')),
                'acceptance': _text(fields.get(mapping.get('acceptance', '验收状态')))}

    def records(self):
        return [self._normalize(record) for record in self._pages('records', 500)]

    def get(self, record_id):
        if not re.fullmatch(r'[A-Za-z0-9_-]+', str(record_id)):
            raise FeishuError('飞书记录 ID 不合法。')
        payload = self._request('GET', self._table_url() + '/records/' + quote(record_id, safe='')
                                + '?user_id_type=open_id')
        return self._normalize(payload.get('data', {}).get('record', {}))

    def update(self, record_id, fields):
        if not re.fullmatch(r'[A-Za-z0-9_-]+', str(record_id)):
            raise FeishuError('飞书记录 ID 不合法。')
        if not isinstance(fields, dict) or not fields:
            raise FeishuError('请选择至少一个需要写回的字段。')
        allowed = {'title', 'start', 'end', 'owners', 'state'}
        if fields.keys() - allowed:
            raise FeishuError('只允许写回标题、起止时间、处理人及工作状态；不会修改验收或个人笔记。')
        result = {}
        for key, value in fields.items():
            field_name = self._config['field_map'].get(key)
            if not field_name:
                raise FeishuError('所选字段尚未配置映射。')
            if key == 'title':
                if not isinstance(value, str) or not value.strip() or len(value) > 10000:
                    raise FeishuError('标题必须是 1 到 10000 字的文本。')
                converted = value.strip()
            elif key in ('start', 'end'):
                if value in ('', None):
                    converted = None
                else:
                    try:
                        parsed = date.fromisoformat(value)
                        if parsed.isoformat() != value:
                            raise ValueError()
                    except (ValueError, TypeError):
                        raise FeishuError('日期必须使用有效的 YYYY-MM-DD 格式。') from None
                    converted = int(datetime.combine(parsed, datetime.min.time(), LOCAL_TIMEZONE).timestamp() * 1000)
            elif key == 'owners':
                if not isinstance(value, list) or any(not isinstance(person, dict) or
                        not isinstance(person.get('id'), str) or not person['id'].strip() for person in value):
                    raise FeishuError('处理人必须包含飞书 open_id，不能仅提交显示姓名。')
                converted = [{'id': person['id']} for person in value] if value else None
            else:
                if value not in self._config['state_map']:
                    raise FeishuError('所选工作状态不受支持。')
                converted = self._config['state_map'][value]
            result[field_name] = converted
        payload = self._request('PUT', self._table_url() + '/records/' + quote(record_id, safe='')
                                + '?user_id_type=open_id', {'fields': result})
        return self._normalize(payload.get('data', {}).get('record', {}))

    authorize = begin_auth
    begin_login = begin_auth
    auth_status = finish_auth
    fetch = records
    write = update


FeishuClient = Feishu
