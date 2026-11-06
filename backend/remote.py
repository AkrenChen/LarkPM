from feishu import API, LOCAL_TIMEZONE, Feishu, _date, _text
from urllib.parse import quote


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

    def records(self, project):
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

    def departments(self, project):
        self.select(project)
        key = project.get('fields', {}).get('department', '部门')
        field = next((f for f in self.client.schema()['fields']
                      if key in (f.get('field_name'), f.get('field_id'))), None)
        result = dict(field=key, options=[], error='')
        if not field:
            return dict(result, error='部门字段不存在，请在项目与连接中配置部门字段映射')
        if field.get('type') not in (3, 4):
            return dict(result, error='部门字段必须为单选或多选，请检查字段映射')
        result['options'] = [dict(id=o.get('id', ''), name=o['name'], color=o.get('color'))
                             for o in (field.get('property') or {}).get('options', []) if o.get('name')]
        return result

    def update(self, project, record_id, patch):
        if self.client.status().get('base_token') != project['base_token'] or self.client.status().get('table_id') != project['table_id']:
            raise ValueError('当前连接与回写项目不一致，请重新读取')
        return self.client.update(record_id, patch)

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
