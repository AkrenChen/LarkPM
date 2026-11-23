import { readNodeShortcuts, saveNodeShortcuts, shortcutText, type NodeShortcuts } from './nodeShortcuts';
import { availableRequirementNames } from './workflowLayout';
import { readGanttScale, saveGanttScale, type GanttScale, readBoardMode, saveBoardMode, type BoardMode } from './preferences';
import Personal from './components/Personal';
import ListSelect from './components/ListSelect';
import { useCallback, useEffect, useRef, useState } from 'react';
import { dateLabel, errorText, rpc } from './api';
import { SnapshotRequests } from './snapshotRequests';
import type { Project, Run, Snapshot, Task } from './types';
import { defaultSettings, defaultPersonalBoard, stateNames } from './types';
import Icon from './components/Icon';
import TaskDetail from './components/TaskDetail';
import Gantt from './components/Gantt';
import Pending from './components/Pending';
import SettingsHub from './components/SettingsHub';
import WorkflowBoard from './components/WorkflowBoard';
import ProjectSummary from './components/ProjectSummary';
import StatusProgress from './components/StatusProgress';
import DepartmentSelect from './components/DepartmentSelect';
import './components/Notification.css';
import './components/WorkspaceLayout.css';
import useTaskFilters from './useTaskFilters';
import { availableFilterOwners, isApprovedFilterVersion } from './filterOptions';

type View = 'board' | 'personal' | 'gantt' | 'pending' | 'settings';
const navs: { id: View; label: string; icon: string; hint: string }[] = [
  { id: 'board', label: '需求总览', icon: 'board', hint: '模块进度与交付' },
  { id: 'gantt', label: '版本甘特', icon: 'gantt', hint: '排期与目标' },
  { id: 'personal', label: '个人工作台', icon: 'person', hint: '现在能做什么' },
  { id: 'pending', label: '同步与回写', icon: 'sync', hint: '选择后提交' },
  { id: 'settings', label: '设置', icon: 'settings', hint: '使用者、人员与连接' },
];
const empty: Snapshot = { tasks: [], projects: [], candidates: [], auth: {}, settings: defaultSettings };

