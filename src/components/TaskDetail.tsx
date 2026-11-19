import { useEffect, useRef, useState } from 'react';
import { errorText, formatValue, parseConflict, rpc, today } from '../api';
import { fieldNames, stateNames, isUnavailable, type AppSettings, type Candidate, type State, type SyncField, type Task, type DepartmentOption, type Project } from '../types';
import { availableRequirementNames } from '../workflowLayout';
import { taskVersionOptions } from '../taskVersions';
import Icon from './Icon';
import InlineValue from './InlineValue';
import ListSelect from './ListSelect';
import './TaskModal.css';
import { DepartmentTag } from './DepartmentSelect';

type Props = { project?: Project; departmentOptions: DepartmentOption[]; settings: AppSettings; task: Task; tasks: Task[]; candidates: Candidate[]; onClose: () => void; onChanged: () => Promise<void>; onWorkingChange: (working: boolean) => void; onError: (e: string) => void; onSelect: (id: string) => void; busy: boolean };

export default function TaskDetail({ project, departmentOptions, settings, task, tasks, candidates, onClose, onChanged, onWorkingChange, onSelect }: Props) {
  const [base, setBase] = useState(task), [draft, setDraft] = useState({ ...task, department_override: null } as Task), [upstream, setUpstream] = useState(task.upstream);
  const [working, setWorking] = useState(false), [error, setError] = useState(''), [feedback, setFeedback] = useState('');
  useEffect(() => { onWorkingChange(working); return () => onWorkingChange(false); }, [working, onWorkingChange]);
  const [conflict, setConflict] = useState<Task | null>(null);
  const [confirmRemove, setConfirmRemove] = useState(false);
  const [customVersion, setCustomVersion] = useState(false);
  const [branchTitle, setBranchTitle] = useState(''), [depSearch, setDepSearch] = useState('');
  const heading = useRef<HTMLDivElement>(null), panel = useRef<HTMLElement>(null);
  const titleInput = useRef<HTMLTextAreaElement>(null);
  function resizeTitle() { const input = titleInput.current; if (input) { input.style.height = 'auto'; input.style.height = `${input.scrollHeight}px`; } }
  useEffect(() => {
    if (!project || project.version_catalog || !task.source) return;
    let active = true;
    void rpc('versions_sync', { project: project.id }).then(() => { if (active) void onChanged(); }).catch(e => { if (active) setError(errorText(e)); });
    return () => { active = false; };
  }, [project?.id]);
  useEffect(() => { heading.current?.focus(); }, []);
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !working) onClose();
      if (e.key !== 'Tab') return;
      const elements = Array.from(panel.current?.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),summary,a[href]') || []).filter(el => el.getClientRects().length);
      const first = elements[0], last = elements[elements.length - 1];
      if (e.shiftKey && (document.activeElement === first || document.activeElement === heading.current)) { e.preventDefault(); last?.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus(); }
    };
    window.addEventListener('keydown', key);
    return () => window.removeEventListener('keydown', key);
  }, [onClose, working]);
  const stale = task.revision !== base.revision;
  const modules = availableRequirementNames(tasks, project?.workflow_columns || []);
  const versions = taskVersionOptions(project, tasks, draft.version);
  const priorities = Array.from(new Set([...(project?.priority_catalog?.options || ['高', '中', '低']), ...tasks.map(task => task.priority || ''), draft.priority || ''].filter(Boolean)));
  const people = Array.from(new Map([...tasks.flatMap(t => t.owners), ...settings.people].map(p => [p.id, p])).values());
  const directory = new Map(settings.people.map(p => [p.id, p]));
  const defaultDepartments = Array.from(new Set(draft.owners.map(p => directory.get(p.id)?.department).filter((d): d is string => !!d)));
  const upstreamTasks = upstream.map(id => tasks.find(t => t.id === id)).filter((t): t is Task => !!t);
  const completeUpstream = upstreamTasks.filter(t => t.state === 'done');
  const remainingUpstream = upstreamTasks.filter(t => t.state !== 'done');
  const changed = ['title', 'start', 'end', 'owners', 'state', 'module', 'version', 'priority', 'department_override'].some(k => JSON.stringify(draft[k as keyof Task]) !== JSON.stringify(base[k as keyof Task]));
  const depChanged = JSON.stringify([...upstream].sort()) !== JSON.stringify([...base.upstream].sort());

  async function action(method: string, params: Record<string, unknown>, success: string) {
    if (working) return;
    setWorking(true); setError(''); setFeedback('');
    try {
      const next = await rpc<Task>(method, params);
      if (next?.id === base.id) {
        const rebased = { ...next };
        if (method !== 'edit') {
          for (const key of ['title', 'start', 'end', 'owners', 'state', 'module', 'version', 'priority', 'department_override'] as const) {
            if (JSON.stringify(draft[key]) !== JSON.stringify(base[key]) && !(method === 'resolve' && params.field === key)) Object.assign(rebased, { [key]: draft[key] });
          }
        }
        setBase(next); setDraft(rebased);
        if (method === 'dependencies') setUpstream(next.upstream);
      }
      setConflict(null); setFeedback(success); await onChanged(); return next;
    } catch (e) {
      const concurrent = parseConflict(e);
      if (concurrent) { setConflict(concurrent.current); setError(concurrent.message); }
      else setError(errorText(e));
    } finally { setWorking(false); }
  }
  async function save() {
    const patch: Record<string, unknown> = {};
    for (const key of ['title', 'start', 'end', 'owners', 'state', 'module', 'version', 'priority', 'department_override'] as const) {
      if (JSON.stringify(draft[key]) !== JSON.stringify(base[key])) patch[key] = draft[key];
    }
    if (!Object.keys(patch).length) return;
    const saved = await action('edit', { id: base.id, revision: base.revision, patch }, '任务已保存于本地');
    if (saved) onClose();
  }
  async function removeLocal() {
    if (working) return;
    setWorking(true); setError('');
    try {
      await rpc('remove_local', { id: base.id, revision: base.revision });
      onClose();
      await onChanged();
    } catch (e) {
      const concurrent = parseConflict(e);
      if (concurrent) { setConflict(concurrent.current); setError(concurrent.message); }
      else setError(errorText(e));
    } finally { setWorking(false); }
  }
  function useLatest(keepInput: boolean) {
    const latest = conflict || task;
    if (keepInput) {
      const rebased = { ...latest };
      for (const key of ['title', 'start', 'end', 'owners', 'state', 'module', 'version', 'priority', 'department_override'] as const) {
        if (JSON.stringify(draft[key]) !== JSON.stringify(base[key])) Object.assign(rebased, { [key]: draft[key] });
      }
      setDraft(rebased);
      if (!depChanged) setUpstream(latest.upstream);
      setFeedback('已保留你修改过的字段，其余采用最新内容，请核对后重新保存。');
    } else { setDraft(latest); setUpstream(latest.upstream); }
    setBase(latest); setConflict(null); setError('');
  }

  return <div className="detail-overlay" onMouseDown={e => { if (e.target === e.currentTarget && !working) onClose(); }}>
    <aside ref={panel} className="detail-panel" role="dialog" aria-modal="true" aria-label="任务详情"><button className="icon-button task-detail-close" aria-label="关闭任务详情" disabled={working} onClick={onClose}><Icon name="close"/></button>
      <div className="detail-scroll">
        {error && <div className="banner error" role="alert">{error}</div>}
        {(stale || conflict) && <section className="revision-conflict"><h3>另一端有新修改</h3><p>当前输入已保留。请比较内容后决定，系统不会自动覆盖。</p>{conflict && <div className="compare-grid"><div><small>当前输入</small><p>{draft.title}</p><span>{stateNames[draft.state]} · {draft.start || '未定'} → {draft.end || '未定'}</span></div><div><small>最新版本</small><p>{conflict.title}</p><span>{stateNames[conflict.state]} · {conflict.start || '未定'} → {conflict.end || '未定'}</span></div></div>}<div className="button-row"><button className="button small" onClick={() => useLatest(false)}>载入最新内容</button><button className="button small" onClick={() => useLatest(true)}>保留输入，比较后重存</button></div></section>}
        {task.source?.missing && <div className="banner warning">飞书记录已不可见或已删除，不能直接写回。可从本地移除。</div>}
        <form onSubmit={e => { e.preventDefault(); void save(); }} className="task-form task-inline-form">
          <div className="task-inline-title" ref={heading} tabIndex={-1}><InlineValue revision={base.revision} label="任务标题" value={draft.title}><textarea ref={titleInput} aria-label="任务标题" rows={1} required maxLength={10000} value={draft.title} onFocus={resizeTitle} onChange={e => { setDraft({ ...draft, title: e.target.value }); resizeTitle(); }}/></InlineValue></div>
          <div className="task-inline-grid">
            <div className="inline-field"><span className="inline-field-label">状态</span><InlineValue revision={base.revision} label="工作状态" value={<span className={`status-pill task-status ${draft.state}`}><i/>{stateNames[draft.state]}</span>}><ListSelect aria-label="工作状态" value={draft.state} onChange={e => setDraft({ ...draft, state: e.target.value as State })}>{Object.entries(stateNames).map(([k, v]) => <option key={k} value={k} disabled={k === 'active' && task.state !== 'active' && task.blocked_by.length > 0}>{v}</option>)}</ListSelect></InlineValue></div>
            <div className="inline-field"><span className="inline-field-label">优先级</span><ListSelect aria-label="任务优先级" value={draft.priority || ''} onChange={event => setDraft({ ...draft, priority: event.target.value })}><option value="">未设置</option>{priorities.map(priority => <option key={priority} value={priority}>{priority}</option>)}</ListSelect></div>
            <div className="inline-field"><span className="inline-field-label">所属需求</span><ListSelect aria-label="所属模块" value={draft.module} renderValue={() => draft.module || '未归类'} onChange={e => setDraft({ ...draft, module: e.target.value })}><option value="">未归类</option>{modules.map(module => <option key={module} value={module}>{module}</option>)}</ListSelect></div>
            <div className="inline-field"><span className="inline-field-label">版本</span>{customVersion ? <input autoFocus aria-label="自定义版本" value={draft.version} onChange={e => setDraft({ ...draft, version: e.target.value })} onBlur={() => setCustomVersion(false)} onKeyDown={e => { if (e.key === 'Enter' || e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); setCustomVersion(false); } }}/> : <ListSelect aria-label="版本" value={draft.version} onChange={e => { if (e.target.value === '__custom_version__') setCustomVersion(true); else setDraft({ ...draft, version: e.target.value }); }}><option value="">未设置</option>{versions.map(v => <option key={v} value={v}>{v}</option>)}{!project?.version_catalog?.selectable && <option value="__custom_version__">自定义版本…</option>}</ListSelect>}</div>
            <div className="inline-field"><span className="inline-field-label">开始</span><InlineValue revision={base.revision} label="开始时间" value={draft.start || '未排期'}><input aria-label="开始时间" type="date" value={draft.start} onFocus={() => { if (!draft.start) setDraft(previous => ({ ...previous, start: today() })); }} onKeyDown={event => { if (event.key === 'Backspace' || event.key === 'Delete') { event.preventDefault(); setDraft(previous => ({ ...previous, start: '' })); } }} onChange={e => setDraft({ ...draft, start: e.target.value })}/></InlineValue></div>
            <div className="inline-field"><span className="inline-field-label">截止</span><InlineValue revision={base.revision} label="截止时间" value={draft.end || '未排期'}><input aria-label="截止时间" type="date" value={draft.end} min={draft.start || undefined} onFocus={() => { if (!draft.end) setDraft(previous => ({ ...previous, end: today() })); }} onKeyDown={event => { if (event.key === 'Backspace' || event.key === 'Delete') { event.preventDefault(); setDraft(previous => ({ ...previous, end: '' })); } }} onChange={e => setDraft({ ...draft, end: e.target.value })}/></InlineValue></div>
          </div>
          <div className="task-owner-department">
            <div className="inline-field"><span className="inline-field-label">处理人</span><ListSelect aria-label="处理人" value="" selectedValues={draft.owners.map(p => p.id)} onChange={() => {}} onToggle={id => {
              const person = people.find(p => p.id === id);
              const owners = !id ? [] : draft.owners.some(p => p.id === id) ? draft.owners.filter(p => p.id !== id) : person ? [...draft.owners, { id: person.id, name: person.name }] : draft.owners;
              setDraft({ ...draft, owners, department_override: null });
            }} renderValue={() => draft.owners.map(p => p.name || '未命名人员').join('、') || '未分配'}>
              <option value="">未分配</option>{people.filter(p => !isUnavailable(directory.get(p.id)) || draft.owners.some(o => o.id === p.id)).map(p => <option value={p.id} key={p.id}>{p.name || '未命名人员'}{directory.get(p.id)?.department ? ` · ${directory.get(p.id)!.department}` : ''}</option>)}
            </ListSelect></div>
            <div className="inline-field"><span className="inline-field-label">部门</span><div className="task-auto-departments" role="status" aria-label="处理人部门">{defaultDepartments.length ? defaultDepartments.map(name => <DepartmentTag key={name} name={name} options={departmentOptions}/>) : <span className="muted">未配置</span>}</div></div>
          </div>
          <div className="task-detail-actions"><button type="button" className="button task-remove-button" disabled={working} onClick={() => setConfirmRemove(value => !value)}>从本地移除</button><div className="button-row right">{feedback && <span className="task-save-feedback" role="status">{feedback}</span>}<button className="button primary" disabled={working || !changed || !draft.title.trim()}>{working ? '处理中…' : '保存修改'}</button></div></div>
          {confirmRemove && <div className="task-remove-confirm" role="group" aria-label="确认从本地移除"><p>从本地工作台移除“{base.title}”？不会删除飞书记录、分支任务或个人笔记；相关前置依赖将解除，重新读取也不会自动加回。</p><div className="button-row right"><button type="button" className="button small" disabled={working} onClick={() => setConfirmRemove(false)}>取消</button><button type="button" className="button small task-remove-button" disabled={working || stale} onClick={() => void removeLocal()}>确认移除</button></div></div>}
        </form>
        <details className="detail-section compact-section"><summary>前置依赖 · {upstream.length} 项</summary><p className="section-description">前置任务交付后提示可开始；不会自动将本任务改为进行中。</p>{remainingUpstream.map(t => <button key={t.id} className="upstream-row" onClick={() => onSelect(t.id)}><span className="mini-dot amber"/><span>{t.title}</span><small>{t.owners.map(o => o.name || o.id).join('、') || '未分配'}</small><Icon name="chevron" size={12}/></button>)}{completeUpstream.length > 0 && <details className="completed-upstream"><summary>已交付上游 · {completeUpstream.length} 项</summary>{completeUpstream.map(t => <button key={t.id} className="upstream-row done" onClick={() => onSelect(t.id)}><Icon name="check" size={13}/><span>{t.title}</span><Icon name="chevron" size={12}/></button>)}</details>}
          <div className="dependency-editor dependency-editor-flat"><input aria-label="搜索前置任务" placeholder="搜索同项目任务…" value={depSearch} onChange={e => setDepSearch(e.target.value)}/><div className="dependency-options">{tasks.filter(t => t.id !== task.id && (!depSearch || t.title.toLowerCase().includes(depSearch.toLowerCase()))).map(t => <label key={t.id} className="checkbox-label"><input type="checkbox" checked={upstream.includes(t.id)} onChange={e => setUpstream(e.target.checked ? [...upstream, t.id] : upstream.filter(id => id !== t.id))}/><span>{t.title}<small>{t.module || '未归类'} · {stateNames[t.state]}</small></span></label>)}</div><button className="button small" disabled={working || !depChanged} onClick={() => void action('dependencies', { id: base.id, upstream, revision: base.revision }, '依赖已保存，循环关系会被拒绝')}>保存前置依赖</button></div>
          {candidates.length > 0 && <div className="candidates"><h4>规则识别的候选依赖 <span>待确认</span></h4><p className="muted">依据任务标题和常见交付流程，仅作为建议。</p>{candidates.map(c => <div className="candidate" key={c.upstream}><strong>{tasks.find(t => t.id === c.upstream)?.title || c.upstream}</strong><p>{c.reason}</p><button className="button small" disabled={working || upstream.includes(c.upstream)} onClick={() => { const next = Array.from(new Set([...upstream, c.upstream])); void action('dependencies', { id: base.id, upstream: next, revision: base.revision }, '已确认候选依赖'); }}>确认此依赖</button></div>)}</div>}
        </details>
        <details className="detail-section compact-section"><summary>新增分支任务</summary><p className="section-description">从当前节点继续拆分个人工作，默认以当前任务为上游；可随后调整。</p><div className="inline-create"><input aria-label="分支任务标题" placeholder="分支任务要做什么？" value={branchTitle} onChange={e => setBranchTitle(e.target.value)}/><button className="button" disabled={working || !branchTitle.trim()} onClick={() => void action('branch', { id: task.id, title: branchTitle }, '已建立本地分支任务').then(result => { if (result) { setBranchTitle(''); onSelect(result.id); } })}><Icon name="plus" size={16}/>创建</button></div>{tasks.filter(t => t.branch_of === task.id).map(t => <button key={t.id} className="upstream-row" onClick={() => onSelect(t.id)}><Icon name="branch" size={13}/><span>{t.title}</span><small>{stateNames[t.state]}</small></button>)}</details>
        {Object.keys(task.conflicts).length > 0 && <section className="detail-section"><h3>飞书同步冲突</h3>{Object.entries(task.conflicts).map(([field, value]) => value && <div className="candidate" key={field}><strong>{fieldNames[field as SyncField]}</strong><div className="compare-grid"><div><small>本地</small><p>{formatValue(value.local)}</p></div><div><small>飞书</small><p>{formatValue(value.remote)}</p></div></div><div className="button-row"><button className="button small" disabled={working} onClick={() => void action('resolve', { id: base.id, field, choice: 'local', revision: base.revision }, '已保留本地修改，等待手动回写')}>保留本地</button><button className="button small" disabled={working} onClick={() => void action('resolve', { id: base.id, field, choice: 'remote', revision: base.revision }, '已采用飞书内容')}>采用飞书</button></div></div>)}</section>}

      </div>
    </aside>
  </div>;
}
