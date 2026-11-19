import { isReleasedTest, latestVersionTarget, versionRows } from '../versionTargets';
import type { GanttScale } from '../preferences';
import { useEffect, useState } from 'react';
import { dateLabel, today } from '../api';
import type { Project, Run, Task } from '../types';
import Icon from './Icon';
import { departmentAccent, departmentStyle } from '../departmentColors';
import './Gantt.css';
import { compareRequirementNames } from '../workflowLayout';

const DAY = 86400000;
const epoch = (date: string) => Date.parse(`${date}T00:00:00Z`);
const label = (time: number) => new Date(time).toISOString().slice(0, 10);

export default function Gantt({ scale, tasks, project, onSelect, run, busy }: { scale: GanttScale; tasks: Task[]; project: Project; onSelect: (id: string) => void; run: Run; busy: boolean }) {
  const unscheduled = tasks.filter(t => (!t.start || !t.end) && !['done', 'closed'].includes(t.state));
  const testCache = project.source_cache?.tests;
  const testRows = testCache?.windows || [];
  const validTests = testRows.filter(t => t.start && t.end && t.end >= t.start);
  const monday = () => { const time = epoch(today()); return time - ((new Date(time).getUTCDay() + 6) % 7) * DAY; };
  const [anchor, setAnchor] = useState(monday), [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  useEffect(() => { setAnchor(monday()); setCollapsed(new Set()); }, [project.id, scale]);
  const monthStart = (time: number) => { const date = new Date(time); return Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), 1); };
  const min = scale === 'month' ? monthStart(anchor) : anchor;
  const max = scale === 'month' ? Date.UTC(new Date(min).getUTCFullYear(), new Date(min).getUTCMonth() + 1, 1) : min + (scale === 'fortnight' ? 14 : 7) * DAY;
  const scheduled = tasks.filter(t => t.start && t.end && epoch(t.start) < max && epoch(t.end) + DAY > min).sort((a, b) => a.start.localeCompare(b.start));
  const days = (max - min) / DAY, rowHeight = 32;
  const scaleNames = { week: '周', fortnight: '双周', month: '月' };
  const shift = (direction: number) => setAnchor(scale === 'month' ? Date.UTC(new Date(min).getUTCFullYear(), new Date(min).getUTCMonth() + direction, 1) : min + direction * days * DAY);
  const toggle = (name: string) => setCollapsed(previous => { const next = new Set(previous); if (next.has(name)) next.delete(name); else next.add(name); return next; });
  const targets = Object.entries(Object.fromEntries(versionRows(project).filter(row => row.submitted).map(row => [`${row.version}（${row.platform}）`, row.submitted])));
  const latest = latestVersionTarget(project);
  const tests = validTests.filter(test => !isReleasedTest(test, project) && epoch(test.start) < max && epoch(test.end) + DAY > min);
  const names = Array.from(new Set(scheduled.map(t => t.module || '未归类')));
  const columns = project.workflow_columns || [];
  names.sort(compareRequirementNames(tasks, columns));
  type Row = { key: string; kind: 'collapsed'; name: string } | { key: string; kind: 'task'; task: Task };
  const rows: Row[] = [];
  const groups = names.map(name => {
    const members = scheduled.filter(t => (t.module || '未归类') === name), start = rows.length;
    if (collapsed.has(name)) rows.push({ key: `group-${name}`, kind: 'collapsed', name });
    else rows.push(...members.map(task => ({ key: task.id, kind: 'task' as const, task })));
    const firstTask = members[0];
    const aggregateStart = members.reduce((value, task) => value < task.start ? value : task.start, firstTask?.start || '');
    const aggregateEnd = members.reduce((value, task) => value > task.end ? value : task.end, firstTask?.end || '');
    const color = project.department_catalog?.options.find(option => option.name === (firstTask?.departments[0] || ''))?.color;
    return { name, start, size: rows.length - start, count: members.length, firstTask, aggregateStart, aggregateEnd, color };
  });
  const percent = (date: string) => (epoch(date) - min) / (days * DAY) * 100;
  const interval = (start: string, end: string) => {
    const left = Math.max(min, epoch(start)), right = Math.min(max, epoch(end) + DAY);
    return right > left ? { left: `${(left - min) / (days * DAY) * 100}%`, width: `${(right - left) / (days * DAY) * 100}%` } : null;
  };
  const visibleTasks = rows.flatMap((row, index) => row.kind === 'task' && interval(row.task.start, row.task.end) ? [{ task: row.task, index }] : []);
  const connections = visibleTasks.flatMap(({ task, index }) => task.upstream.flatMap(id => {
    const parent = visibleTasks.find(item => item.task.id === id);
    if (!parent) return [];
    const x1 = Math.min(100, percent(parent.task.end) + 100 / days), x2 = Math.max(0, percent(task.start));
    const middle = Math.min(99, Math.max(x1 + 1, (x1 + x2) / 2));
    return [{ key: `${id}-${task.id}`, d: `M${x1},${parent.index * rowHeight + 16} H${middle} V${index * rowHeight + 16} H${x2}`, invalid: task.start < parent.task.end }];
  }));

  return <div className="gantt-view">
    <section className="gantt-card weekly-gantt"><header><div className="gantt-heading-targets"><h2>需求排期</h2>{latest && <div className="gantt-current-target" aria-label="最新版本目标"><div className="gantt-target-version"><strong>{latest.version}（{latest.platform}）</strong><span>{latest.submitted ? `提审 ${latest.submitted}` : '提审时间待定'}</span></div><p className="gantt-target-description">{latest.description || '暂未填写版本目标'}</p></div>}</div><div className="gantt-week-navigation" aria-label="甘特周期切换"><button className="button small gantt-page-arrow" aria-label={`上一${scaleNames[scale]}`} onClick={() => shift(-1)}><span className="gantt-previous"><Icon name="chevron" size={14}/></span></button><strong aria-live="polite">{label(min)} — {label(max - DAY)}</strong><button className="button small gantt-page-arrow" aria-label={`下一${scaleNames[scale]}`} onClick={() => shift(1)}><Icon name="chevron" size={14}/></button><button className="button small" onClick={() => setAnchor(scale === 'month' ? monthStart(epoch(today())) : monday())}>本{scaleNames[scale]}</button></div></header>
    <div className="gantt-scroll"><div className="gantt-canvas" style={{ minWidth: 320 + days * (scale === 'month' ? 26 : 50) }}>
    {tests.length > 0 && <div className="gantt-tests" aria-label="本项目测试排期">{tests.map(test => { const position = interval(test.start, test.end); return <div className="gantt-test-row" key={test.id}><div className="gantt-test-name" title={test.title}>测试 · {test.title || test.version || project.name}</div><div className="gantt-test-track">{position && <div className="gantt-test-bar" role="img" aria-label={`测试：${test.title}，${test.start}至${test.end}`} title={`${test.title}\n${test.start} → ${test.end}`} style={position}>测试 {test.version || ''}</div>}</div></div>; })}</div>}
    <div className="gantt-table-head"><div className="gantt-label-column"><span>需求</span><span>任务</span></div><div className="gantt-axis">{Array.from({ length: days }, (_, day) => { const date = new Date(min + day * DAY), weekday = date.getUTCDay(); return <span key={day} style={{ left: `${day / days * 100}%`, width: `${100 / days}%` }} className={weekday === 0 || weekday === 6 ? 'weekend' : ''}>{scale === 'month' ? date.getUTCDate() : dateLabel(label(min + day * DAY))}{scale === 'week' && ` 周${'日一二三四五六'[weekday]}`}</span>; })}</div></div>
    <div className="gantt-body" style={{ height: rows.length * rowHeight }}><div className="gantt-labels" style={{ height: rows.length * rowHeight }}>{rows.map(row => row.kind === 'task' ? <button key={row.key} className="gantt-row-label gantt-task-label" onClick={() => onSelect(row.task.id)}><strong title={row.task.title}>{row.task.title}</strong></button> : <div className="gantt-row-label gantt-collapsed-label" key={row.key}/>)}{groups.map(group => <button key={group.name} className="gantt-merged-requirement" style={{ top: group.start * rowHeight, height: group.size * rowHeight }} aria-label={`需求：${group.name}（${group.count}项）`} aria-expanded={!collapsed.has(group.name)} onClick={() => toggle(group.name)}><span aria-hidden="true">{collapsed.has(group.name) ? '▸' : '▾'}</span><strong title={group.name}>{group.name}</strong><small>{group.count}</small></button>)}</div>
    <div className="gantt-timeline" style={{ height: rows.length * rowHeight }}>{Array.from({ length: days }, (_, day) => <div key={day} className="gantt-grid-line" style={{ left: `${day / days * 100}%` }}/>) }
    {rows.map((row, index) => <div key={row.key} className={`gantt-background-row ${row.kind === 'collapsed' ? 'gantt-group-background' : ''}`} style={{ top: index * rowHeight, height: rowHeight }}/>) }
    {epoch(today()) >= min && epoch(today()) < max && <div className="today-line" style={{ left: `${percent(today())}%` }} title={`今日 ${today()}`}/>}
    {targets.filter(([, date]) => epoch(date) >= min && epoch(date) < max).map(([v, date]) => <div className="target-line" key={v} style={{ left: `${percent(date)}%` }} title={`${v} 目标 ${date}`}><span>{v}</span></div>)}
    <svg className="dependency-lines" width="100%" height={rows.length * rowHeight} viewBox={`0 0 100 ${Math.max(1, rows.length * rowHeight)}`} preserveAspectRatio="none" aria-label="任务依赖连线">{connections.map(c => <path key={c.key} d={c.d} fill="none" stroke={c.invalid ? '#d88e34' : '#a0a6af'} strokeWidth="1" vectorEffect="non-scaling-stroke" strokeDasharray={c.invalid ? '4 3' : undefined}/>)}</svg>
    {rows.map((row, index) => {
      if (row.kind === 'collapsed') {
        const group = groups.find(item => item.start === index);
        const position = group && interval(group.aggregateStart, group.aggregateEnd);
        if (!group || !position) return null;
        return <div key={row.key} className="gantt-requirement-summary-bar" style={{ ...position, top: index * rowHeight + 6, ...departmentStyle(group.color, group.firstTask?.departments[0] || ''), borderColor: departmentAccent(group.color, group.firstTask?.departments[0] || '') }} title={`${group.name}\n${group.aggregateStart} → ${group.aggregateEnd}`} aria-label={`${group.name}总排期，${group.aggregateStart}至${group.aggregateEnd}`} />;
      }
      const position = interval(row.task.start, row.task.end);
      if (!position) return null;
      const task = row.task, department = task.departments[0] || '', color = project.department_catalog?.options.find(option => option.name === department)?.color;
      return <button key={row.key} className={`gantt-bar ${task.state} ${project.targets?.[task.version] && task.end > project.targets[task.version] ? 'over-target' : ''}`} style={{ ...position, top: index * rowHeight + 6, ...departmentStyle(color, department), borderColor: departmentAccent(color, department) }} onClick={() => onSelect(task.id)} title={`${task.title}\n${task.owners.map(owner => owner.name || owner.id).join(' / ')}\n${task.departments.join(' / ')}\n${task.start} → ${task.end}`} aria-label={`${task.title}，${task.start}至${task.end}`}><span>{task.owners.map(owner => owner.name || owner.id).join(' / ') || `${Math.max(1, Math.round((epoch(task.end) - epoch(task.start)) / DAY) + 1)}天`}</span></button>;
    })}</div></div></div></div>
    {!rows.length && <div className="empty"><p>暂无完整排期。为任务填写开始与截止时间后显示。</p></div>}
    <footer>排期条按部门配色；紫色为本项目测试。点击需求名称可折叠任务。</footer>{project.sources?.tests && <div className="gantt-test-note"><button className="text-button" disabled={busy} onClick={() => void run('project_sources_refresh', { project: project.id, kinds: ['tests'] }, '测试排期正在后台更新')}>刷新测试排期</button> · {testCache?.updated_at ? `更新于 ${new Date(testCache.updated_at).toLocaleString('zh-CN')}` : '尚未读取'}{!testRows.length && testCache?.updated_at && ' · 未找到本项目测试排期'}{testRows.length > validTests.length && ` · ${testRows.length - validTests.length} 条日期缺失或倒置，未推测工期`}{testCache?.error && <p className="source-error" role="alert">{testCache.error}；已保留上次结果</p>}</div>}</section>
    <section className="unscheduled"><header><h2>待排期</h2><span className="badge">{unscheduled.length}</span><p>缺少开始或截止时间，不推测工期。</p></header>{unscheduled.length ? <div className="unscheduled-grid">{unscheduled.map(task => <button key={task.id} onClick={() => onSelect(task.id)}><Icon name="calendar" size={16}/><span><strong>{task.title}</strong><small>{task.module || '未归类'} · {task.start ? '缺截止时间' : task.end ? '缺开始时间' : '尚未排期'}</small></span><Icon name="chevron" size={14}/></button>)}</div> : <p className="muted">当前筛选下的工作项均已有排期。</p>}</section>
  </div>;
}
