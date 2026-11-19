import copy
import json
import uuid
import time


def module_name(task):
    return task.get('module') or ''


def archive_column(workspace, project_id, name):
    with workspace.db:
        workspace.db.execute('BEGIN IMMEDIATE')
        row = workspace.db.execute('SELECT body FROM projects WHERE id=?', (project_id,)).fetchone()
        if not row:
            raise ValueError('项目不存在')
        tasks = [t for t in workspace._all(project_id) if module_name(t) == name and not t.get('is_requirement')]
        if any(t['state'] not in ('done', 'closed') for t in tasks):
            raise ValueError('所有任务完成后才可归档，请刷新后重试')
        project = json.loads(row[0])
        columns = project.setdefault('workflow_columns', [])
        column = next((c for c in columns if c['name'] == name), None)
        if column is None:
            if not tasks or not name:
                raise ValueError('需求不存在')
            column = dict(id=str(uuid.uuid4()), name=name, priority='')
            columns.append(column)
        column['archived_tasks'] = sorted(t['id'] for t in tasks)
        workspace.db.execute('UPDATE projects SET body=? WHERE id=?', (json.dumps(project, ensure_ascii=False), project_id))
    return column


def arrange(workspace, project_id, systems, revisions, include_snapshot=True, version=None):
    if version is not None and not isinstance(version, str):
        raise ValueError('版本筛选必须是原始版本名称')
    if not isinstance(systems, list) or not systems:
        raise ValueError('请选择需要编排的需求列')
    names = [s.get('module') for s in systems]
    if any(not isinstance(n, str) for n in names) or len(names) != len(set(names)):
        raise ValueError('需求列不能重复')
    with workspace.db:
        workspace.db.execute('BEGIN IMMEDIATE')
        tasks = {t['id']: workspace._raw(t['id']) for t in workspace._all(project_id) if not t.get('is_requirement')}
        assignments = {}
        for system in systems:
            stages = system.get('stages')
            if not isinstance(stages, list):
                raise ValueError('无效阶段')
            branches = system.get('branches', {})
            if not isinstance(branches, dict) or any(not isinstance(parent, str) or not isinstance(children, list) or not children for parent, children in branches.items()):
                raise ValueError('无效分支')
            def assign(task_id, rank, parents, branch_parent=None):
                if not isinstance(task_id, str) or task_id not in tasks or task_id in assignments:
                    raise ValueError('任务不存在、跨项目、重复或分支形成循环')
                if version is not None and tasks[task_id].get('version', '') != version:
                    raise ValueError('编排只能包含当前版本的任务，请刷新后重试')
                if not system['module'] and branch_parent is None:
                    parents = [parent for parent in parents if parent in tasks and tasks[parent].get('version', '') == tasks[task_id].get('version', '')]
                assignments[task_id] = (system['module'], rank, parents, branch_parent)
                for child in branches.get(task_id, []):
                    assign(child, rank, [task_id], task_id)
            for rank, stage in enumerate(stages):
                if not isinstance(stage, list) or not stage:
                    raise ValueError('阶段不能为空')
                for task_id in stage:
                    assign(task_id, rank, stages[rank - 1] if rank else [])
            if any(parent not in assignments or assignments[parent][0] != system['module'] for parent in branches):
                raise ValueError('分支上游不存在或分支形成循环')
        required = {t['id'] for t in tasks.values() if module_name(t) in names and (version is None or t.get('version', '') == version)}
        if set(assignments) != required:
            raise ValueError('必须包含来源及目标需求列的全部任务，请刷新后重试')
        for task_id in assignments:
            workspace._check(tasks[task_id], revisions.get(task_id))
        for task_id, (name, rank, parents, branch_parent) in assignments.items():
            task = tasks[task_id]
            task.update(module=name, module_local=True, workflow_stage=rank, workflow_parent=branch_parent,
                        upstream=list(dict.fromkeys([i for i in task['upstream'] if i not in assignments] + parents)))
        visited, active = set(), set()
        def visit(task_id):
            if task_id in active:
                raise ValueError('依赖形成循环，请调整')
            if task_id in visited or task_id not in tasks:
                return
            active.add(task_id)
            for parent in tasks[task_id]['upstream']:
                visit(parent)
            active.remove(task_id)
            visited.add(task_id)
        for task_id in tasks:
            visit(task_id)
        for task_id in assignments:
            workspace._put(tasks[task_id])
    return workspace.snapshot(project_id) if include_snapshot else {'updated': list(assignments)}


def save_column(workspace, project_id, name, priority='', column_id=None, previous_name=None):
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 100:
        raise ValueError('需求列名称须为 1–100 字')
    name = name.strip()
    if name == '未归类':
        raise ValueError('未归类为保留名称')
    if priority not in ('', 'high', 'medium', 'low'):
        raise ValueError('无效优先级')
    with workspace.db:
        workspace.db.execute('BEGIN IMMEDIATE')
        row = workspace.db.execute('SELECT body FROM projects WHERE id=?', (project_id,)).fetchone()
        if not row:
            raise ValueError('项目不存在')
        project = json.loads(row[0])
        columns = copy.deepcopy(project.get('workflow_columns', []))
        current = next((c for c in columns if c['id'] == column_id), None)
        if column_id and not current:
            raise ValueError('需求列已变化，请刷新')
        old_name = current['name'] if current else previous_name
        existing_names = {module_name(t) for t in workspace._all(project_id)} | {c['name'] for c in columns}
        if name != old_name and name in existing_names:
            raise ValueError('已有同名需求列')
        if previous_name is not None and not current and (previous_name not in existing_names or any(c['name'] == previous_name for c in columns)):
            raise ValueError('需求列已变化，请刷新')
        if not current:
            current = dict(id=str(uuid.uuid4()), name=name, priority=priority, created_at=time.time_ns())
            columns.append(current)
        else:
            current.update(name=name, priority=priority)
        if old_name is not None and old_name != name:
            for raw in workspace._all(project_id):
                if module_name(raw) == old_name:
                    task = workspace._raw(raw['id'])
                    task.update(module=name, module_local=True)
                    workspace._put(task)
        project['workflow_columns'] = columns
        workspace.db.execute('UPDATE projects SET body=? WHERE id=?', (json.dumps(project, ensure_ascii=False), project_id))
    return current