export default function App() {
  const [boardMode, setBoardMode] = useState<BoardMode>(readBoardMode);
  const changeBoardMode = (value: BoardMode) => { saveBoardMode(value); setBoardMode(value); };
  const [personalAdd, setPersonalAdd] = useState(0);
  const [nodeShortcuts, setNodeShortcuts] = useState<NodeShortcuts>(readNodeShortcuts);
  const changeNodeShortcuts = (value: NodeShortcuts) => { saveNodeShortcuts(value); setNodeShortcuts(value); };
  const [snapshot, setSnapshot] = useState<Snapshot>(empty);
  const [projectId, setProjectId] = useState(() => localStorage.getItem('larkpm-project') || '');
  const [ganttScale, setGanttScale] = useState<GanttScale>(readGanttScale);
  const changeGanttScale = (value: GanttScale) => { saveGanttScale(value); setGanttScale(value); };
  const [view, setView] = useState<View>(() => {
    const saved = sessionStorage.getItem('larkpm-view');
    return navs.some(item => item.id === saved) ? saved as View : 'board';
  });
  useEffect(() => { sessionStorage.setItem('larkpm-view', view); }, [view]);
  const [settingsSection, setSettingsSection] = useState<'profile' | 'people' | 'connections'>('profile');
  const { search, setSearch, owner, setOwner, version, setVersion, department, setDepartment } = useTaskFilters(projectId, view);
  const [personalOwner, setPersonalOwner] = useState<string | null>(null);
  const [personalDepartment, setPersonalDepartment] = useState('');
  const [selected, setSelected] = useState(''), [error, setError] = useState(''), [notice, setNotice] = useState('');
  const [loading, setLoading] = useState(true), [busy, setBusy] = useState(false);
  const [newUpstream, setNewUpstream] = useState<string[]>([]);
  const [newModuleLocked, setNewModuleLocked] = useState(false);
  const [creating, setCreating] = useState(false), [newTitle, setNewTitle] = useState(''), [newModule, setNewModule] = useState('');
  const locked = useRef(false), fetchVersion = useRef(0);
  const snapshotRequests = useRef(new SnapshotRequests<Snapshot>());
  const sourcePending = useRef(false);
  const activeProject = useRef(projectId), detailWorking = useRef(false);
  activeProject.current = projectId;
  const onDetailWorking = useCallback((value: boolean) => { detailWorking.current = value; }, []);
  const refresh = useCallback(async (silent = false, fresh = false) => {
    if (activeProject.current !== projectId) return;
    const generation = ++fetchVersion.current;
    try {
      const data = await snapshotRequests.current.run(projectId, () => rpc<Snapshot>('snapshot', projectId ? { project: projectId } : {}), fresh);
      if (generation !== fetchVersion.current || activeProject.current !== projectId) return;
      setSnapshot({ ...empty, ...data });
      sourcePending.current = !!data.projects.find(project => project.id === projectId)?.source_refresh?.length;
      if (!data.projects.some(p => p.id === projectId && !p.archived)) setProjectId(data.projects.find(p => !p.archived)?.id || '');
      if (!silent) setError('');
    } catch (e) { if (generation === fetchVersion.current && !silent) setError(errorText(e)); }
    finally { if (generation === fetchVersion.current) setLoading(false); }
  }, [projectId]);
  useEffect(() => {
    let active = true, timer: number;
    const poll = async (initial = false) => {
      if (initial || (!locked.current && !detailWorking.current)) await refresh(!initial);
      if (active) timer = window.setTimeout(() => void poll(), sourcePending.current ? 1000 : 4000);
    };
    void poll(true);
    return () => { active = false; window.clearTimeout(timer); };
  }, [refresh]);
  useEffect(() => { localStorage.setItem('larkpm-project', projectId); setPersonalOwner(null); setPersonalDepartment(''); setSelected(''); }, [projectId]);
  useEffect(() => { if (!notice) return; const timeout = window.setTimeout(() => setNotice(''), 6000); return () => window.clearTimeout(timeout); }, [notice]);

  const run: Run = async <T,>(method: string, params: Record<string, unknown> = {}, message?: string) => {
    if (locked.current) return undefined;
    locked.current = true; setBusy(true); setError('');
    try {
      const result = await rpc<T>(method, params);
      await refresh(true, true);
      if (message) setNotice(message);
      return result;
    } catch (e) { setError(errorText(e)); await refresh(true, true); return undefined; }
    finally { locked.current = false; setBusy(false); }
  };
  const project = snapshot.projects.find(p => p.id === projectId);
  const activeProjects = snapshot.projects.filter(p => !p.archived);
  const tasks = snapshot.tasks.filter(t => !projectId || t.project === projectId);
  const effectiveDepartment = view === 'personal' ? personalDepartment : department;
  const departmentTasks = tasks.filter(t => !effectiveDepartment || t.departments.includes(effectiveDepartment));
  const people = availableFilterOwners(departmentTasks.flatMap(t => t.owners), snapshot.settings.people);
  const departmentCatalog = project?.department_catalog?.options || [];
  const departmentOptions = [...departmentCatalog, ...Array.from(new Set(tasks.flatMap(t => t.departments))).filter(name => !departmentCatalog.some(o => o.name === name)).map(name => ({ id: `local:${name}`, name, color: null }))];
  const versions = Array.from(new Set(tasks.map(t => t.version).filter(value => value && !isApprovedFilterVersion(value, project)))).sort();
  const selfId = snapshot.settings.profile.owner_id;
  const availableSelf = availableFilterOwners([{ id: selfId }], snapshot.settings.people).length > 0;
  useEffect(() => {
    if (!project || loading || !['board', 'gantt'].includes(view)) return;
    if (owner && !availableFilterOwners([{ id: owner }], snapshot.settings.people).length) setOwner('');
    if (version && isApprovedFilterVersion(version, project)) setVersion('');
  }, [project, loading, view, owner, version, snapshot.settings.people]);
  const needsIdentity = view === 'personal' && !selfId;
  const effectiveOwner = view === 'personal' ? personalOwner ?? selfId : owner;
  const scoped = needsIdentity ? [] : departmentTasks.filter(t => view !== 'personal' || !effectiveOwner || t.owners.some(o => o.id === effectiveOwner));
  const filtered = scoped.filter(t => view === 'personal' || ((!search || `${t.title} ${t.module}`.toLowerCase().includes(search.toLowerCase())) && (!effectiveOwner || t.owners.some(o => o.id === effectiveOwner)) && (!version || t.version === version)));
  const visible = filtered.filter(t => view !== 'personal' || !['done', 'closed'].includes(t.state));
  const creations = (snapshot.creations || []).filter(item => item.project === projectId);
  const pendingCount = tasks.filter(t => Object.keys(t.pending).length).length + creations.length;
  const conflictCount = tasks.filter(t => Object.keys(t.conflicts).length).length;
  const current = tasks.find(t => t.id === selected);
  function selectOwner(id: string) { if (view === 'personal') setPersonalOwner(id); else setOwner(id); }
  function selectDepartment(name: string) {
    if (view === 'personal') setPersonalDepartment(name); else setDepartment(name);
    if (effectiveOwner && !tasks.some(t => (!name || t.departments.includes(name)) && t.owners.some(o => o.id === effectiveOwner))) selectOwner('');
  }

  function switchView(id: View) { setView(id); setSelected(''); if (id === 'personal') { setPersonalOwner(null); setPersonalDepartment(''); } if (id === 'settings') setSettingsSection('profile'); }
  function openConnections() { setSettingsSection('connections'); setView('settings'); setSelected(''); }

  const filters = <div className="filterbar"><label className="search"><Icon name="search" size={16}/><input aria-label="搜索任务或模块" placeholder="搜索任务或模块…" value={search} onChange={e => setSearch(e.target.value)}/></label><DepartmentSelect label="按部门筛选" placeholder="全部部门" clearLabel="全部部门" value={effectiveDepartment} options={departmentOptions} onChange={selectDepartment}/><ListSelect aria-label="按处理人筛选" value={effectiveOwner} onChange={e => selectOwner(e.target.value)}><option value="">全部处理人</option>{selfId && availableSelf && !effectiveDepartment && !people.some(p => p.id === selfId) && <option value={selfId}>{snapshot.settings.profile.name || '本人'}</option>}{people.map(p => <option value={p.id} key={p.id}>{p.name || p.id}</option>)}</ListSelect><ListSelect aria-label="按版本筛选" value={version} onChange={e => setVersion(e.target.value)}><option value="">全部版本</option>{versions.map(v => <option key={v}>{v}</option>)}</ListSelect><button className={`button small ${effectiveOwner && effectiveOwner === selfId ? 'primary' : ''}`} disabled={!snapshot.settings.profile.owner_id || !availableSelf} title={snapshot.settings.profile.owner_id ? `查看${snapshot.settings.profile.name || '本人'}的任务` : '先在设置中关联使用者人员'} onClick={() => { if (view === 'personal') { setPersonalDepartment(''); setPersonalOwner(null); } else { setDepartment(''); setOwner(owner === selfId ? '' : selfId); } }}>我的任务</button><span className="result-count">{view === 'board' ? visible.filter(t => !['done', 'closed'].includes(t.state)).length : visible.length} 项</span></div>;

  return <div className="app-shell">
    <a className="skip-link" href="#workspace-main">跳到工作区</a>
    <aside className="sidebar">
      <div className="brand"><div className="brand-symbol"><span/><span/><span/></div><div><strong>LarkPM</strong><span>需求工作台</span></div><span className="version-tag">1.0.8</span></div>
      <div className="project-switch"><label htmlFor="project-selector">当前项目</label><ListSelect aria-label="当前项目" id="project-selector" value={projectId} onChange={e => setProjectId(e.target.value)} disabled={busy}>
        {!activeProjects.length && <option value="">尚未配置项目</option>}{activeProjects.map(p => <option value={p.id} key={p.id}>{p.name}</option>)}
      </ListSelect><button className="text-button" onClick={openConnections}>管理项目连接 <span>↗</span></button></div>
      <nav aria-label="工作台导航">{navs.map(n => <button key={n.id} className={`nav-item ${view === n.id ? 'selected' : ''}`} onClick={() => switchView(n.id)} aria-current={view === n.id ? 'page' : undefined}>
        <Icon name={n.icon}/><span>{n.label}</span>{n.id === 'pending' && pendingCount > 0 && <b className={conflictCount ? 'badge orange' : 'badge'}>{pendingCount}</b>}
      </button>)}</nav>
      <div className="sidebar-bottom"><div className="local-status" role="status"><i/>{loading ? '正在读取本地数据' : '更改已保存于本地'}</div><p>个人任务与依赖保存在本机<br/>飞书修改由你选择提交</p></div>
    </aside>
    <div className="workspace">
      <main id="workspace-main" className={`main-content ${view === 'settings' ? 'settings-main' : view === 'board' && project ? 'board-main' : view === 'personal' ? 'personal-main' : ''}`}>
        <div className="page-heading"><div><h1>{navs.find(n => n.id === view)?.label}</h1><p>{view === 'board' ? `按住 ${nodeShortcuts.arrange} 编排 · Ctrl＋点击多选 · 选中任务后按 ${shortcutText(nodeShortcuts.status)} 切换状态 · Esc 取消拖动` : view === 'personal' ? '默认展示你负责的任务，看清现在能做什么、还在等待谁。' : view === 'gantt' ? '真实排期与版本目标，缺少日期的工作单独列出。' : view === 'pending' ? '核对本地修改，解决冲突，再选择写回飞书。' : '配置使用者、人员部门与各项目的数据连接。'}</p></div>
          {!['pending', 'settings'].includes(view) && <div className="page-heading-actions"><button className="button" disabled={busy || !project?.base_token || !project?.table_id} onClick={() => void run('sync', { project: projectId }, '已读取飞书需求')}><Icon name="sync" size={14}/>{busy ? '处理中…' : '读取飞书'}</button><button className="button primary" disabled={busy || (view !== 'personal' && !project)} onClick={() => { if (view === 'personal') { setPersonalAdd(value => value + 1); return; } setNewModule(''); setNewModuleLocked(false); setNewUpstream([]); setCreating(true); }}><Icon name="plus" size={16}/>{view === 'personal' ? '新建待办' : '新建本地任务'}</button></div>}
        </div>
        {error && <div className="banner error" role="alert"><Icon name="alert"/><span>{error}</span><button aria-label="关闭错误提示" className="icon-button" onClick={() => setError('')}><Icon name="close" size={16}/></button></div>}
        {view === 'settings' ? <SettingsHub boardMode={boardMode} onBoardMode={changeBoardMode} nodeShortcuts={nodeShortcuts} onNodeShortcuts={changeNodeShortcuts} ganttScale={ganttScale} onGanttScale={changeGanttScale} settings={snapshot.settings} initialSection={settingsSection} projects={snapshot.projects} project={project} auth={snapshot.auth} run={run} busy={busy} onProject={setProjectId}/> : view === 'personal' ? <>{project && <ProjectSummary key={`summary:${project.id}`} project={project} tasks={tasks} run={run} busy={busy}/>}<Personal addRequest={personalAdd} config={snapshot.personal_board || defaultPersonalBoard} ownerId={selfId} key={`personal:${projectId}`} projectId={projectId} tasks={visible} allTasks={tasks} onSelect={setSelected} run={run} busy={busy}/></> : !project ? <div className="welcome"><div className="welcome-icon"><Icon name="board" size={36}/></div><h2>从一个项目开始</h2><p>连接你的飞书需求表，开始管理项目。<br/>每个项目的任务、依赖和回写清单彼此独立。</p><div className="button-row"><button className="button primary" onClick={openConnections}>配置需求表</button></div></div> : <>
          {['board', 'personal', 'gantt'].includes(view) && <ProjectSummary key={`summary:${project.id}`} project={project} tasks={tasks} run={run} busy={busy}/>}
          {['board', 'gantt'].includes(view) && <>
            <StatusProgress tasks={filtered}/>
            {view !== 'board' && filters}
          </>}
          {view === 'board' && <WorkflowBoard filterKey={JSON.stringify([search, owner, department])} displayMode={boardMode} shortcuts={nodeShortcuts} version={version} onCreate={(module, upstream = []) => { setNewModule(module); setNewModuleLocked(true); setNewUpstream(upstream); setCreating(true); }} controls={filters} key={`board:${projectId}`} project={project} run={run} busy={busy} tasks={visible} allTasks={tasks} departmentOptions={project?.department_catalog?.options || []} onSelect={setSelected}/>}


          {view === 'gantt' && <Gantt scale={ganttScale} tasks={visible} project={project} onSelect={setSelected} run={run} busy={busy}/>}
          {view === 'pending' && <Pending key={project.id} tasks={tasks} creations={creations} ignoredCreations={(snapshot.ignored_creations || []).filter(item => item.project === projectId)} project={project} run={run} busy={busy} onSelect={setSelected}/>}
        </>}
      </main>
    </div>
    {notice && <div className="banner success notification-toast" role="status"><Icon name="check"/><span>{notice}</span><button aria-label="关闭通知" className="icon-button" onClick={() => setNotice('')}><Icon name="close" size={16}/></button></div>}
    {current && <TaskDetail project={project} departmentOptions={project?.department_catalog?.options || []} key={current.id} settings={snapshot.settings} task={current} tasks={tasks} candidates={snapshot.candidates.filter(c => c.downstream === current.id)} onClose={() => setSelected('')} onChanged={() => refresh(true, true)} onWorkingChange={onDetailWorking} onError={setError} onSelect={setSelected} busy={busy}/>}
    {creating && <div className="modal-backdrop" onMouseDown={e => { if (e.target === e.currentTarget) setCreating(false); }}><section className="modal" role="dialog" aria-modal="true" aria-labelledby="new-task-heading"><header><h2 id="new-task-heading">新建本地任务</h2><button className="icon-button" aria-label="关闭新建任务" onClick={() => setCreating(false)}><Icon name="close"/></button></header><form onSubmit={e => { e.preventDefault(); void run<Task>('create', { project: projectId, title: newTitle, module: newModule, version: version || "", upstream: newUpstream }, '已新建本地任务').then(t => { if (t) { setCreating(false); setNewTitle(''); setNewModule(''); setSelected(t.id); } }); }}><label>任务标题<input autoFocus required maxLength={10000} value={newTitle} onChange={e => setNewTitle(e.target.value)} placeholder="要完成的具体工作"/></label><label>所属模块{newModuleLocked ? <span className="new-task-module-value" aria-label="所属模块">{newModule || '未归类'}</span> : <><input value={newModule} onChange={e => setNewModule(e.target.value)} placeholder="例如：新手引导" list="module-options"/><datalist id="module-options">{availableRequirementNames(tasks, project?.workflow_columns || []).map(m => <option key={m}>{m}</option>)}</datalist></>}</label><p className="muted">{newUpstream.length > 0 && <>前置任务：{newUpstream.map(id => tasks.find(task => task.id === id)?.title || id).join("、")}<br/></>}保存在本地，不会自动创建飞书记录。可在详情中关联上下游或转入 LinkinNotes。</p><div className="button-row right"><button className="button" type="button" onClick={() => setCreating(false)}>取消</button><button className="button primary" disabled={busy || !newTitle.trim()}>创建任务</button></div></form></section></div>}
  </div>;
}

export function Status({ task }: { task: Task }) { return <span className={`status-pill task-status ${task.state === 'todo' && task.readiness === 'blocked' ? 'blocked' : task.state}`}><i/>{task.state === 'todo' ? task.readiness === 'blocked' ? '等待上游' : '可开始' : stateNames[task.state]}</span>; }
export function People({ task }: { task: Task }) { return <span className="people" title={task.owners.map(o => o.name || o.id).join('、') || '未分配处理人'}><span className={`avatar ${!task.owners.length ? 'unassigned' : ''}`}>{(task.owners[0]?.name || task.owners[0]?.id || '?').slice(0, 1)}</span><span>{task.owners.map(o => o.name || o.id).join('、') || '未分配'}</span></span>; }
export function Empty({ text }: { text: string }) { return <div className="empty"><Icon name="box" size={30}/><p>{text}</p></div>; }
