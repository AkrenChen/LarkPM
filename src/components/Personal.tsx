import { useEffect, useRef, useState, type DragEvent } from 'react';
import type { PersonalBoardConfig, Quadrant, Run, Task } from '../types';
import { dateLabel } from '../api';
import { Status } from '../App';
import ListSelect from './ListSelect';
import Icon from './Icon';
import { NativePersonalCard, useNativePersonal } from './NativePersonal';
import PersonalInlineEditor from './PersonalInlineEditor';
import './Personal.css';

const quadrants: Quadrant[] = ['ui', 'nui', 'uni', 'nuni'];

export default function Personal({ tasks, onSelect, run, busy, projectId, config, ownerId, addRequest }: { tasks: Task[]; allTasks: Task[]; onSelect: (id: string) => void; run: Run; busy: boolean; projectId: string; config: PersonalBoardConfig; ownerId: string; addRequest: number }) {
  const [adding, setAdding] = useState<Quadrant | null>(null), [editing, setEditing] = useState('');
  const previousAdd = useRef(addRequest);
  useEffect(() => { if (previousAdd.current !== addRequest) { setAdding('nuni'); previousAdd.current = addRequest; } }, [addRequest]);
  const [selection, setSelection] = useState<string[]>([]), [dragging, setDragging] = useState(''), [over, setOver] = useState('');
  const inFlight = useRef(false);
  const native = useNativePersonal(config.sync);
  const eligible = tasks.filter(task => !task.linked);
  const eligibleKey = eligible.map(task => task.id).sort().join(',');
  useEffect(() => {
    const ids = new Set(eligibleKey.split(','));
    setSelection(previous => previous.filter(id => ids.has(id)));
  }, [eligibleKey]);
  useEffect(() => { if (projectId && config.sync) void run('personal_prepare', { project: projectId }); }, [projectId, ownerId, config.sync]);
  const chosen = eligible.filter(task => selection.includes(task.id));
  async function move(task: Task, quadrant: Quadrant) {
    if (busy || inFlight.current || (task.personal_quadrant || 'nuni') === quadrant) return;
    inFlight.current = true;
    try { await run('personal_move', { id: task.id, revision: task.revision, quadrant }, config.sync && task.linked ? '象限已更新，已同步到 LinkinNotes' : '象限已保存于本地'); }
    finally { inFlight.current = false; }
  }
  function drop(event: DragEvent, quadrant: Quadrant) {
    event.preventDefault();
    const id = event.dataTransfer.getData('application/x-larkpm-task');
    const nativeId = event.dataTransfer.getData('application/x-linkin-native');
    const nativeTask = native.data.tasks.find(item => item.id === nativeId);
    const task = tasks.find(item => item.id === id);
    setDragging(''); setOver('');
    if (task) void move(task, quadrant);
    if (nativeTask) void native.change(nativeTask, 'move', { priority: quadrant });
  }
  return <>
    <div className="personal-quadrant-toolbar"><span>待办保存在本机 · 拖动分配象限</span><label title="开启后同步独立待办的内容、完成状态及象限。未连接时继续保存在本地，恢复连接后同步。"><input type="checkbox" aria-label="与 LinkinNotes 同步" checked={config.sync} disabled={busy} onChange={event => void run('personal_sync', { enabled: event.target.checked }, event.target.checked ? '已开启 LinkinNotes 同步' : '已关闭同步，待办继续保存在本地')}/>与 LinkinNotes 同步</label></div>
    {native.error && <div className="personal-native-notice" role="status">{native.error}<button className="button small" onClick={() => void native.refresh()}>重试</button></div>}
    {!config.sync && eligible.length > 0 && <div className="personal-batchbar"><label><input type="checkbox" aria-label="全选未关联任务" checked={eligible.length > 0 && chosen.length === eligible.length} disabled={busy} onChange={event => setSelection(event.target.checked ? eligible.map(task => task.id) : [])}/>全选未关联</label><span>已选 {chosen.length} 项</span><button className="button small" disabled={busy || !chosen.length} onClick={() => void run('link_many', { project: projectId, selections: chosen.map(task => ({ id: task.id, revision: task.revision })) }, '所选任务已转为 LinkinNotes 个人待办').then(result => { if (result) setSelection([]); })}><Icon name="link" size={14}/>转为 LinkinNotes</button></div>}
    <div className="personal-quadrants">{quadrants.map((quadrant, index) => {
      const entries = tasks.filter(task => (task.personal_quadrant || 'nuni') === quadrant);
      const nativeEntries = native.data.tasks.filter(task => (task.priority || 'nuni') === quadrant);
      return <section key={quadrant} className={`personal-quadrant quadrant-${quadrant}${over === quadrant ? ' is-drop-target' : ''}`} aria-label={config.names[quadrant]} onDragOver={event => { if (!busy && !native.busy && (dragging || event.dataTransfer.types.includes('application/x-linkin-native'))) { event.preventDefault(); event.dataTransfer.dropEffect = 'move'; setOver(quadrant); } }} onDragLeave={event => { if (!event.currentTarget.contains(event.relatedTarget as Node)) setOver(''); }} onDrop={event => drop(event, quadrant)}>
        <header><span className="personal-quadrant-number">0{index + 1}</span><h2>{config.names[quadrant]}</h2><small>{entries.length + nativeEntries.length}</small><button className="icon-button" aria-label={`在${config.names[quadrant]}新增待办`} disabled={native.busy} onClick={() => setAdding(quadrant)}><Icon name="plus" size={14}/></button></header>
        <div className="personal-quadrant-list">{adding === quadrant && <PersonalInlineEditor label="新增独立待办内容" onSave={text => native.create(text, quadrant)} onCancel={() => setAdding(null)}/>}{entries.map(task => <article key={task.id} data-task-id={task.id} className={`personal-task${dragging === task.id ? ' is-dragging' : ''}`} draggable={!busy && editing !== task.id} onDragStart={event => { setDragging(task.id); event.dataTransfer.setData('application/x-larkpm-task', task.id); event.dataTransfer.effectAllowed = 'move'; }} onDragEnd={() => { setDragging(''); setOver(''); }}>
          {!config.sync && !task.linked && <input className="personal-select" type="checkbox" aria-label={`选择任务：${task.title}`} checked={selection.includes(task.id)} disabled={busy} onChange={event => setSelection(previous => event.target.checked ? [...previous, task.id] : previous.filter(id => id !== task.id))}/>}
          <button className="personal-complete" aria-label={`交付就绪：${task.title}`} disabled={busy} onClick={() => void run('edit', { id: task.id, revision: task.revision, patch: { state: 'done' } }, '已标记交付就绪')}><Icon name="check" size={12}/></button>
          <div className="personal-task-content">{editing === task.id ? <PersonalInlineEditor initial={task.title} label="编辑任务标题" onSave={async title => !!await run('edit', { id: task.id, revision: task.revision, patch: { title } }, '标题已保存')} onCancel={() => setEditing('')}/> : <button className="personal-task-title" disabled={busy} onClick={() => setEditing(task.id)}>{task.title}</button>}<div className="personal-task-meta"><button title="查看需求任务详情" onClick={() => onSelect(task.id)}>{task.module || '未归类'}</button><time>{dateLabel(task.end)}</time><Status task={task}/></div></div>
          <ListSelect className="personal-task-move" aria-label={`移动象限：${task.title}`} renderValue={() => '⋯'} value={quadrant} disabled={busy} onChange={event => void move(task, event.target.value as Quadrant)}>{quadrants.map(key => <option key={key} value={key}>{config.names[key]}</option>)}</ListSelect>
        </article>)}{nativeEntries.map(task => <NativePersonalCard key={task.id} task={task} names={config.names} busy={native.busy} change={native.change}/>)}{!entries.length && !nativeEntries.length && adding !== quadrant && <p className="personal-quadrant-empty">拖入任务或点 ＋ 新增待办</p>}</div>
      </section>;
    })}</div>
  </>;
}
