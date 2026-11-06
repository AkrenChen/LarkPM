import { useEffect, useState } from 'react';
import type { Run, Task } from '../types';
import { dateLabel } from '../api';
import { People } from '../App';
import Icon from './Icon';
import './Personal.css';

export default function Personal({ tasks, allTasks, onSelect, run, busy, projectId }: { tasks: Task[]; allTasks: Task[]; onSelect: (id: string) => void; run: Run; busy: boolean; projectId: string }) {
  const [selection, setSelection] = useState<string[]>([]);
  const eligible = tasks.filter(task => !task.linked);
  const eligibleKey = eligible.map(task => task.id).sort().join(',');
  useEffect(() => {
    const ids = new Set(eligibleKey.split(','));
    setSelection(previous => previous.filter(id => ids.has(id)));
  }, [eligibleKey]);
  const chosen = eligible.filter(task => selection.includes(task.id));
  const groups = [
    { name: '进行中', hint: '正在推进的工作', tasks: tasks.filter(t => t.state === 'active'), tone: 'blue' },
    { name: '可开始', hint: '前置条件已满足，等待你开始', tasks: tasks.filter(t => t.state === 'todo' && t.readiness === 'ready'), tone: 'green' },
    { name: '等待上游', hint: '上游交付后可推进', tasks: tasks.filter(t => t.state === 'todo' && t.readiness === 'blocked'), tone: 'amber' },
    { name: '其他状态', hint: '暂停、交付就绪与已关闭', tasks: tasks.filter(t => !['active', 'todo'].includes(t.state)), tone: 'gray' },
  ];
  return <>
    <div className="personal-batchbar"><label><input type="checkbox" aria-label="全选未关联任务" checked={eligible.length > 0 && chosen.length === eligible.length} disabled={busy || !eligible.length} onChange={event => setSelection(event.target.checked ? eligible.map(task => task.id) : [])}/>全选未关联</label><span>已选 {chosen.length} 项</span><button className="button small" disabled={busy || !chosen.length} onClick={() => void run('link_many', { project: projectId, selections: chosen.map(task => ({ id: task.id, revision: task.revision })) }, '所选任务已转为 LinkinNotes 个人待办').then(result => { if (result) setSelection([]); })}><Icon name="link" size={14}/>转为 LinkinNotes</button></div>
    <div className="personal-groups">{groups.filter(group => group.tasks.length || group.name !== '其他状态').map(group => <section key={group.name} className="personal-group">
      <header><span className={`group-dot ${group.tone}`}/><h2>{group.name}</h2><span className="badge">{group.tasks.length}</span><small>{group.hint}</small></header>
      {!group.tasks.length ? <p className="group-empty">暂无工作项</p> : group.tasks.map(task => <article className="task-row" key={task.id}>
        <input className="personal-select" type="checkbox" aria-label={`选择任务：${task.title}`} disabled={busy || task.linked} checked={!task.linked && selection.includes(task.id)} onChange={event => setSelection(previous => event.target.checked ? [...previous, task.id] : previous.filter(id => id !== task.id))}/>
        <button className={`task-check ${task.state === 'done' ? 'checked' : ''}`} aria-label={`${task.state === 'done' ? '取消完成' : '交付就绪'}：${task.title}`} disabled={busy} onClick={() => void run('edit', { id: task.id, revision: task.revision, patch: { state: task.state === 'done' ? task.blocked_by.length ? 'todo' : 'active' : 'done' } }, task.state === 'done' ? '已取消完成，下游就绪状态已重新计算' : '已标记交付就绪')}><Icon name="check" size={13}/></button>
        <button className="task-row-main" onClick={() => onSelect(task.id)}><strong>{task.title}</strong><span>{task.module || '未归类'} {task.version && ` / ${task.version}`}{task.blocked_by.length > 0 && <em>等待：{task.blocked_by.map(id => allTasks.find(t => t.id === id)?.title || '缺失任务').join('、')}</em>}</span></button><People task={task}/><span className="row-date">{dateLabel(task.end)}</span>{task.linked && <span className="personal-linked" title="已关联 LinkinNotes"><Icon name="link" size={14}/></span>}<button className="icon-button" aria-label={`查看${task.title}`} onClick={() => onSelect(task.id)}><Icon name="chevron" size={14}/></button>
      </article>)}
    </section>)}</div>
  </>;
}
