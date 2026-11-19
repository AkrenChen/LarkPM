import copy
import json
import uuid

from workspace import FIELDS


def scope(project):
    return project['base_token'] + '/' + project['table_id']


def parent_records(workspace, project, tasks=None):
    result = {}
    for task in workspace._all(project['id']) if tasks is None else tasks:
        source = task.get('source')
        if task.get('is_requirement') and source and source['scope'] == scope(project) and not source.get('missing'):
            name = task['module'] if task.get('module_local') else task['title']
            result.setdefault(name, []).append(source['record_id'])
    return result


def candidates(workspace, project, include_ignored=False):
    tasks = workspace._all(project['id'])
    parents = parent_records(workspace, project, tasks)
    views = {task['id']: task for task in workspace.task_views(project['id'], tasks)}
    result = []
    archived = set()
    for column in project.get('workflow_columns', []):
        entries = [task for task in tasks if not task.get('is_requirement') and task['module'] == column['name']]
        saved = column.get('archived_tasks')
        if (isinstance(saved, list) and set(saved) == {t['id'] for t in entries} and all(t['state'] in ('done', 'closed') for t in entries)) or (entries and all(t.get('acceptance') == '验收通过' and not (t.get('source') or {}).get('missing') for t in entries)):
            archived.add(column['name'])
        elif column['name'] not in parents:
            result.append(dict(kind='requirement', id=column['id'], title=column['name'], module=column['name'], revision=0, created_at=column.get('created_at', project.get('workflow_columns', []).index(column)),
                               values=dict(title=column['name'], start='', end='', owners=[], state='todo', priority='', version='', departments=[])))
    for index, task in enumerate(tasks):
        if not task.get('source') and not task.get('is_requirement') and task['module'] not in archived:
            current = views[task['id']]
            result.append(dict(kind='task', id=task['id'], title=task['title'], module=task['module'], revision=task['revision'], created_at=task.get('created_at', index),
                               values={key: current[key] for key in (*FIELDS, 'version', 'departments')}))
    for item in result:
        item['parents'] = [dict(id=record_id, title=task['title'], version=task.get('version', ''), owners=task['owners'], start=task['start'], end=task['end'])
                           for record_id in parents.get(item['module'], []) for task in tasks if (task.get('source') or {}).get('record_id') == record_id and (task.get('source') or {}).get('scope') == scope(project)] if item['kind'] == 'task' else []
        job = workspace.db.execute('SELECT payload FROM publication_jobs WHERE project=? AND scope=? AND kind=? AND entity_id=?',
                                   (project['id'], scope(project), item['kind'], item['id'])).fetchone()
        item['retry'] = bool(job)
        if job:
            item['values'] = json.loads(job[0])
    ignored = {(kind, entity_id) for kind, entity_id in workspace.db.execute('SELECT kind,entity_id FROM publication_ignored WHERE project=? AND scope=?', (project['id'], scope(project)))}
    for item in result:
        item['ignored'] = (item['kind'], item['id']) in ignored
    return sorted([item for item in result if include_ignored or not item['ignored']], key=lambda item: item['created_at'], reverse=True)


def ignore(workspace, project, kind, entity_id, ignored):
    if not isinstance(ignored, bool) or not any(item['kind'] == kind and item['id'] == entity_id for item in candidates(workspace, project, True)):
        raise ValueError('本地新增项已变化，请刷新后重试')
    with workspace.db:
        key = (project['id'], scope(project), kind, entity_id)
        if ignored:
            workspace.db.execute('INSERT OR IGNORE INTO publication_ignored VALUES (?,?,?,?)', key)
        else:
            workspace.db.execute('DELETE FROM publication_ignored WHERE project=? AND scope=? AND kind=? AND entity_id=?', key)
    return dict(ignored=ignored)


