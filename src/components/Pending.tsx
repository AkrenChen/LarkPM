import { useEffect, useRef, useState } from 'react';
import { formatValue } from '../api';
import { fieldNames, stateNames, type Creation, type State, type Project, type Run, type SyncField, type Task } from '../types';
import LocalCreations, { creationKey } from './LocalCreations';
import Icon from './Icon';
import './Pending.css';

function SelectionBox({ checked, partial, disabled, label, onChange }: { checked: boolean; partial?: boolean; disabled?: boolean; label: string; onChange: (checked: boolean) => void }) {
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => { if (input.current) input.current.indeterminate = !!partial; }, [partial]);
  return <input ref={input} type="checkbox" aria-label={label} checked={checked} disabled={disabled} onChange={event => onChange(event.target.checked)}/>;
}

function ChangeValue({ field, value }: { field: string; value: unknown }) {
  if (field === 'state' && typeof value === 'string' && value in stateNames) return <span className={`status-pill task-status ${value}`}><i/>{stateNames[value as State]}</span>;
  return <span>{formatValue(value)}</span>;
}

export default function Pending({ tasks, creations, ignoredCreations, project, run, busy, onSelect }: { tasks: Task[]; creations: Creation[]; ignoredCreations: Creation[]; project: Project; run: Run; busy: boolean; onSelect: (id: string) => void }) {
  const [selected, setSelected] = useState<Record<string, string[]>>({});
  const [newSelected, setNewSelected] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [parentChoices, setParentChoices] = useState<Record<string, string>>({});
  const dirty = tasks.filter(t => Object.keys(t.pending).length > 0);
  const conflicts = tasks.filter(t => Object.keys(t.conflicts).length > 0);
  const eligible = dirty.filter(t => !t.source?.missing && !Object.keys(t.conflicts).length);
  const selectedFields = eligible.reduce((count, t) => count + (selected[t.id] || []).filter(k => k in t.pending).length, 0);
  const eligibleFields = eligible.reduce((count, task) => count + Object.keys(task.pending).length, 0);
  function selectAll(checked: boolean) { setSelected(checked ? Object.fromEntries(eligible.map(task => [task.id, Object.keys(task.pending)])) : {}); }
  const selections = eligible.map(t => ({ id: t.id, fields: (selected[t.id] || []).filter(k => k in t.pending), revision: t.revision })).filter(s => s.fields.length);
  const toCreate = creations.filter(item => newSelected.includes(creationKey(item)));
  const selectedCount = selections.length + toCreate.length;
  const unresolvedParents = toCreate.some(item => !item.retry && (item.parents?.length || 0) > 1 && (parentChoices[item.module] === undefined || (parentChoices[item.module] !== '' && !item.parents!.some(parent => parent.id === parentChoices[item.module]))));
  async function submit() {
    setSubmitting(true);
    try {
      if (selections.length) {
        const result = await run('write', { project: project.id, selections }, `已回写 ${selections.length} 项修改`);
        if (!result) return;
        setSelected({});
      }
      if (toCreate.length) {
        const result = await run('publish', { project: project.id, creations: toCreate.map(item => ({ kind: item.kind, id: item.id, name: item.title, revision: item.revision, ...(!item.retry && parentChoices[item.module] !== undefined ? { parent_id: parentChoices[item.module] } : {}) })) }, `已创建 ${toCreate.length} 项到飞书`);
        if (result) setNewSelected([]);
      }
    } finally { setSubmitting(false); }
  }
  return <div className="pending-layout"><section className="sync-summary"><div><h2>{dirty.length} 项修改 · {creations.length} 项本地新增</h2><p>{project.name} · {project.table_id || '未连接飞书表'} · 勾选后提交；需求可仅保存在本地，独立便签不上传</p></div><button className="button primary" title={unresolvedParents ? '请先选择同名父需求或仅本地归类' : undefined} disabled={unresolvedParents || busy || submitting || !selectedCount || !project.base_token || !project.table_id} onClick={() => void submit()}><Icon name="check" size={16}/>{busy || submitting ? '正在提交…' : `提交所选${selectedCount ? `（${selectedCount}）` : ''}`}</button></section>
    {creations.length > 0 && <LocalCreations items={creations} selected={newSelected} setSelected={setNewSelected} parentChoices={parentChoices} onParentChange={(module, value) => setParentChoices(previous => ({ ...previous, [module]: value }))} busy={busy || submitting} onSelect={onSelect} onIgnore={item => void run('creation_ignore', { project: project.id, kind: item.kind, id: item.id, ignored: true }, '已忽略，不再提醒')}/>}
    {conflicts.length > 0 && <section className="sync-conflicts"><header className="pending-section-heading"><h2><Icon name="alert" size={15}/>同步冲突</h2><span>{conflicts.length} 项 · 选择保留本地或采用飞书</span></header><div className="pending-table-scroll"><table className="pending-conflict-table"><thead><tr><th>任务</th><th>字段</th><th>本地修改</th><th>飞书最新</th><th>处理</th></tr></thead>{conflicts.map(task => <tbody key={task.id}>{Object.entries(task.conflicts).filter(([, value]) => value).map(([field, value], index, entries) => value && <tr key={field}>{index === 0 && <th rowSpan={entries.length} scope="rowgroup"><button className="task-title-link" title={task.title} onClick={() => onSelect(task.id)}><span>{task.title}</span><Icon name="chevron" size={12}/></button></th>}<th scope="row">{fieldNames[field as SyncField] || field}</th><td title={formatValue(value.local)}><ChangeValue field={field} value={value.local}/></td><td title={formatValue(value.remote)}><ChangeValue field={field} value={value.remote}/></td><td><div className="button-row"><button className="button small" disabled={busy} onClick={() => void run('resolve', { id: task.id, field, choice: 'local', revision: task.revision }, '已保留本地内容，可选择写回')}>保留本地</button><button className="button small" disabled={busy} onClick={() => void run('resolve', { id: task.id, field, choice: 'remote', revision: task.revision }, '已采用飞书内容')}>采用飞书</button></div></td></tr>)}</tbody>)}</table></div></section>}
    {dirty.length > 0 ? <section className="pending-list"><header><h2>待回写明细</h2><span>已选 {selectedFields} 个字段</span><button className="text-button" disabled={busy || !selectedFields} onClick={() => selectAll(false)}>清空选择</button></header><div className="pending-table-scroll"><table className="pending-fields"><thead><tr><th><SelectionBox label="全选可提交字段" checked={eligibleFields > 0 && selectedFields === eligibleFields} partial={selectedFields > 0 && selectedFields < eligibleFields} disabled={busy || !eligibleFields} onChange={selectAll}/></th><th>任务</th><th>变更字段</th><th>飞书基线</th><th>本地修改</th></tr></thead><tbody>{dirty.map(task => {
      const disabled = !!task.source?.missing || !!Object.keys(task.conflicts).length;
      const fields = Object.entries(task.pending).filter(([, value]) => value);
      const chosen = (selected[task.id] || []).filter(field => field in task.pending);
      const reason = task.source?.missing ? '飞书记录不可见' : Object.keys(task.conflicts).length ? '需先解决冲突' : '';
      return <tr className={disabled ? 'disabled' : ''} key={task.id}><td><SelectionBox label={`选择任务：${task.title}`} checked={fields.length > 0 && chosen.length === fields.length} partial={chosen.length > 0 && chosen.length < fields.length} disabled={busy || disabled} onChange={checked => setSelected(previous => ({ ...previous, [task.id]: checked ? fields.map(([field]) => field) : [] }))}/></td><th scope="row"><div className="pending-task-name"><button className="task-title-link" title={`${task.module || '未归类'} · ${task.title}`} onClick={() => onSelect(task.id)}><span>{task.title}</span><Icon name="chevron" size={12}/></button>{reason && <span className="pending-unavailable" title={reason}>需处理</span>}</div></th><td><div className="pending-field-choices">{fields.map(([field]) => <span key={field}>{fieldNames[field as SyncField] || field}</span>)}</div></td>{(['before', 'after'] as const).map(side => <td key={side} title={fields.map(([field, value]) => `${fieldNames[field as SyncField] || field}：${formatValue(value![side])}`).join('；')}><div className="pending-change-values">{fields.map(([field, value]) => <span key={field}>{fields.length > 1 && <small>{fieldNames[field as SyncField] || field}：</small>}<ChangeValue field={field} value={value![side]}/></span>)}</div></td>)}</tr>;
    })}</tbody></table></div></section> : !creations.length && <div className="empty"><Icon name="check" size={34}/><h3>暂时没有待回写修改</h3><p>勾选本地新增可创建到飞书；依赖与独立便签仅保存在本地。</p></div>}
    {ignoredCreations.length > 0 && <details key={ignoredCreations.length} className="ignored-creations"><summary>已忽略 · {ignoredCreations.length}</summary><div>{ignoredCreations.map(item => <div className="ignored-creation" key={creationKey(item)}><span>{item.title}</span><small>{item.kind === 'requirement' ? '父需求' : '任务'}{item.module && item.kind === 'task' ? ` · ${item.module}` : ''}</small><button className="text-button" disabled={busy || submitting} onClick={() => void run('creation_ignore', { project: project.id, kind: item.kind, id: item.id, ignored: false }, '已恢复到待提交列表')}>恢复</button></div>)}</div></details>}
  </div>;
}
