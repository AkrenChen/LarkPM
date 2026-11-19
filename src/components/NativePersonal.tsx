import { useCallback, useEffect, useRef, useState } from 'react';
import PersonalInlineEditor from './PersonalInlineEditor';
import { errorText, rpc } from '../api';
import type { Quadrant } from '../types';
import ListSelect from './ListSelect';
import Icon from './Icon';

type NativeTask = { id: string; text: string; priority: Quadrant; update_at: number; revision: string; editable: boolean; recurring: boolean; source?: { account: string; id: string } | null; conflict?: { text: string; priority: Quadrant; completed: boolean }; choice?: 'local' | 'remote' };
type NativeSnapshot = { account: string; tasks: NativeTask[]; pending: number; failed: number; sync_error?: string };

export function useNativePersonal(sync: boolean) {
  const [data, setData] = useState<NativeSnapshot>({ account: '', tasks: [], pending: 0, failed: 0 });
  const [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const locked = useRef(false), refreshing = useRef(false), mounted = useRef(true), generation = useRef(0);
  const refresh = useCallback(async () => {
    if (locked.current || refreshing.current) return;
    refreshing.current = true;
    const current = ++generation.current;
    try { const next = await rpc<NativeSnapshot>('personal_native'); if (mounted.current && generation.current === current) { setData(next); setError(next.sync_error || ''); } }
    catch (error) { if (mounted.current && generation.current === current) setError(errorText(error)); }
    finally { refreshing.current = false; }
  }, []);
  useEffect(() => { mounted.current = true; void refresh(); const timer = window.setInterval(() => void refresh(), 8000); return () => { mounted.current = false; window.clearInterval(timer); }; }, [refresh, sync]);
  async function mutate(action: 'save' | 'move' | 'complete' | 'resolve', values: Partial<NativeTask>) {
    if (locked.current) return false;
    locked.current = true; generation.current++; setBusy(true);
    let saved = false;
    try { const note = await rpc<NativeTask & { completed?: boolean }>('personal_native', { action, account: data.account, ...values }); saved = true; if (mounted.current) { setData(previous => ({ ...previous, account: 'local', tasks: note.completed && !note.conflict ? previous.tasks.filter(task => task.id !== note.id) : [note, ...previous.tasks.filter(task => task.id !== note.id)] })); setError(''); } }
    catch (error) { if (mounted.current) setError(errorText(error)); }
    finally { locked.current = false; if (mounted.current) setBusy(false); }
    if (saved) void refresh();
    return saved;
  }
  const change = (task: NativeTask, action: 'save' | 'move' | 'complete' | 'resolve', values: Partial<NativeTask> = {}) => mutate(action, { ...task, ...values });
  const create = (text: string, priority: Quadrant) => mutate('save', { text, priority });
  return { data, error, busy, refresh, change, create };
}

export function NativePersonalCard({ task, names, busy, change }: { task: NativeTask; names: Record<Quadrant, string>; busy: boolean; change: (task: NativeTask, action: 'save' | 'move' | 'complete' | 'resolve', values?: Partial<NativeTask>) => Promise<boolean> }) {
  const [editing, setEditing] = useState(false);
  return <>
    <article className="personal-task" data-native-id={task.id} draggable={!busy && !editing} onDragStart={event => { event.dataTransfer.setData('application/x-linkin-native', task.id); event.dataTransfer.effectAllowed = 'move'; }}>
      <button className="personal-complete" aria-label={`完成独立待办：${task.text}`} disabled={busy || task.recurring} title={task.recurring ? '重复待办请在好用便签中处理' : '完成待办'} onClick={() => void change(task, 'complete')}><Icon name="check" size={12}/></button>
      <div className="personal-task-content">{editing ? <PersonalInlineEditor initial={task.text} label="编辑独立待办内容" onSave={text => change(task, 'save', { text })} onCancel={() => setEditing(false)}/> : <button className="personal-task-title" disabled={!task.editable || busy} title={task.editable ? '编辑独立待办' : '富文本待办请在 LinkinNotes 中编辑'} onClick={() => setEditing(true)}>{task.text}</button>}<div className="personal-task-meta"><span>{task.source ? 'LinkinNotes · 已关联' : '本地待办'}</span></div>{task.conflict && <div className="personal-note-conflict"><span>LinkinNotes：{task.conflict.completed ? '已完成或删除' : `${task.conflict.text} · ${names[task.conflict.priority]}`}</span><div><button disabled={busy || task.conflict.completed} onClick={() => void change(task, 'resolve', { choice: 'local' })}>保留本地</button><button disabled={busy} onClick={() => void change(task, 'resolve', { choice: 'remote' })}>采用 LinkinNotes</button></div></div>}</div>
      <ListSelect className="personal-task-move" aria-label={`移动独立待办：${task.text}`} renderValue={() => '⋯'} value={task.priority} disabled={busy} onChange={event => void change(task, 'move', { priority: event.target.value as Quadrant })}>{Object.entries(names).map(([key, name]) => <option key={key} value={key}>{name}</option>)}</ListSelect>
    </article>
  </>;
}
