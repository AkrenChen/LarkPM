import ListSelect from './ListSelect';
import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { stateNames, type Run, type State, type Task, type WorkflowColumn } from '../types';
import { priorityNames } from '../workflowLayout';

export function StatusMenu({ task, x, y, run, busy, close }: { task: Task; x: number; y: number; run: Run; busy: boolean; close: () => void }) {
  const menu = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const outside = (e: MouseEvent) => { if (!menu.current?.contains(e.target as Node)) close(); };
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape') { e.stopPropagation(); close(); } };
    menu.current?.querySelector<HTMLButtonElement>('button:not(:disabled)')?.focus();
    document.addEventListener('mousedown', outside); document.addEventListener('keydown', key, true);
    window.addEventListener('resize', close); window.addEventListener('scroll', close, true);
    return () => { document.removeEventListener('mousedown', outside); document.removeEventListener('keydown', key, true); window.removeEventListener('resize', close); window.removeEventListener('scroll', close, true); };
  }, [close]);
  return createPortal(<div ref={menu} className="workflow-menu" role="dialog" aria-label="快捷流转状态" style={{ left: Math.max(8, Math.min(x, window.innerWidth - 210)), top: Math.max(8, Math.min(y, window.innerHeight - 245)) }}>
    {Object.entries(stateNames).map(([state, name]) => <button key={state} disabled={busy || state === task.state || state === 'active' && task.blocked_by.length > 0} title={state === 'active' && task.blocked_by.length ? '先完成上游或调整依赖' : ''} onClick={() => void run('edit', { id: task.id, revision: task.revision, patch: { state: state as State } }, '状态已保存').then(result => { if (result) close(); })}>{name}{state === task.state && ' ✓'}</button>)}
    {task.blocked_by.length > 0 && <small>上游未完成，禁止新开始</small>}
  </div>, document.body);
}

export function ColumnEditor({ column, previousName, project, run, busy, close }: { column?: WorkflowColumn; previousName?: string; project: string; run: Run; busy: boolean; close: () => void }) {
  const [name, setName] = useState(column?.name || previousName || ''), [priority, setPriority] = useState(column?.priority || '');
  const [error, setError] = useState('');
  const panel = useRef<HTMLElement>(null), trigger = useRef(document.activeElement as HTMLElement | null);
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !busy) { e.stopPropagation(); close(); }
      if (e.key === 'Tab') {
        const items = Array.from(panel.current?.querySelectorAll<HTMLElement>('input,select,button:not(:disabled)') || []);
        const first = items[0], last = items[items.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus(); }
      }
    };
    window.addEventListener('keydown', key); return () => { window.removeEventListener('keydown', key); trigger.current?.focus(); };
  }, [close, busy]);
  return <div className="modal-backdrop" onMouseDown={e => { if (e.target === e.currentTarget && !busy) close(); }}><section ref={panel} className="modal" role="dialog" aria-modal="true" aria-label={column || previousName != null ? '编辑需求列' : '新建需求列'}><header><h2>{column || previousName != null ? '编辑需求列' : '新建需求列'}</h2><button disabled={busy} aria-label="关闭需求列编辑" onClick={close}>×</button></header><form onSubmit={e => { e.preventDefault(); setError(''); void run('workflow_column_save', { project, id: column?.id, previous_name: previousName, name, priority }, '需求列已保存').then(result => { if (result) close(); else setError('保存未成功，请检查名称是否重复并重试。'); }); }}>{error && <div className="banner error" role="alert">{error}</div>}<label>需求列名称<input autoFocus required maxLength={100} value={name} onChange={e => setName(e.target.value)}/></label><label>优先级<ListSelect aria-label="优先级" value={priority} onChange={e => setPriority(e.target.value)}>{Object.entries(priorityNames).map(([id, title]) => <option key={id} value={id}>{title}</option>)}</ListSelect></label><div className="button-row right"><button type="button" className="button" disabled={busy} onClick={close}>取消</button><button className="button primary" disabled={busy || !name.trim()}>保存需求列</button></div></form></section></div>;
}
