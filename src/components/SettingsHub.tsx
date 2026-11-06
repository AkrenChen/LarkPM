import type { GanttScale } from '../preferences';
import ListSelect from './ListSelect';
import { useEffect, useState } from 'react';
import { employmentNames, isUnavailable, type EmploymentStatus, type AppSettings, type Auth, type Person, type Project, type Run } from '../types';
import ProjectConnections from './Settings';
import Icon from './Icon';
import DepartmentSelect from './DepartmentSelect';
import './SettingsHub.css';

type Section = 'profile' | 'people' | 'connections' | 'personalization';
type Props = { ganttScale: GanttScale; onGanttScale: (value: GanttScale) => void; settings: AppSettings; projects: Project[]; project?: Project; auth: Auth; run: Run; busy: boolean; onProject: (id: string) => void; initialSection: Section };
const sections: { id: Section; title: string; hint: string; icon: string }[] = [
  { id: 'profile', title: '使用者', hint: '名称与我的任务', icon: 'person' },
  { id: 'people', title: '人员与部门', hint: '跨项目的默认归属', icon: 'board' },
  { id: 'personalization', title: '个性化', hint: '甘特显示偏好', icon: 'settings' },
  { id: 'connections', title: '项目与连接', hint: '需求表、字段与飞书授权', icon: 'link' },
];

