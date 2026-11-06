import type { Task } from '../types';
import './StatusProgress.css';

export default function StatusProgress({ tasks }: { tasks: Task[] }) {
  const paused = tasks.filter(t => t.state === 'paused').length;
  const closed = tasks.filter(t => t.state === 'closed').length;
  const segments = [
    { key: 'paused', label: closed ? `暂停 ${paused} 项／已关闭 ${closed} 项` : `暂停 ${paused} 项`, count: paused + closed },
    { key: 'done', label: `已完成 ${tasks.filter(t => t.state === 'done').length} 项`, count: tasks.filter(t => t.state === 'done').length },
    { key: 'active', label: `进行中 ${tasks.filter(t => t.state === 'active').length} 项`, count: tasks.filter(t => t.state === 'active').length },
    { key: 'todo', label: `未开始 ${tasks.filter(t => t.state === 'todo').length} 项`, count: tasks.filter(t => t.state === 'todo').length },
  ];
  return <section className="status-progress" aria-label="任务进度统计"><div className="status-progress-legend">{segments.map(s => <span key={s.key}><i className={`progress-${s.key}`}/>{s.label}</span>)}<small>共 {tasks.length} 项</small></div><div className="status-progress-track" role="img" aria-label={segments.map(s => s.label).join('，')}>{segments.filter(s => s.count).map(s => <div key={s.key} className={`status-progress-segment progress-${s.key}`} style={{ width: `${s.count / tasks.length * 100}%` }} title={`${s.label}（${Math.round(s.count / tasks.length * 100)}%）`}/>)}</div></section>;
}
