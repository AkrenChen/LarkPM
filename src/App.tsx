import { readGanttScale, saveGanttScale, type GanttScale } from './preferences';
import Personal from './components/Personal';
import ListSelect from './components/ListSelect';
import { useCallback, useEffect, useRef, useState } from 'react';
import { dateLabel, errorText, rpc } from './api';
import type { Project, Run, Snapshot, Task } from './types';
import { defaultSettings, stateNames } from './types';
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
  const [snapshot, setSnapshot] = useState<Snapshot>(empty);
  const [projectId, setProjectId] = useState(() => localStorage.getItem('larkpm-project') || '');
  const [ganttScale, setGanttScale] = useState<GanttScale>(readGanttScale);
  const changeGanttScale = (value: GanttScale) => { saveGanttScale(value); setGanttScale(value); };
  const [view, setView] = useState<View>('board');
  const [settingsSection, setSettingsSection] = useState<'profile' | 'people' | 'connections'>('profile');
  const [search, setSearch] = useState(''), [owner, setOwner] = useState(''), [version, setVersion] = useState('');
  const [personalOwner, setPersonalOwner] = useState<string | null>(null);
  const [department, setDepartment] = useState(''), [personalDepartment, setPersonalDepartment] = useState('');
  const [selected, setSelected] = useState(''), [error, setError] = useState(''), [notice, setNotice] = useState('');
  const [loading, setLoading] = useState(true), [busy, setBusy] = useState(false), [showDone, setShowDone] = useState(false);
  const [creating, setCreating] = useState(false), [newTitle, setNewTitle] = useState(''), [newModule, setNewModule] = useState('');
  const locked = useRef(false), fetchVersion = useRef(0);
  const refresh = useCallback(async (silent = false) => {
    const generation = ++fetchVersion.current;
    try {
      const data = await rpc<Snapshot>('snapshot', projectId ? { project: projectId } : {});
      if (generation !== fetchVersion.current) return;
      setSnapshot({ ...empty, ...data });
      if (!projectId && data.projects.length) setProjectId(data.projects[0].id);
      if (!silent) setError('');
    } catch (e) { if (generation === fetchVersion.current && !silent) setError(errorText(e)); }
    finally { if (generation === fetchVersion.current) setLoading(false); }
  }, [projectId]);
  useEffect(() => { void refresh(); const timer = window.setInterval(() => { if (!locked.current) void refresh(true); }, 4000); return () => window.clearInterval(timer); }, [refresh]);
  useEffect(() => { localStorage.setItem('larkpm-project', projectId); setOwner(''); setPersonalOwner(null); setDepartment(''); setPersonalDepartment(''); setVersion(''); setSelected(''); }, [projectId]);
  useEffect(() => { if (!notice) return; const timeout = window.setTimeout(() => setNotice(''), 6000); return () => window.clearTimeout(timeout); }, [notice]);

  const run: Run = async <T,>(method: string, params: Record<string, unknown> = {}, message?: string) => {
    if (locked.current) return undefined;
    locked.current = true; setBusy(true); setError('');
    try {
      const result = await rpc<T>(method, params);
      await refresh(true);
      if (message) setNotice(message);
      return result;
    } catch (e) { setError(errorText(e)); await refresh(true); return undefined; }
    finally { locked.current = false; setBusy(false); }
  };
  const project = snapshot.projects.find(p => p.id === projectId);
  const tasks = snapshot.tasks.filter(t => !projectId || t.project === projectId);
  const effectiveDepartment = view === 'personal' ? personalDepartment : department;
  const departmentTasks = tasks.filter(t => !effectiveDepartment || t.departments.includes(effectiveDepartment));
  const people = Array.from(new Map(departmentTasks.flatMap(t => t.owners).map(o => [o.id, o])).values());
  const departmentCatalog = project?.department_catalog?.options || [];
  const departmentOptions = [...departmentCatalog, ...Array.from(new Set(tasks.flatMap(t => t.departments))).filter(name => !departmentCatalog.some(o => o.name === name)).map(name => ({ id: `local:${name}`, name, color: null }))];
  const versions = Array.from(new Set(tasks.map(t => t.version).filter(Boolean))).sort();
  const selfId = snapshot.settings.profile.owner_id;
  const needsIdentity = view === 'personal' && !selfId;
  const effectiveOwner = view === 'personal' ? personalOwner ?? selfId : owner;
  const scoped = needsIdentity ? [] : departmentTasks.filter(t => view !== 'personal' || !effectiveOwner || t.owners.some(o => o.id === effectiveOwner));
  const filtered = scoped.filter(t => view === 'personal' || ((!search || `${t.title} ${t.module}`.toLowerCase().includes(search.toLowerCase())) && (!effectiveOwner || t.owners.some(o => o.id === effectiveOwner)) && (!version || t.version === version)));
  const visible = filtered.filter(t => (view !== 'personal' && showDone) || !['done', 'closed'].includes(t.state));
  const pendingCount = tasks.filter(t => Object.keys(t.pending).length).length;
  const conflictCount = tasks.filter(t => Object.keys(t.conflicts).length).length;
  const current = tasks.find(t => t.id === selected);
  function selectOwner(id: string) { if (view === 'personal') setPersonalOwner(id); else setOwner(id); }
  function selectDepartment(name: string) {
    if (view === 'personal') setPersonalDepartment(name); else setDepartment(name);
    if (effectiveOwner && !tasks.some(t => (!name || t.departments.includes(name)) && t.owners.some(o => o.id === effectiveOwner))) selectOwner('');
  }

  async function demo() {
    const data = await run<{ project: string }>('demo', {}, '已建立独立示例项目，数据均为虚构');
    if (data) { setProjectId(data.project); setView('board'); }
  }
  function switchView(id: View) { setView(id); setSelected(''); if (id === 'personal') { setPersonalOwner(null); setPersonalDepartment(''); } if (id === 'settings') setSettingsSection('profile'); }
  function openConnections() { setSettingsSection('connections'); setView('settings'); setSelected(''); }

  const filters = <div className="filterbar"><label className="search"><Icon name="search" size={16}/><input aria-label="搜索任务或模块" placeholder="搜索任务或模块…" value={search} onChange={e => setSearch(e.target.value)}/></label><DepartmentSelect label="按部门筛选" placeholder="全部部门" clearLabel="全部部门" value={effectiveDepartment} options={departmentOptions} onChange={selectDepartment}/><ListSelect aria-label="按处理人筛选" value={effectiveOwner} onChange={e => selectOwner(e.target.value)}><option value="">全部处理人</option>{selfId && !effectiveDepartment && !people.some(p => p.id === selfId) && <option value={selfId}>{snapshot.settings.profile.name || '本人'}</option>}{people.map(p => <option value={p.id} key={p.id}>{p.name || p.id}</option>)}</ListSelect><ListSelect aria-label="按版本筛选" value={version} onChange={e => setVersion(e.target.value)}><option value="">全部版本</option>{versions.map(v => <option key={v}>{v}</option>)}</ListSelect><button className={`button small ${effectiveOwner && effectiveOwner === selfId ? 'primary' : ''}`} disabled={!snapshot.settings.profile.owner_id} title={snapshot.settings.profile.owner_id ? `查看${snapshot.settings.profile.name || '本人'}的任务` : '先在设置中关联使用者人员'} onClick={() => { if (view === 'personal') { setPersonalDepartment(''); setPersonalOwner(null); } else { setDepartment(''); setOwner(owner === selfId ? '' : selfId); } }}>我的任务</button>{view !== 'board' && <label className="checkbox-label"><input type="checkbox" checked={showDone} onChange={e => setShowDone(e.target.checked)}/>显示已交付／关闭</label>}<span className="result-count">{view === 'board' ? visible.filter(t => !['done', 'closed'].includes(t.state)).length : visible.length} 项</span></div>;

  return <div className="app-shell">
    <a className="skip-link" href="#workspace-main">跳到工作区</a>
    <aside className="sidebar">
      <div className="brand"><div className="brand-symbol"><span/><span/><span/></div><div><strong>LarkPM</strong><span>需求工作台</span></div><span className="version-tag">1.0</span></div>
      <div className="project-switch"><label htmlFor="project-selector">当前项目</label><ListSelect aria-label="当前项目" id="project-selector" value={projectId} onChange={e => setProjectId(e.target.value)} disabled={busy}>
        {!snapshot.projects.length && <option value="">尚未配置项目</option>}{snapshot.projects.map(p => <option value={p.id} key={p.id}>{p.name}</option>)}
      </ListSelect><button className="text-button" onClick={openConnections}>管理项目连接 <span>↗</span></button></div>
      <nav aria-label="工作台导航">{navs.map(n => <button key={n.id} className={`nav-item ${view === n.id ? 'selected' : ''}`} onClick={() => switchView(n.id)} aria-current={view === n.id ? 'page' : undefined}>
        <Icon name={n.icon}/><span>{n.label}</span>{n.id === 'pending' && pendingCount > 0 && <b className={conflictCount ? 'badge orange' : 'badge'}>{pendingCount}</b>}
      </button>)}</nav>
      <div className="sidebar-bottom"><div className="local-status" role="status"><i/>{loading ? '正在读取本地数据' : '更改已保存于本地'}</div><p>个人任务与依赖保存在本机<br/>飞书修改由你选择提交</p><button className="text-button" disabled={busy} onClick={() => void demo()}>试用流程示例 <Icon name="arrow" size={14}/></button></div>
    </aside>
    <div className="workspace">
      <main id="workspace-main" className={`main-content ${view === 'settings' ? 'settings-main' : view === 'board' && project ? 'board-main' : ''}`}>
        <div className="page-heading"><div><h1>{navs.find(n => n.id === view)?.label}</h1><p>{view === 'board' ? '按模块看进展，按交付物理清依赖。' : view === 'personal' ? '默认展示你负责的任务，看清现在能做什么、还在等待谁。' : view === 'gantt' ? '真实排期与版本目标，缺少日期的工作单独列出。' : view === 'pending' ? '核对本地修改，解决冲突，再选择写回飞书。' : '配置使用者、人员部门与各项目的数据连接。'}</p></div>
          {!['pending', 'settings'].includes(view) && <div className="page-heading-actions"><button className="button" disabled={busy || !project?.base_token || !project?.table_id} onClick={() => void run('sync', { project: projectId }, '已从飞书读取需求与关联表')}><Icon name="sync" size={14}/>{busy ? '处理中…' : '读取飞书'}</button><button className="button primary" disabled={!project || busy} onClick={() => setCreating(true)}><Icon name="plus" size={16}/>新建本地任务</button></div>}
        </div>
        {error && <div className="banner error" role="alert"><Icon name="alert"/><span>{error}</span><button aria-label="关闭错误提示" className="icon-button" onClick={() => setError('')}><Icon name="close" size={16}/></button></div>}
        {view === 'settings' ? <SettingsHub ganttScale={ganttScale} onGanttScale={changeGanttScale} settings={snapshot.settings} initialSection={settingsSection} projects={snapshot.projects} project={project} auth={snapshot.auth} run={run} busy={busy} onProject={setProjectId}/> : !project ? <div className="welcome"><div className="welcome-icon"><Icon name="board" size={36}/></div><h2>从一个项目开始</h2><p>连接你自己的飞书需求表，或先用虚构系统体验任务流转。<br/>每个项目的任务、依赖和回写清单彼此独立。</p><div className="button-row"><button className="button primary" onClick={openConnections}>配置需求表</button><button className="button" disabled={busy} onClick={() => void demo()}>载入流程示例</button></div></div> : <>
          {['board', 'personal', 'gantt'].includes(view) && <ProjectSummary key={project.id} project={project} tasks={tasks} run={run} busy={busy}/>}
          {['board', 'gantt'].includes(view) && <>
            <StatusProgress tasks={scoped}/>
            {view !== 'board' && filters}
          </>}
          {view === 'board' && <WorkflowBoard onCreate={module => { setNewModule(module); setCreating(true); }} controls={filters} key={projectId} project={project} run={run} busy={busy} tasks={visible} allTasks={tasks} departmentOptions={project?.department_catalog?.options || []} onSelect={setSelected}/>}
          {needsIdentity && <div className="welcome"><h2>先关联你的人员身份</h2><p>关联后，个人工作台默认只展示你负责的任务。</p><button className="button primary" onClick={() => switchView('settings')}>设置使用者</button></div>}
          {view === 'personal' && !needsIdentity && <Personal key={projectId} projectId={projectId} tasks={visible} allTasks={tasks} onSelect={setSelected} run={run} busy={busy}/>}
          {view === 'gantt' && <Gantt scale={ganttScale} tasks={visible} project={project} onSelect={setSelected} run={run} busy={busy}/>}
          {view === 'pending' && <Pending tasks={tasks} project={project} run={run} busy={busy} onSelect={setSelected}/>}
        </>}
      </main>
    </div>
    {notice && <div className="banner success notification-toast" role="status"><Icon name="check"/><span>{notice}</span><button aria-label="关闭通知" className="icon-button" onClick={() => setNotice('')}><Icon name="close" size={16}/></button></div>}
    {current && <TaskDetail departmentOptions={project?.department_catalog?.options || []} key={current.id} settings={snapshot.settings} task={current} tasks={tasks} candidates={snapshot.candidates.filter(c => c.downstream === current.id)} onClose={() => setSelected('')} onChanged={() => refresh(true)} onError={setError} onSelect={setSelected} busy={busy}/>}
    {creating && <div className="modal-backdrop" onMouseDown={e => { if (e.target === e.currentTarget) setCreating(false); }}><section className="modal" role="dialog" aria-modal="true" aria-labelledby="new-task-heading"><header><h2 id="new-task-heading">新建本地任务</h2><button className="icon-button" aria-label="关闭新建任务" onClick={() => setCreating(false)}><Icon name="close"/></button></header><form onSubmit={e => { e.preventDefault(); void run<Task>('create', { project: projectId, title: newTitle, module: newModule }, '已新建本地任务').then(t => { if (t) { setCreating(false); setNewTitle(''); setNewModule(''); setSelected(t.id); } }); }}><label>任务标题<input autoFocus required maxLength={10000} value={newTitle} onChange={e => setNewTitle(e.target.value)} placeholder="要完成的具体工作"/></label><label>所属模块<input value={newModule} onChange={e => setNewModule(e.target.value)} placeholder="例如：新手引导" list="module-options"/><datalist id="module-options">{Array.from(new Set([...tasks.map(t => t.module), ...(project?.workflow_columns || []).map(c => c.name)].filter(Boolean))).map(m => <option key={m}>{m}</option>)}</datalist></label><p className="muted">保存在本地，不会自动创建飞书记录。可在详情中关联上下游或转入 LinkinNotes。</p><div className="button-row right"><button className="button" type="button" onClick={() => setCreating(false)}>取消</button><button className="button primary" disabled={busy || !newTitle.trim()}>创建任务</button></div></form></section></div>}
  </div>;
}

export function Status({ task }: { task: Task }) { return <span className={`status-pill ${task.state === 'todo' && task.readiness === 'blocked' ? 'blocked' : task.state}`}><i/>{task.state === 'todo' ? task.readiness === 'blocked' ? '等待上游' : '可开始' : stateNames[task.state]}</span>; }
export function People({ task }: { task: Task }) { return <span className="people" title={task.owners.map(o => o.name || o.id).join('、') || '未分配处理人'}><span className={`avatar ${!task.owners.length ? 'unassigned' : ''}`}>{(task.owners[0]?.name || task.owners[0]?.id || '?').slice(0, 1)}</span><span>{task.owners.map(o => o.name || o.id).join('、') || '未分配'}</span></span>; }
export function Empty({ text }: { text: string }) { return <div className="empty"><Icon name="box" size={30}/><p>{text}</p></div>; }