export default function SettingsHub({ settings, initialSection, ...props }: Props) {
  const [section, setSection] = useState<Section>(initialSection);
  const [base, setBase] = useState(settings), [profile, setProfile] = useState({ ...settings.profile });
  const [people, setPeople] = useState<Person[]>(settings.people.map(p => ({ ...p })));
  const [search, setSearch] = useState(''), [personId, setPersonId] = useState(''), [personName, setPersonName] = useState(''), [personDepartment, setPersonDepartment] = useState('');
  const [addError, setAddError] = useState('');
  const [departmentFilter, setDepartmentFilter] = useState(''), [statusFilter, setStatusFilter] = useState('visible');
  const [selectedIds, setSelectedIds] = useState<string[]>([]), [batchStatus, setBatchStatus] = useState<EmploymentStatus>('active'), [batchDepartment, setBatchDepartment] = useState('');
  const dirty = JSON.stringify(profile) !== JSON.stringify(base.profile) || JSON.stringify(people) !== JSON.stringify(base.people);
  function load(next: AppSettings, resetSelection = false) {
    setBase(next); setProfile({ ...next.profile }); setPeople(next.people.map(p => ({ ...p })));
    if (resetSelection) setSelectedIds([]);
  }
  useEffect(() => { if (!dirty) load(settings); }, [settings]);
  useEffect(() => { setSection(initialSection); }, [initialSection]);
  useEffect(() => { setSelectedIds([]); }, [search, departmentFilter, statusFilter]);
  const departmentOptions = props.project?.department_catalog?.options || [];
  const departmentError = props.project?.department_catalog?.error;
  useEffect(() => {
    setBatchDepartment(''); setPersonDepartment('');
    if (section === 'people' && props.project && !props.project.department_catalog) void props.run('departments_sync', { project: props.project.id });
  }, [section, props.project?.id]);
  const stale = base.revision !== settings.revision;
  const catalog = people;
  const departments = Array.from(new Set([...departmentOptions.map(o => o.name), ...people.map(p => p.department).filter(Boolean)]));
  const visible = catalog.filter(p => `${p.name} ${p.id} ${p.department}`.toLowerCase().includes(search.toLowerCase())
    && (!departmentFilter || (departmentFilter === '__empty' ? !p.department : p.department === departmentFilter))
    && (statusFilter === 'all' || (statusFilter === 'visible' ? !isUnavailable(p) : (p.employment_status || 'unknown') === statusFilter)));
  const departedCount = catalog.filter(isUnavailable).length;
  async function save() {
    const result = await props.run<AppSettings>('settings_save', { revision: base.revision, profile, people }, '设置已保存于本机');
    if (result) load(result, true);
  }
  function addPerson() {
    const id = personId.trim();
    if (!id) return;
    if (people.some(p => p.id === id)) { setAddError('这个人员 ID 已在列表中，请直接修改其部门。'); return; }
    setPeople([...people, { id, name: personName.trim() || id, department: personDepartment.trim(), employment_status: 'unknown' }]);
    setPersonId(''); setPersonName(''); setPersonDepartment(''); setAddError('');
  }
  return <div className="settings-hub">
    <nav className="settings-tabs" aria-label="设置分类">{sections.map(s => <button key={s.id} title={s.hint} aria-current={section === s.id ? 'page' : undefined} className={section === s.id ? 'selected' : ''} onClick={() => setSection(s.id)}><Icon name={s.icon} size={16}/><span>{s.title}</span></button>)}</nav>
    <div className="settings-content">
      {section === 'personalization' ? <section className="settings-card preference-card"><header><div className="settings-card-icon"><Icon name="settings"/></div><div><h2>个性化</h2><p>本机跨项目共用，选择后自动保存。</p></div></header><label>甘特显示周期<ListSelect aria-label="甘特显示周期" value={props.ganttScale} onChange={event => props.onGanttScale(event.target.value as GanttScale)}><option value="week">按周 · 7天</option><option value="fortnight">双周 · 14天</option><option value="month">按月 · 自然月</option></ListSelect><small>左右箭头按所选周期翻页，右侧按钮返回当前周期。</small></label></section> : section === 'connections' ? <ProjectConnections {...props}/> : <>
        {stale && <div className="banner warning"><span>设置已在另一处更新，当前输入保留。重新载入会放弃此处未保存的修改。</span><button className="button small" onClick={() => load(settings, true)}>重新载入设置</button></div>}
        {section === 'profile' ? <section className="settings-card preference-card"><header><div className="settings-card-icon"><Icon name="person"/></div><div><h2>使用者</h2><p>让工作台知道你是谁，方便归类个人任务。</p></div></header>
          <label>使用者名称<input maxLength={200} value={profile.name} onChange={e => setProfile({ ...profile, name: e.target.value })} placeholder="你的常用名称"/></label>
          <label>关联飞书人员<select aria-label="关联飞书人员" value={profile.owner_id} onChange={e => setProfile({ ...profile, owner_id: e.target.value })}><option value="">暂不关联</option>{catalog.filter(p => !isUnavailable(p) || p.id === profile.owner_id).map(p => <option key={p.id} value={p.id} disabled={isUnavailable(p)}>{p.name || p.id}{p.department ? ` · ${p.department}` : ''}{isUnavailable(p) ? ` · ${employmentNames[p.employment_status!]}` : ''} · {p.id}</option>)}{profile.owner_id && !people.some(p => p.id === profile.owner_id) && <option value={profile.owner_id}>{profile.owner_id}</option>}</select><small>关联后可直接筛选“我的任务”。按人员 ID 匹配，不会因重名误认。</small></label>
          <p className="muted">人员来自已读取的各项目需求；也可在“人员与部门”中补充。名称和关联均只保存在本机。</p>
        </section> : <section className="settings-card preference-card"><header><div className="settings-card-icon purple"><Icon name="board"/></div><div><h2>人员与部门</h2><p>本机跨项目共用，手动维护状态和部门，历史任务保留。</p></div><span className="badge">{visible.length} / {people.length} 人</span></header>
          <p className="contact-help">人员状态与部门归属保存在本机；部门选项和标签颜色来自当前项目需求表。修改后点击“保存设置”。</p>
          <div className="department-source"><span>选项来源：{props.project?.name || '尚未选择项目'} · {props.project?.fields.department || '部门'}</span><button className="button small" disabled={props.busy || !props.project} onClick={() => void props.run('departments_sync', { project: props.project!.id }, '部门选项已更新')}>更新部门选项</button>{departmentError ? <span className="department-source-error" role="status">{departmentError}</span> : !departmentOptions.length && <span>暂无可选部门，请检查字段映射并更新选项。</span>}</div>
          <label>查找人员<input type="search" value={search} onChange={e => setSearch(e.target.value)} placeholder="姓名、部门或人员 ID"/></label>
          <div className="people-settings-filters"><label>部门<select aria-label="按部门筛选人员" value={departmentFilter} onChange={e => setDepartmentFilter(e.target.value)}><option value="">全部部门</option><option value="__empty">未配置部门</option>{departments.map(d => <option key={d} value={d}>{d}</option>)}</select></label><label>状态<select aria-label="按人员状态筛选人员" value={statusFilter} onChange={e => setStatusFilter(e.target.value)}><option value="visible">隐藏离职／暂不使用</option><option value="all">全部状态</option>{Object.entries(employmentNames).map(([id,name]) => <option key={id} value={id}>{name}</option>)}</select></label>{statusFilter === 'visible' && departedCount > 0 && <span className="muted">已隐藏 {departedCount} 名离职／暂不使用人员</span>}</div>
          <div className="people-batchbar"><span>已选 {selectedIds.length} 人</span><select aria-label="批量人员状态" value={batchStatus} onChange={e => setBatchStatus(e.target.value as EmploymentStatus)}>{Object.entries(employmentNames).map(([id,name]) => <option key={id} value={id}>{name}</option>)}</select><button className="button small" disabled={!selectedIds.length} onClick={() => { setPeople(people.map(p => selectedIds.includes(p.id) ? { ...p, employment_status: batchStatus } : p)); setSelectedIds([]); }}>应用状态</button><DepartmentSelect label="批量部门" value={batchDepartment} options={departmentOptions} onChange={setBatchDepartment}/><button className="button small" disabled={!selectedIds.length || !batchDepartment.trim()} onClick={() => { setPeople(people.map(p => selectedIds.includes(p.id) ? { ...p, department: batchDepartment.trim() } : p)); setSelectedIds([]); setBatchDepartment(''); }}>应用部门</button></div>
          <div className="people-settings-list"><div className="people-settings-head"><input type="checkbox" aria-label="选择当前筛选结果" disabled={!visible.length} checked={visible.length > 0 && visible.every(p => selectedIds.includes(p.id))} onChange={e => setSelectedIds(e.target.checked ? visible.map(p => p.id) : [])}/><span>人员</span><span>人员 ID</span><span>默认部门</span><span>人员状态</span></div>{visible.map(p => <div className="person-setting" key={p.id}><input type="checkbox" aria-label={`选择${p.name || p.id}（${p.id}）`} checked={selectedIds.includes(p.id)} onChange={e => setSelectedIds(e.target.checked ? [...selectedIds, p.id] : selectedIds.filter(id => id !== p.id))}/><div><strong>{p.name || p.id}</strong><small title={p.id}>{p.id}</small></div><label><DepartmentSelect label={`${p.name || p.id}的默认部门（${p.id}）`} value={p.department} options={departmentOptions} onChange={value => setPeople(people.map(o => o.id === p.id ? { ...o, department: value } : o))}/></label><select aria-label={`${p.name || p.id}的人员状态（${p.id}）`} value={p.employment_status || 'unknown'} onChange={e => { setPeople(people.map(o => o.id === p.id ? { ...o, employment_status: e.target.value as EmploymentStatus } : o)); setSelectedIds(selectedIds.filter(id => id !== p.id)); }}>{Object.entries(employmentNames).map(([id,name]) => <option key={id} value={id}>{name}</option>)}</select></div>)}{!visible.length && <p className="muted">没有匹配的人员，可调整筛选条件或读取飞书需求。</p>}</div>
          <details className="mapping-details"><summary>补充人员</summary><div className="form-grid"><label>人员 ID<input value={personId} onChange={e => setPersonId(e.target.value)} maxLength={200} placeholder="飞书 open_id / 本地稳定 ID"/></label><label>姓名<input value={personName} onChange={e => setPersonName(e.target.value)} maxLength={200}/></label><label>默认部门<DepartmentSelect label="补充人员默认部门" value={personDepartment} options={departmentOptions} onChange={setPersonDepartment}/></label></div>{addError && <p role="alert">{addError}</p>}<button className="button small" disabled={!personId.trim()} onClick={addPerson}>加入人员列表</button><p className="muted">加入后需保存设置。重名人员以 ID 区分；用于飞书回写时须使用真实 open_id。</p></details>
        </section>}
        <div className="settings-savebar"><span className="muted">{dirty ? '有未保存的设置' : '设置已保存'} · 仅保存在本机</span><div className="button-row"><button className="button" disabled={!dirty || props.busy} onClick={() => load(settings, true)}>放弃修改</button><button className="button primary" disabled={!dirty || stale || props.busy} onClick={() => void save()}>保存设置</button></div></div>
      </>}
    </div>
  </div>;
}
