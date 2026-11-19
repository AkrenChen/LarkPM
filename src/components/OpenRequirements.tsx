import { useEffect, useRef, useState } from 'react';
import { workflowIds, type WorkflowSystem } from '../workflowLayout';
import type { Task } from '../types';
import { Status } from '../App';
import Icon from './Icon';
import './OpenRequirements.css';

export default function OpenRequirements({ systems, tasks, onClose, onSelect }: {
  systems: WorkflowSystem[]; tasks: Task[]; onClose: () => void; onSelect: (id: string) => void;
}) {
  const [search, setSearch] = useState('');
  const panel = useRef<HTMLElement>(null);
  useEffect(() => {
    const trigger = document.activeElement as HTMLElement | null;
    panel.current?.querySelector<HTMLInputElement>('input')?.focus();
    const key = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.stopPropagation(); onClose(); }
      if (event.key !== 'Tab') return;
      const items = Array.from(panel.current?.querySelectorAll<HTMLElement>('input,button,summary') || []).filter(el => el.getClientRects().length);
      const first = items[0], last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    };
    window.addEventListener('keydown', key);
    return () => { window.removeEventListener('keydown', key); trigger?.focus(); };
  }, [onClose]);
  const byId = new Map(tasks.map(task => [task.id, task]));
  const query = search.trim().toLowerCase();
  const groups = systems.map(system => ({ system, members: workflowIds(system).map(id => byId.get(id)!).filter(Boolean) }))
    .filter(({ system, members }) => !query || (system.module || '未归类').toLowerCase().includes(query) || members.some(task => `${task.title} ${task.owners.map(o => o.name).join(' ')}`.toLowerCase().includes(query)));
  return <div className="modal-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) onClose(); }}>
    <section ref={panel} className="modal open-requirements" role="dialog" aria-modal="true" aria-labelledby="open-requirements-heading">
      <header><h2 id="open-requirements-heading">未结需求 <small>{systems.length} 个</small></h2><button className="icon-button" aria-label="关闭未结需求" onClick={onClose}><Icon name="close"/></button></header>
      <input type="search" aria-label="搜索未结需求" placeholder="搜索需求、任务或处理人" value={search} onChange={event => setSearch(event.target.value)}/>
      <div className="open-requirements-list">{groups.map(({ system, members }) => <details open key={system.module}>
        <summary><strong>{system.module || '未归类'}</strong><small>{members.length} 项</small></summary>
        {members.map(task => <button className="open-task" key={task.id} onClick={() => onSelect(task.id)}>
          <span><strong>{task.title}</strong><small>{task.owners.map(owner => owner.name || owner.id).join('、') || '未分配'}{task.version && ` · ${task.version}`}{task.end && ` · ${task.end}`}</small></span><Status task={task}/>
        </button>)}{!members.length && <p className="muted">暂无任务</p>}
      </details>)}{!groups.length && <p className="empty">没有符合条件的未结需求</p>}</div>
    </section>
  </div>;
}