def publish(service, project_id, selections):
    workspace, remote = service.w, service.remote
    project = service.project(project_id)
    if project.get('archived') or project.get('demo'):
        raise ValueError('归档或示例项目不能创建飞书记录')
    if not isinstance(selections, list) or not selections:
        raise ValueError('请选择要创建到飞书的需求或任务')
    service.sync(project_id)
    project = service.project(project_id)
    available = {(item['kind'], item['id']): item for item in candidates(workspace, project)}
    chosen, seen = [], set()
    for selection in selections:
        key = (selection.get('kind'), selection.get('id'))
        if key in seen or key not in available:
            raise ValueError('新增项已变化、已提交或不属于当前项目，请刷新后重试')
        seen.add(key)
        item = available[key]
        item = copy.deepcopy(item)
        item['parent_choice'] = selection.get('parent_id')
        if item['kind'] == 'task':
            workspace._check(workspace.get(item['id']), selection.get('revision'))
        elif selection.get('name') != item['title']:
            raise ValueError('需求名称已变化，请刷新后重试')
        chosen.append(item)
    parents = parent_records(workspace, project)
    chosen.sort(key=lambda item: item['kind'] != 'requirement')
    selected_parents = {item['module'] for item in chosen if item['kind'] == 'requirement'}
    for item in chosen:
        if not item['retry'] and item['kind'] == 'task' and item['module']:
            choices = parents.get(item['module'], [])
            choice = item['parent_choice']
            if choice is not None and (not isinstance(choice, str) or (choice and choice not in choices)):
                raise ValueError('所选父需求已变化或不属于当前需求，请重新选择')
            if len(choices) > 1 and choice is None:
                raise ValueError('飞书存在同名父需求，请选择具体父需求或仅本地归类')
            parent = choice if choice is not None else next(iter(choices), None)
            if choice == '':
                continue
            if parent or item['module'] in selected_parents:
                item['values']['parent_id'] = parent or '__pending_parent__'
    remote.prepare_create(project, [item['values'] for item in chosen])
    created = 0
    for item in chosen:
        key = (project_id, scope(project), item['kind'], item['id'])
        try:
            job = workspace.db.execute('SELECT token,payload,response FROM publication_jobs WHERE project=? AND scope=? AND kind=? AND entity_id=?', key).fetchone()
            if job:
                token, payload, response = job
                values = json.loads(payload)
            else:
                token, response = str(uuid.uuid4()), None
                values = copy.deepcopy(item['values'])
                if values.get('parent_id') == '__pending_parent__':
                    values['parent_id'] = parents[item['module']][0]
                with workspace.db:
                    workspace.db.execute('INSERT INTO publication_jobs VALUES (?,?,?,?,?,?,?,NULL)', (*key, token, json.dumps(values, ensure_ascii=False), item['module']))
            record = json.loads(response) if response else remote.create(project, values, token)
            rid = record.get('record_id')
            if not rid:
                raise ValueError('飞书响应缺少记录ID，请重试创建以核实结果')
            baseline = {field: copy.deepcopy(values.get(field, '' if field == 'priority' else None)) for field in FIELDS}
            with workspace.db:
                workspace.db.execute('UPDATE publication_jobs SET response=? WHERE project=? AND scope=? AND kind=? AND entity_id=?',
                                     (json.dumps(record, ensure_ascii=False), *key))
                if item['kind'] == 'requirement':
                    existing = next((t for t in workspace._all(project_id) if t.get('source') and t['source']['scope'] == scope(project) and t['source']['record_id'] == rid), None)
                    task = existing or dict(id=str(uuid.uuid4()), project=project_id, **baseline, module=item['module'], version='', linked=False, upstream=[], branch_of=None, prototypes=False, conflicts={}, acceptance='', revision=0)
                    task.update(is_requirement=True, published_requirement=True, module_local=True)
                    parents[item['module']] = [rid]
                else:
                    task = workspace._raw(item['id'])
                    mirrors = [t for t in workspace._all(project_id) if t['id'] != task['id'] and t.get('source') and t['source']['scope'] == scope(project) and t['source']['record_id'] == rid]
                    for mirror in mirrors:
                        if workspace.pending(mirror) or mirror.get('linked') or workspace.db.execute('SELECT id FROM notes WHERE id=?', (mirror['id'],)).fetchone():
                            raise ValueError('已读取到创建结果且该副本有本地修改，请先处理重复本地副本后重试')
                        for other in workspace._all(project_id):
                            if mirror['id'] in other.get('upstream', []):
                                other['upstream'] = [task['id'] if value == mirror['id'] else value for value in other['upstream']]
                                workspace._put(other)
                        workspace.db.execute('DELETE FROM tasks WHERE id=?', (mirror['id'],))
                    task.update(module_local=True, version_local=True)
                task['source'] = dict(record_id=rid, scope=scope(project), base=baseline, missing=False)
                workspace._put(task)
            created += 1
        except Exception as error:
            raise ValueError(f'已创建 {created} 条，后续创建未完成；已成功内容已保留，重试沿用上次提交内容，不会主动新建重复记录。{error}') from error
    return dict(created=created)
