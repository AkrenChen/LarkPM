import { useEffect, useRef, useState } from 'react';
import type { Task } from '../types';
import type { WorkflowSystem } from '../workflowLayout';
import Icon from './Icon';
import './ArchivedRequirements.css';

export default function ArchivedRequirements({ systems, tasks, onClose, onCreate, onSelect }: {
  systems: WorkflowSystem[]; tasks: Task[]; onClose: () => void; onCreate: (module: string) => void; onSelect: (id: string) => void;
}) {
  const [search, setSearch] = useState('');
  const panel = useRef<HTMLElement>(null), trigger = useRef(document.activeElement as HTMLElement | null);
  const byId = new Map(tasks.map(task => [task.id, task]));
  useEffect(() => {
    panel.current?.querySelector<HTMLInputElement>('input')?.focus();
    const key = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.stopPropagation(); onClose(); }
      if (event.key !== 'Tab') return;
      const elements = Array.from(panel.current?.querySelectorAll<HTMLElement>('input,button:not(:disabled),summary') || []).filter(el => el.getClientRects().length);
      const first = elements[0], last = elements[elements.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    };
    window.addEventListener('keydown', key);
    return () => { window.removeEventListener('keydown', key); trigger.current?.focus(); };
  }, [onClose]);
  const filtered = systems.filter(system => (system.module || '未归类').toLowerCase().includes(search.trim().toLowerCase()));
  return <div className="modal-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) onClose(); }}>
    <section ref={panel} className="modal archived-requirements" role="dialog" aria-modal="true" aria-labelledby="archived-requirements-heading">
      <header><h2 id="archived-requirements-heading">已结需求 <span>{systems.length}</span></h2><button className="icon-button" aria-label="关闭已结需求" onClick={onClose}><Icon name="close"/></button></header>
      <label className="archived-search">搜索已结需求<input value={search} onChange={event => setSearch(event.target.value)} placeholder="按需求名称搜索…"/></label>
      <div className="archived-list">{filtered.map(system => <div className="archived-requirement" key={system.module}>
        <details><summary><strong>{system.module || '未归类'}</strong><span>已结</span></summary>
          <div className="archived-task-list">{system.stages.flat().map(id => {
            const task = byId.get(id)!;
            return <button key={id} aria-label={`查看历史任务${task.title}`} onClick={() => onSelect(id)}><span>{task.title}</span><small>{task.state === 'closed' ? '已关闭' : '已完成'}</small></button>;
          })}</div>
        </details>
        <button className="button small" aria-label={`追加任务到${system.module || '未归类'}`} onClick={() => onCreate(system.module)}><Icon name="plus" size={13}/>追加任务</button>
      </div>)}{!filtered.length && <p className="archived-empty">{search ? '没有匹配的已结需求' : '暂无已结需求'}</p>}</div>
    </section>
  </div>;
}
