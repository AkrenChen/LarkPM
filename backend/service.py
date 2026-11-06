import json
import pathlib
import sys
import urllib.parse

from workspace import Conflict, FIELDS, Workspace, data_dir
from project_sources import normalize_source, refreshed_cache

DEFAULT_FIELDS = dict(title='需求内容', start='开始时间', end='截止时间', owners='处理人', state='开发状态', parent='父记录', version='版本', description='需求描述及反馈', department='部门')


class Service:
    def __init__(self, path=None, remote=None):
        self.w = Workspace(path)
        if remote is None:
            from remote import Remote
            remote = Remote(config_dir=(pathlib.Path(path).parent if path else data_dir()) / 'auth')
        self.remote = remote

    def project(self, project_id):
        found = next((p for p in self.w.projects() if p['id'] == project_id), None)
        if not found:
            raise ValueError('请先创建并选择项目连接')
        return found

    def save_project(self, values):
        p = dict(values)
        p.pop('department_catalog', None)
        p.pop('workflow_columns', None)
        previous = next((old for old in self.w.projects() if old['id'] == p.get('id')), None)
        p.pop('source_cache', None)
        if previous and 'workflow_columns' in previous:
            p['workflow_columns'] = previous['workflow_columns']
        sources = {}
        for kind in ('tests', 'versions'):
            source = normalize_source(p.get('sources', (previous or {}).get('sources', {})).get(kind, {}), kind)
            if source:
                sources[kind] = source
        p['sources'] = sources
        p['source_cache'] = {kind: cached for kind, cached in (previous or {}).get('source_cache', {}).items()
                             if kind in sources and sources[kind] == (previous or {}).get('sources', {}).get(kind)}
        url_changed = bool(p.get('url') and (not previous or p['url'] != previous.get('url')))
        if url_changed:
            url = urllib.parse.urlparse(p['url'])
            pieces = url.path.strip('/').split('/')
            if len(pieces) < 2 or pieces[-2] != 'base':
                raise ValueError('请提供包含 /base/ 的需求表链接；Wiki 链接请先获取真实 Base 链接')
            p['base_token'] = pieces[-1]
            p['table_id'] = urllib.parse.parse_qs(url.query).get('table', [''])[0]
        if not p.get('url') or (not url_changed and previous and any(p.get(k) != previous.get(k) for k in ('base_token', 'table_id'))):
            host = urllib.parse.urlparse((previous or {}).get('url', '')).netloc or 'www.feishu.cn'
            p['url'] = f"https://{host}/base/{p.get('base_token', '')}?table={p.get('table_id', '')}"
        if previous and all(p.get(k) == previous.get(k) for k in ('base_token', 'table_id')) and previous.get('fields', {}).get('department', '部门') == p.get('fields', {}).get('department', '部门'):
            if 'department_catalog' in previous:
                p['department_catalog'] = previous['department_catalog']
        if not p.get('name', '').strip() or not p.get('base_token') or not p.get('table_id'):
            raise ValueError('请填写项目名称及 Base、Table，或粘贴带 table 参数的表链接')
        p['fields'] = dict(DEFAULT_FIELDS, **p.get('fields', {}))
        if any(not p['fields'].get(k) for k in FIELDS):
            raise ValueError('标题、日期、处理人和状态必须配置字段映射')
        p.setdefault('targets', {})
        import datetime
        for target in p['targets'].values():
            if target:
                datetime.date.fromisoformat(target)
        saved = self.w.save_project(p)
        if hasattr(self.remote, 'select'):
            self.remote.select(saved)
        return saved

    def sync_sources(self, project_id):
        project = self.project(project_id)
        cache = dict(project.get('source_cache', {}))
        for kind, source in project.get('sources', {}).items():
            try:
                cache[kind] = refreshed_cache(self.remote, source, kind)
            except Exception as error:
                cache[kind] = dict(cache.get(kind, {}), error=str(error))
        self.w.save_project(dict(project, source_cache=cache))
        return cache

    def sync_departments(self, project_id):
        project = self.project(project_id)
        if project.get('demo'):
            return project.get('department_catalog', dict(field='部门', options=[], error='示例未配置部门选项'))
        catalog = self.remote.departments(project)
        self.w.save_project(dict(project, department_catalog=catalog))
        return catalog

    def sync(self, project_id):
        p = self.project(project_id)
        if p.get('demo'):
            raise ValueError('示例项目使用虚构数据，请新建真实项目连接后读取飞书')
        records = self.remote.records(p)
        by_id = {r['record_id']: r for r in records}
        containers = {parent for r in records for parent in (r.get('parents') or ([r['parent_id']] if r.get('parent_id') else []))}
        for r in records:
            parents = r.get('parents') or ([r['parent_id']] if r.get('parent_id') else [])
            if not parents and r['record_id'] in containers:
                r['module'] = r['title']
            if parents:
                parent_id, visited = parents[0], set()
                while parent_id in by_id and parent_id not in visited:
                    visited.add(parent_id)
                    parent = by_id[parent_id]
                    r['module'] = parent.get('title', '')
                    parent_ids = parent.get('parents') or ([parent['parent_id']] if parent.get('parent_id') else [])
                    if not parent_ids:
                        break
                    parent_id = parent_ids[0]
        self.w.merge_remote(records, p['base_token'] + '/' + p['table_id'], project_id)
        warning = ''
        if hasattr(self.remote, 'departments'):
            try:
                warning = self.sync_departments(project_id).get('error', '')
            except Exception:
                warning = '部门选项更新失败，已保留上次列表；请在人员与部门中重试'
        failures = [c['error'] for c in self.sync_sources(project_id).values() if c.get('error')]
        if failures:
            warning = '；'.join(filter(None, [warning, *failures]))
        return {'count': len(records), 'warning': warning}

    def write(self, project_id, selections):
        p = self.project(project_id)
        if not selections:
            raise ValueError('请勾选要回写的字段')
        scope = p['base_token'] + '/' + p['table_id']
        expected = {}
        for selection in selections:
            task = self.w.get(selection['id'])
            self.w._check(task, selection['revision'])
            if task['project'] != project_id or not task['source'] or task['source']['scope'] != scope:
                raise ValueError('只能回写当前项目已存在的飞书任务，本地分支不能回写')
            fields = selection.get('fields', [])
            if not fields or any(k not in FIELDS for k in fields):
                raise ValueError('请选择允许回写的字段')
            expected[task['id']] = {k: task[k] for k in fields}
        self.sync(project_id)
        for selection in selections:
            task = self.w.get(selection['id'])
            if task['conflicts'] or task['source'].get('missing'):
                raise ValueError('远端有冲突或记录已不可见，请刷新并处理后重新选择回写')
            if any(task[k] != v for k, v in expected[task['id']].items()):
                raise Conflict(task)
        written = 0
        for selection in selections:
            task = self.w.get(selection['id'])
            patch = {k: v for k, v in expected[task['id']].items() if k in task['pending']}
            if not patch:
                continue
            if any(task[k] != v for k, v in patch.items()):
                raise Conflict(task)
            try:
                self.remote.update(p, task['source']['record_id'], patch)
                self.w.acknowledge(task['id'], patch)
                written += 1
            except Exception as error:
                raise ValueError(f'已提交 {written} 条，后续提交未完成；请先读取远端再重试。{error}') from error
        return {'written': written}

    def call(self, method, p):
        if method == 'snapshot':
            return dict(self.w.snapshot(p.get('project')), candidates=self.w.candidates(p.get('project')), auth=self.remote.status(), settings=self.w.settings())
        if method == 'settings_save':
            return self.w.save_settings(p)
        if method == 'departments_sync':
            return self.sync_departments(p['project'])
        if method == 'project_sources_sync':
            return self.sync_sources(p['project'])
        if method == 'open_project_table':
            project = self.project(p['project'])
            kind = p.get('kind')
            url = project.get('url', '') if kind == 'requirements' else project.get('sources', {}).get(kind, {}).get('url', '')
            parsed = urllib.parse.urlparse(url)
            if parsed.scheme != 'https' or not (parsed.hostname or '').endswith(('.feishu.cn', '.larksuite.com')) or parsed.username:
                raise ValueError('未配置有效的飞书源表链接，请在设置中填写完整链接')
            import os
            os.startfile(url)
            return {'opened': True}
        if method in ('contacts_sync', 'contacts_authorize'):
            raise ValueError('通讯录接口已关闭，请在人员与部门中维护本地状态')
        if method == 'create':
            self.project(p['project'])
            return self.w.create(p)
        if method == 'edit':
            return self.w.edit(p['id'], p['patch'], p['revision'])
        if method == 'workflow_arrange':
            from workflow import arrange
            self.project(p['project'])
            return arrange(self.w, p['project'], p['systems'], p['revisions'])
        if method == 'workflow_column_save':
            from workflow import save_column
            return save_column(self.w, p['project'], p['name'], p.get('priority', ''), p.get('id'), p.get('previous_name'))
        if method == 'workflow_column_archive':
            from workflow import archive_column
            return archive_column(self.w, p['project'], p['name'])
        if method == 'dependencies':
            return self.w.dependencies(p['id'], p['upstream'], p['revision'])
        if method == 'branch':
            return self.w.branch(p['id'], p)
        if method == 'link_many':
            self.project(p['project'])
            return self.w.link_many(p['project'], p['selections'])
        if method == 'link':
            return self.w.link(p['id'], p['revision'])
        if method == 'resolve':
            return self.w.resolve(p['id'], p['field'], p['choice'], p['revision'])
        if method == 'project_save':
            return self.save_project(p)
        if method == 'sync':
            return self.sync(p['project'])
        if method == 'write':
            return self.write(p['project'], p['selections'])
        if method == 'auth_configure':
            result = self.remote.configure(**p)
            project = next((p for p in self.w.projects() if not p.get('demo')), None)
            if project and hasattr(self.remote, 'select'):
                result = self.remote.select(project)
            return result
        if method == 'auth_begin':
            project = next((p for p in self.w.projects() if not p.get('demo')), None)
            if project and hasattr(self.remote, 'select'):
                self.remote.select(project)
            return self.remote.begin_auth()
        if method == 'auth_status':
            return self.remote.status()
        if method == 'auth_finish':
            return self.remote.finish_auth(**p)
        if method == 'demo':
            return self.demo()
        raise ValueError('未知操作')

    def demo(self):
        catalog = dict(field='部门', error='', options=[dict(id=name, name=name, color=color) for name, color in [('策划', 14), ('美术', 19), ('UI', 13), ('开发', 17), ('动效', 16)]])
        project = self.w.save_project(dict(name='示例 · 新系统开发', base_token='demo', table_id='demo', fields=DEFAULT_FIELDS, targets={'v1.0': '2026-11-20'}, demo=True, department_catalog=catalog))
        def task(title, state, owner, start, end, **extra):
            return self.w.create(dict(project=project['id'], title=title, state=state, owners=[{'id': owner, 'name': owner}], start=start, end=end, module='活动系统', version='v1.0', **extra))
        doc = task('需求文档 / 原型图 / 流程图', 'done', '策划', '2026-11-05', '2026-11-06')
        dev = task('功能开发', 'active', '开发', '2026-11-06', '2026-11-13')
        ui = task('UI绘制', 'active', 'UI', '2026-11-06', '2026-11-11')
        cut = task('切摆', 'active', '切摆', '2026-11-06', '2026-11-10', prototypes=True)
        motion = task('预制件动效制作', 'todo', '动效', '2026-11-10', '2026-11-14')
        integrate = task('开发接入动效', 'todo', '开发', '2026-11-14', '2026-11-18')
        for child in (dev, ui, cut):
            self.w.dependencies(child['id'], [doc['id']], child['revision'])
        self.w.dependencies(motion['id'], [cut['id']], motion['revision'])
        self.w.dependencies(integrate['id'], [dev['id'], motion['id']], integrate['revision'])
        return {'project': project['id']}


def main():
    sys.stdin.reconfigure(encoding='utf-8')
    sys.stdout.reconfigure(encoding='utf-8')
    service = Service()
    for line in sys.stdin:
        try:
            request = json.loads(line)
            result = {'result': service.call(request['method'], request.get('params') or {})}
        except Conflict as error:
            result = {'error': json.dumps({'kind': 'conflict', 'message': str(error), 'current': error.current}, ensure_ascii=False)}
        except Exception as error:
            result = {'error': str(error)}
        print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
