import { matchesStatus, type NodeShortcuts } from '../nodeShortcuts';
import { useCallback, useEffect, useRef, useState, type CSSProperties, type DragEvent, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import type { DepartmentOption, Project, Run, Task } from '../types';
import { departmentAccent, departmentStyle } from '../departmentColors';
import { People, Status } from '../App';
import { DepartmentTag } from './DepartmentSelect';
import { ColumnEditor, StatusMenu } from './WorkflowMenus';
import { archivedRequirementNames, moveWorkflow, priorityNames, workflowLayout, workflowIds, compareRequirementNames, type WorkflowSystem } from '../workflowLayout';
import Icon from './Icon';
import type { BoardMode } from '../preferences';
import OpenRequirements from './OpenRequirements';
import useMasonry from './useMasonry';
import { StableRequirementOrder } from '../feedLayout';
import { orderParallelTasks } from '../taskPriority';
import ArchivedRequirements from './ArchivedRequirements';
import './WorkflowBoard.css';

function deadline(task: Task) {
  if (!task.end) return { text: '未排期', overdue: false };
  const now = new Date();
  const [year, month, day] = task.end.slice(0, 10).split('-').map(Number);
  const days = Math.round((Date.UTC(year, month - 1, day) - Date.UTC(now.getFullYear(), now.getMonth(), now.getDate())) / 86400000);
  const overdue = days < 0 && task.state !== 'done' && task.state !== 'closed';
  const date = task.end.slice(0, 10).replaceAll('-', '/');
  return { text: overdue ? `${date}（已延期 ${-days}d）` : `${date}（${days === 0 ? '今天' : `${days}d`}）`, overdue };
}

export default function WorkflowBoard({ tasks, allTasks, departmentOptions, onSelect, project, run, busy, controls, onCreate, version, shortcuts, displayMode, filterKey = '' }: {
  tasks: Task[]; allTasks: Task[]; departmentOptions: DepartmentOption[]; onSelect: (id: string) => void; project: Project; run: Run; busy: boolean; controls: ReactNode; onCreate: (module: string, upstream?: string[]) => void;
  version: string; shortcuts: NodeShortcuts; displayMode: BoardMode; filterKey?: string;
}) {
  const [showOpen, setShowOpen] = useState(false);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const closeOpen = useCallback(() => setShowOpen(false), []);
  const [showArchive, setShowArchive] = useState(false);
  const [arranging, setArranging] = useState(false), [selection, setSelection] = useState<string[]>([]);
  const [dragging, setDragging] = useState<string[]>([]), [hover, setHover] = useState('');
  const [editor, setEditor] = useState<{ name?: string } | null>(null);
  const [context, setContext] = useState<{ name: string; x: number; y: number } | null>(null);
  const [taskContext, setTaskContext] = useState<{ id: string; x: number; y: number } | null>(null);
  const [status, setStatus] = useState<{ id: string; x: number; y: number } | null>(null);
  const mode = useRef(false), dragIds = useRef<string[]>([]), inFlight = useRef(false), focusId = useRef('');
  const board = useRef<HTMLDivElement>(null);
  const stableOrder = useRef(new StableRequirementOrder());
  const columns = project.workflow_columns || [];
  const allSystems = workflowLayout(allTasks, columns);
  const systems = version ? workflowLayout(allTasks.filter(task => task.version === version), columns) : allSystems;
  const byId = new Map(allTasks.map(t => [t.id, t]));
  const inVersion = (task: Task) => !version || task.version === version;
  const visible = new Set(tasks.filter(t => inVersion(t) && !(['done', 'closed'].includes(t.state) && t.acceptance === '验收通过')).map(t => t.id));
  const completed = systems.filter(system => {
    const ids = workflowIds(system).filter(id => inVersion(byId.get(id)!));
    return ids.length > 0 && ids.every(id => ['done', 'closed'].includes(byId.get(id)!.state));
  });
  const completedNames = new Set(completed.map(system => system.module));
  const archivableNames = new Set(systems.filter(system => system.module && workflowIds(system).every(id => ['done', 'closed'].includes(byId.get(id)!.state))).map(system => system.module));
  const archivedNames = archivedRequirementNames(allTasks, columns);
  const archived = allSystems.filter(system => archivedNames.has(system.module));
  const compareNames = compareRequirementNames(tasks.filter(inVersion), columns);
  const desiredSystems = systems.filter(system => !archivedNames.has(system.module) && (completedNames.has(system.module) || workflowIds(system).some(id => visible.has(id)) || (!version && !system.stages.length))).sort((a, b) => Number(!b.module) - Number(!a.module) || Number(completedNames.has(b.module)) - Number(completedNames.has(a.module)) || compareNames(a.module, b.module));
  const order = stableOrder.current.update(desiredSystems.map(system => system.module), allTasks, columns, JSON.stringify([project.id, version, filterKey, displayMode]));
  const systemByName = new Map(desiredSystems.map(system => [system.module, system]));
  const boardSystems = order.names.map(name => systemByName.get(name)!);
  useMasonry(board, displayMode === 'feed', JSON.stringify(order.names), String(order.epoch));
  const closeArchive = useCallback(() => setShowArchive(false), []);
  const closeStatus = useCallback(() => setStatus(null), []), closeEditor = useCallback(() => setEditor(null), []);
  const cancelDrag = useCallback(() => { dragIds.current = []; setDragging([]); setHover(''); }, []);
  useEffect(() => {
    const endMode = () => { mode.current = false; setArranging(false); setSelection([]); cancelDrag(); };
    const keydown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { cancelDrag(); setContext(null); setTaskContext(null); return; }
      if ((e.target as HTMLElement)?.closest('input,textarea,select,[role="combobox"],[role="listbox"],[contenteditable="true"]') || document.querySelector('[aria-modal="true"]') || status) return;
      if (e.key === shortcuts.arrange && !e.ctrlKey && !e.metaKey) { e.preventDefault(); mode.current = true; setArranging(true); }
      if (matchesStatus(e, shortcuts.status) && focusId.current) {
        const el = board.current?.querySelector<HTMLElement>(`[data-task-id="${focusId.current}"]`);
        if (el) { e.preventDefault(); const rect = el.getBoundingClientRect(); setStatus({ id: focusId.current, x: rect.right - 190, y: rect.top + 25 }); }
      }
    };
    const keyup = (e: KeyboardEvent) => { if (e.key === shortcuts.arrange) { e.preventDefault(); endMode(); } else if (e.key === 'Control' && !mode.current) setSelection([]); };
    window.addEventListener('keydown', keydown); window.addEventListener('keyup', keyup); window.addEventListener('blur', endMode);
    return () => { window.removeEventListener('keydown', keydown); window.removeEventListener('keyup', keyup); window.removeEventListener('blur', endMode); };
  }, [cancelDrag, status, shortcuts]);
  useEffect(() => {
    if (!context && !taskContext) return;
    const dismiss = () => { setContext(null); setTaskContext(null); };
    window.addEventListener('click', dismiss); window.addEventListener('scroll', dismiss, true); window.addEventListener('resize', dismiss);
    return () => { window.removeEventListener('click', dismiss); window.removeEventListener('scroll', dismiss, true); window.removeEventListener('resize', dismiss); };
  }, [context, taskContext]);

  function allowDrop(e: DragEvent, key: string) {
    if (!mode.current || !dragIds.current.length || busy || inFlight.current) return;
    e.preventDefault(); e.stopPropagation(); e.dataTransfer.dropEffect = 'move'; setHover(key);
  }
  async function drop(e: DragEvent, module: string, index: number, parallel: boolean, parent?: string) {
    e.preventDefault(); e.stopPropagation();
    if (!mode.current || !dragIds.current.length || busy || inFlight.current) { cancelDrag(); return; }
    const next = moveWorkflow(systems, dragIds.current, { module, index, parallel, parent });
    cancelDrag();
    if (!next) return;
    inFlight.current = true;
    try {
      await run('workflow_arrange', { project: project.id, version: version || undefined, systems: next, revisions: Object.fromEntries(next.flatMap(workflowIds).map(id => [id, byId.get(id)!.revision])) }, '编排已保存');
    } finally { inFlight.current = false; }
  }
  function gap(module: string, index: number) {
    const key = `${module}:gap:${index}`;
    return <div className={`workflow-drop-gap ${hover === key ? 'is-over' : ''}`} key={key} data-drop-gap={index} aria-label={`${module || '未归类'}阶段间隙${index + 1}`} onDragOver={e => allowDrop(e, key)} onDrop={e => void drop(e, module, index, false)}>{arranging && (dragging.length ? '放到这里 · 串行阶段' : '串行')}</div>;
  }
  function hasVisibleTree(id: string, system: WorkflowSystem): boolean {
    return visible.has(id) || (system.branches?.[id] || []).some(child => hasVisibleTree(child, system));
  }
  function renderTask(task: Task, system: WorkflowSystem, index: number, depth = 0): ReactNode {
    const module = system.module;
    const expanded = task.state === 'active', due = deadline(task);
    const department = task.departments[0] || '', color = departmentOptions.find(o => o.name === department)?.color;
    const tone = departmentStyle(color, department), key = `${module}:parallel:${index}`;
    const card = <article data-task-id={task.id} className={`flow-node ${expanded ? 'is-active' : 'is-compact'} state-${task.state}${selection.includes(task.id) ? ' is-selected' : ''}${dragging.includes(task.id) ? ' is-dragging' : ''}${hover === key ? ' is-drop-target' : ''}`} key={task.id}
      style={{ '--department-border': departmentAccent(color, department), '--department-heading': tone.backgroundColor, '--department-text': tone.color } as CSSProperties}
      draggable={arranging && !busy} onFocus={() => { focusId.current = task.id; }}
      onContextMenu={e => { e.preventDefault(); e.stopPropagation(); setContext(null); setStatus(null); setTaskContext({ id: task.id, x: Math.max(8, Math.min(e.clientX, window.innerWidth - 200)), y: Math.max(8, Math.min(e.clientY, window.innerHeight - 64)) }); }}
      onDragStart={e => {
        if (!mode.current || busy) { e.preventDefault(); return; }
        const ids = selection.includes(task.id) ? selection.filter(id => visible.has(id)) : [task.id];
        dragIds.current = ids; setDragging(ids); setSelection(ids); e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/plain', ids.join(','));
      }} onDragEnd={cancelDrag} onDragOver={e => allowDrop(e, key)} onDrop={e => void drop(e, module, index, true)}>
      <span className="flow-node-dot" aria-hidden="true">{task.state === 'done' && <Icon name="check" size={10}/>}</span>
      <div className="flow-node-card task-card"><div className="flow-node-heading">
        <button className="flow-node-title flow-edit" aria-label={`查看${task.title}`} onClick={e => {
          focusId.current = task.id;
          if (e.ctrlKey || e.metaKey) setSelection(old => old.includes(task.id) ? old.filter(id => id !== task.id) : [...old, task.id]);
          else if (mode.current) setSelection([task.id]); else onSelect(task.id);
        }}>{!expanded && task.departments.length > 0 && <span className="flow-departments">{task.departments.map(name => <DepartmentTag key={name} name={name} options={departmentOptions}/>)}</span>}<h3 title={task.title}>{task.title}</h3></button>
        <button className="flow-status-button" disabled={busy || arranging} aria-label={`切换状态：${task.title}`} onClick={e => { const rect = e.currentTarget.getBoundingClientRect(); setStatus({ id: task.id, x: rect.left, y: rect.bottom + 4 }); }}><Status task={task}/></button>
      </div>
        {expanded && <div className="flow-node-detail"><span className="flow-node-assignee">{task.departments.length > 0 && <span className="flow-departments">{task.departments.map(name => <DepartmentTag key={name} name={name} options={departmentOptions}/>)}</span>}<People task={task}/></span><span className={`flow-deadline${due.overdue ? ' is-overdue' : ''}`}>{due.text}</span></div>}
        {expanded && task.blocked_by.length > 0 && <span className="flow-upstream-warning">上游未完成 · 保留当前进度</span>}
        {Object.keys(task.conflicts).length > 0 && <span className="flow-conflict">存在同步冲突</span>}
        {task.acceptance === '验收通过' && <span className="flow-accepted">✓ 验收通过</span>}
      </div>
    </article>;

    const children = orderParallelTasks((system.branches?.[task.id] || []).filter(id => hasVisibleTree(id, system)).map(id => byId.get(id)!), project.priority_catalog?.options).map(task => task.id);
    return <div className={`flow-task-tree${depth ? ' is-branch' : ''}`} key={task.id}>
      <div className="flow-task-anchor">
      {visible.has(task.id) && card}
      {arranging && visible.has(task.id) && <div className={`workflow-branch-target ${hover === `branch:${task.id}` ? 'is-over' : ''}`} data-branch-target={task.id} onDragOver={event => allowDrop(event, `branch:${task.id}`)} onDrop={event => void drop(event, module, index, false, task.id)}>仅接在此任务后</div>}
      </div>
      {children.length > 0 && <div className="flow-branch-list">{children.map(id => renderTask(byId.get(id)!, system, index, depth + 1))}</div>}
    </div>;
  }
  return <>
    <div className="workflow-controls">{controls}<div className="workflow-tools"><button className="button small" onClick={() => setShowOpen(true)}>未结需求</button><button className="button small" onClick={() => setShowArchive(true)}>已结需求{archived.length > 0 ? ` · ${archived.length}` : ''}</button><button className="button small" disabled={busy} onClick={() => setEditor({})}><Icon name="plus" size={14}/>新建需求列</button></div>{arranging && <div className="workflow-arrange-hint">编排中 · 完成且验收通过的节点已隐藏；空隙串行，阶段内并行，“仅接在此任务后”添加分支；松开 {shortcuts.arrange} 退出，Esc 取消当前拖动</div>}</div>
    <div ref={board} className={`workflow-board${arranging ? ' is-arranging' : ''}${dragging.length ? ' is-dragging-tasks' : ''}${displayMode === 'feed' ? ' is-feed' : ''}`}>
      <div className="workflow-columns">
      {boardSystems.map(system => {
        const module = system.module, all = workflowIds(system).map(id => byId.get(id)!).filter(inVersion);
        const column = columns.find(c => c.name === module);
        const versions = Array.from(new Set(all.map(t => t.version).filter(Boolean)));
        return <section className="workflow-module" data-module={module} key={module} aria-label={`${module || '未归类'}需求流程`}>
          <header className="workflow-header" onContextMenu={e => { e.preventDefault(); setContext({ name: module, x: Math.min(e.clientX, window.innerWidth - 180), y: Math.min(e.clientY, window.innerHeight - 160) }); }}>
            <div className="workflow-module-title"><button className="workflow-title-toggle" aria-expanded={!collapsed.has(module)} aria-label={`折叠需求：${module || '未归类'}`} onClick={() => setCollapsed(previous => { const next = new Set(previous); if (next.has(module)) next.delete(module); else next.add(module); return next; })}><span aria-hidden="true">{collapsed.has(module) ? '▸' : '▾'}</span><h2>{module || '未归类'}</h2></button></div>
            <div className="workflow-column-meta">{column?.priority && <span className={`column-priority priority-${column.priority}`}>{priorityNames[column.priority]}</span>}{completedNames.has(module) && <span className="workflow-awaiting">待验收</span>}{versions.length > 0 && <span className="workflow-versions" title={versions.join('、')}>{versions.join(' / ')}</span>}{module && <button className="column-more" aria-label={`编辑需求列${module}`} disabled={busy} onClick={() => setEditor({ name: module })}>···</button>}</div>
          </header>
          <div className="workflow-timeline" hidden={collapsed.has(module)}>
            
            {system.stages.map((ids, index) => {
              const entries = orderParallelTasks(ids.filter(id => hasVisibleTree(id, system)).map(id => byId.get(id)!), project.priority_catalog?.options);
              if (!entries.length) return null;
              return <div className="flow-stage-wrapper" key={index}>
                {arranging && gap(module, index)}
                {entries.length > 0 && <section className={`flow-stage${ids.length > 1 ? ' is-parallel' : ''}`} aria-label={`阶段 ${index + 1}`} onDragOver={e => allowDrop(e, `${module}:parallel:${index}`)} onDrop={e => void drop(e, module, index, true)}>
                  {entries.length > 1 && <div className="flow-stage-label"><span className="flow-parallel"><Icon name="branch" size={11}/>并行 · {entries.length} 个节点</span></div>}
                  <div className="flow-stage-nodes">{entries.map(task => renderTask(task, system, index))}</div>
                  {arranging && <div className={`workflow-parallel-target ${hover === `${module}:parallel:${index}` ? 'is-over' : ''}`} data-parallel-target={index}>放到这里 · 加入此阶段并行</div>}
                </section>}

              </div>;
            })}
            {arranging && gap(module, system.stages.length)}
            {!all.length && <div className="workflow-empty-column" onDragOver={e => allowDrop(e, `${module}:gap:0`)} onDrop={e => void drop(e, module, 0, false)}>{arranging ? '拖入任务' : '按住编排键，将任务拖入此列'}</div>}
            {all.length > 0 && !completedNames.has(module) && !all.some(t => visible.has(t.id)) && !arranging && <div className="workflow-empty-column">当前筛选下无任务</div>}
          </div>
        </section>;
      })}
      </div>
      {!boardSystems.length && <div className="empty"><Icon name="box" size={30}/><p>{archived.length ? '当前没有未完成需求，历史记录可在已结需求中查看' : '没有符合筛选条件的需求，可新建需求列或本地任务'}</p></div>}
    </div>
    {showOpen && <OpenRequirements systems={allSystems.filter(system => !archivedNames.has(system.module)).sort((a,b) => Number(!b.module) - Number(!a.module))} tasks={allTasks} onClose={closeOpen} onSelect={id => { setShowOpen(false); onSelect(id); }}/>}
    {showArchive && <ArchivedRequirements systems={archived} tasks={allTasks} onClose={closeArchive} onCreate={module => { setShowArchive(false); onCreate(module); }} onSelect={id => { setShowArchive(false); onSelect(id); }}/>}
    {context && <div className="workflow-menu" role="menu" style={{ left: context.x, top: context.y }}><button role="menuitem" disabled={busy} onClick={() => { onCreate(context.name, allTasks.filter(task => (task.module || "") === context.name && inVersion(task) && task.state === "active").map(task => task.id)); setContext(null); }}>添加任务</button><button role="menuitem" disabled={busy} onClick={() => { setEditor({ name: context.name }); setContext(null); }}>编辑名称和优先级</button>{archivableNames.has(context.name) && <button role="menuitem" disabled={busy} onClick={() => { void run('workflow_column_archive', { project: project.id, name: context.name }, '需求已归档'); setContext(null); }}>归档需求</button>}</div>}
    {taskContext && byId.has(taskContext.id) && createPortal(<div className="workflow-menu" role="menu" aria-label="任务菜单" style={{ left: taskContext.x, top: taskContext.y }}><button role="menuitem" disabled={busy || byId.get(taskContext.id)!.acceptance === '验收通过' || !!byId.get(taskContext.id)!.source?.missing} onClick={() => { const task = byId.get(taskContext.id)!; setTaskContext(null); void run('task_accept', { id: task.id, revision: task.revision }, task.source ? '验收通过，已写回飞书' : '已标记验收通过'); }}>{byId.get(taskContext.id)!.acceptance === '验收通过' ? '已验收通过' : '标记验收通过'}</button></div>, document.body)}
    {editor && <ColumnEditor project={project.id} column={columns.find(c => c.name === editor.name)} previousName={columns.some(c => c.name === editor.name) ? undefined : editor.name} run={run} busy={busy} close={closeEditor}/>}
    {status && byId.has(status.id) && <StatusMenu task={byId.get(status.id)!} x={status.x} y={status.y} run={run} busy={busy} close={closeStatus}/>}
  </>;
}
