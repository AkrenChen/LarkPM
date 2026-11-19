from feishu import API, LOCAL_TIMEZONE, Feishu, _date, _text
from urllib.parse import quote
from datetime import date, datetime


class Remote:
    def __init__(self, config_dir):
        self.client = Feishu(config_dir=config_dir)
        self._table_authorization()

    def _table_authorization(self):
        current = self.client.status().get('scope', 'bitable:app offline_access')
        scope = ' '.join(s for s in current.split() if not s.startswith('contact:'))
        if scope != current:
            self.client.configure({'scope': scope or 'bitable:app offline_access'})

    def select(self, project):
        fields = {('parent_id' if k == 'parent' else k): v for k, v in project['fields'].items() if k != 'department'}
        fields.setdefault('acceptance', '验收状态')
        fields.setdefault('priority', '优先级')
        states = {'todo': project.get('todo_value', '未开始'), 'active': project.get('active_value', '进行中'),
                  'done': project.get('done_value', '已完成'), 'paused': project.get('paused_value', '暂停'),
                  'closed': project.get('closed_value', '关闭需求')}
        return self.client.configure({'base_token': project['base_token'], 'table_id': project['table_id'], 'field_map': fields, 'state_map': states})

    def status(self):
        return dict(self.client.status(), **self.client.finish_auth())

    def configure(self, **params):
        if 'scope' in params:
            params['scope'] = ' '.join(s for s in params['scope'].split() if not s.startswith('contact:')) or 'bitable:app offline_access'
        return self.client.configure(params)

    def begin_auth(self):
        self._table_authorization()
        return self.client.begin_auth()

    def finish_auth(self, **params):
        return self.client.finish_auth()

    def records(self, project, schema=None):
        if schema is None:
            self.select(project)
            schema = self.client.schema()['fields']
        mapping = self.client.status()['field_map']
        by_key = {}
        for field in schema:
            name = field.get('field_name', field.get('name', ''))
            by_key[name] = name
            by_key[field.get('field_id', field.get('id', ''))] = name
        for key, value in mapping.items():
            if value and value not in by_key and key in ('title', 'start', 'end', 'owners', 'state'):
                raise ValueError('字段映射不存在：' + value + '，请在项目设置中修正后读取')
        self.client.configure({'field_map': {k: by_key.get(v, v) for k, v in mapping.items()}})
        return self.client.records()

    def read_requirements(self, project):
        self.select(project)
        schema = self.client.schema()['fields']
        records = self.records(project, schema)
        catalogs, warnings = {}, []
        for method, key, message in ((self.versions, 'version_catalog', '版本选项更新失败，已保留上次列表'),
                                     (self.departments, 'department_catalog', '部门选项更新失败，已保留上次列表'),
                                     (self.priorities, 'priority_catalog', '优先级选项更新失败，已保留上次列表')):
            try:
                catalogs[key] = method(project, schema)
                if catalogs[key].get('error'):
                    warnings.append(catalogs[key]['error'])
            except Exception:
                warnings.append(message)
        return dict(records=records, catalogs=catalogs, warning='；'.join(warnings))

    def departments(self, project, schema=None):
        if schema is None:
            self.select(project)
            schema = self.client.schema()['fields']
        key = project.get('fields', {}).get('department', '部门')
        field = next((f for f in schema
                      if key in (f.get('field_name'), f.get('field_id'))), None)
        result = dict(field=key, options=[], error='')
        if not field:
            return dict(result, error='部门字段不存在，请在项目与连接中配置部门字段映射')
        if field.get('type') not in (3, 4):
            return dict(result, error='部门字段必须为单选或多选，请检查字段映射')
        result['options'] = [dict(id=o.get('id', ''), name=o['name'], color=o.get('color'))
                             for o in (field.get('property') or {}).get('options', []) if o.get('name')]
        return result

    def versions(self, project, schema=None):
        if schema is None:
            self.select(project)
            schema = self.client.schema()['fields']
        key = project.get('fields', {}).get('version', '版本')
        field = next((f for f in schema
                      if key in (f.get('field_name'), f.get('field_id'))), None)
        if not field:
            raise ValueError('版本字段不存在，请检查项目字段映射')
        return dict(field=key, selectable=field.get('type') in (3, 4),
                    options=list(dict.fromkeys(o['name'] for o in (field.get('property') or {}).get('options', []) if o.get('name'))))

    def update(self, project, record_id, patch):
        if self.client.status().get('base_token') != project['base_token'] or self.client.status().get('table_id') != project['table_id']:
            raise ValueError('当前连接与回写项目不一致，请重新读取')
        return self.client.update(record_id, patch)

    def priorities(self, project, schema=None):
        if schema is None:
            self.select(project)
            schema = self.client.schema()['fields']
        key = project.get('fields', {}).get('priority', '优先级')
        field = next((field for field in schema if key in (field.get('field_name'), field.get('field_id'))), None)
        return dict(field=key, selectable=bool(field and field.get('type') == 3),
                    options=[option['name'] for option in ((field or {}).get('property') or {}).get('options', []) if option.get('name')])

    def prepare_create(self, project, values):
        self.select(project)
        schema = self.client.schema()['fields']
        mapping = dict(self.client.status()['field_map'], department=project['fields'].get('department', '部门'))
        self._creation_fields = {key: next((field for field in schema if value in (field.get('field_name'), field.get('field_id'))), None) for key, value in mapping.items()}
        self._creation_project = (project['base_token'], project['table_id'])
        self.client.configure({'field_map': {key: field['field_name'] for key, field in self._creation_fields.items() if field and key != 'department'}})
        for value in values:
            self._encode_creation(project, value)

    def _encode_creation(self, project, values):
        result = {}
        kinds = dict(title=(1,), start=(5,), end=(5,), owners=(11,), state=(1, 3), priority=(1, 3), version=(1, 3, 4), departments=(3, 4), parent_id=(18, 21))
        for key, types in kinds.items():
            value = values.get(key)
            if key != 'title' and not value:
                continue
            field = self._creation_fields.get('department' if key == 'departments' else key)
            if not field or field.get('type') not in types or field.get('is_synced'):
                raise ValueError(f'创建所需字段不存在、类型不符或不可写：{key}，请检查项目字段映射')
            if key == 'title':
                if not isinstance(value, str) or not value.strip() or len(value) > 10000:
                    raise ValueError('标题必须是1到10000字的文本')
                value = value.strip()
            elif key in ('start', 'end'):
                parsed = date.fromisoformat(value)
                if parsed.isoformat() != value:
                    raise ValueError('日期格式必须是YYYY-MM-DD')
                value = int(datetime.combine(parsed, datetime.min.time(), LOCAL_TIMEZONE).timestamp() * 1000)
            elif key == 'owners':
                if not isinstance(value, list) or any(not isinstance(person, dict) or not person.get('id') for person in value):
                    raise ValueError('处理人缺少飞书人员ID')
                value = [dict(id=person['id']) for person in value]
                if not (field.get('property') or {}).get('multiple', True) and len(value) > 1:
                    raise ValueError('飞书处理人字段只允许一人')
            elif key == 'state':
                if value not in self.client.status()['state_map']:
                    raise ValueError('未知工作状态')
                value = self.client.status()['state_map'][value]
            elif key == 'parent_id':
                if (field.get('property') or {}).get('table_id') != project['table_id']:
                    raise ValueError('父记录字段必须关联当前需求表')
                value = [value]
            if key in ('version', 'departments'):
                options = value if isinstance(value, list) else [value]
                if field['type'] == 3 and len(options) != 1:
                    raise ValueError('飞书单选字段不能写入多个部门或版本')
                value = options if field['type'] == 4 else options[0]
            if field['type'] in (3, 4):
                allowed = {option['name'] for option in (field.get('property') or {}).get('options', [])}
                if any(option not in allowed for option in (value if isinstance(value, list) else [value])):
                    raise ValueError(f'飞书字段“{field["field_name"]}”没有对应选项，请先在源表配置')
            result[field['field_name']] = value
        return result

    def create(self, project, values, client_token):
        if getattr(self, '_creation_project', None) != (project['base_token'], project['table_id']):
            self.prepare_create(project, [values])
        return self.client.create_record(self._encode_creation(project, values), client_token)

    def accept(self, project, record_id):
        self.select(project)
        key = self.client.status()['field_map'].get('acceptance', '验收状态')
        field = next((f for f in self.client.schema()['fields']
                      if key in (f.get('field_name'), f.get('field_id'))), None)
        if not field or field.get('type') != 3:
            raise ValueError('验收字段不存在或不是单选，请检查项目字段映射')
        if not any(option.get('name') == '验收通过' for option in (field.get('property') or {}).get('options', [])):
            raise ValueError('飞书验收字段中没有“验收通过”选项，请先在源表配置')
        self.client.configure({'field_map': {'acceptance': field['field_name']}})
        result = self.client.update(record_id, {'acceptance': '验收通过'})
        if result.get('acceptance') != '验收通过':
            raise ValueError('飞书未返回验收通过状态，请重新读取飞书核实后重试')
        return result

    def source_rows(self, source, kind):
        base = source.get('base_token', '')
        if not base:
            raise ValueError('Wiki 表请在关联表配置中填写真实 Base Token（在飞书中打开为多维表格后获取）')
        table_url = API + '/bitable/v1/apps/' + quote(base, safe='') + '/tables/' + quote(source['table_id'], safe='')
        schema = self.client._pages('fields', 100, table_url)
        keys = {alias: f['field_name'] for f in schema for alias in (f['field_id'], f['field_name'])}
        mapping = dict(source['fields'])
        if kind == 'versions' and 'submitted' not in mapping:
            submission = next((name for name in ('提审时间', '提审日期') if name in keys), None)
            if submission:
                mapping['submitted'] = submission
        for value in mapping.values():
            if value not in keys:
                raise ValueError('关联表字段不存在：' + value)
        rows = []
        for record in self.client._pages('records', 500, table_url):
            fields = record.get('fields', {})
            row = dict(id=record['record_id'])
            for key, field in mapping.items():
                value = fields.get(keys[field])
                row[key] = _date(value) if key in ('start', 'end', 'submitted') else _text(value)
                if key == 'released' and isinstance(value, (int, float)):
                    from datetime import datetime
                    row[key] = datetime.fromtimestamp(value / 1000, LOCAL_TIMEZONE).isoformat()
            rows.append(row)
        return rows
