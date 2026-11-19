import { useState } from 'react';
import VersionTargets from './VersionTargets';
import type { Project, Run, Task } from '../types';
import Icon from './Icon';
import './ProjectSummary.css';

export function ProjectLinks({ project, run, busy }: { project: Project; run: Run; busy: boolean }) {
  return <div className="project-source-links">{([['requirements', '需求表'], ['versions', '版本表'], ['tests', '测试表']] as const).map(([kind, label]) => <button key={kind} className="button small" disabled={busy || !(kind === 'requirements' ? project.url : project.sources?.[kind]?.url)} onClick={() => void run('open_project_table', { project: project.id, kind })}><Icon name="link" size={13}/>{label} ↗</button>)}</div>;
}

export default function ProjectSummary({ project, run, busy, tasks }: { project: Project; run: Run; busy: boolean; tasks: Task[] }) {
  const [targetsOpen, setTargetsOpen] = useState(false);
  const cache = project.source_cache?.versions;
  return <section className="project-summary" aria-label="项目线上版本与源表"><div className="project-summary-row"><div className="online-versions" title={cache?.updated_at ? `更新于 ${new Date(cache.updated_at).toLocaleString('zh-CN')}` : '尚未读取版本表'}><span className="online-label">线上版本</span>{([['android', 'Android'], ['ios', 'iOS']] as const).map(([key, label]) => { const version = cache?.online?.[key]; return <span className={`online-version ${key}`} key={key}><span>{label}</span><strong>{version?.version || (project.sources?.versions ? '暂无已过审版本' : '未关联')}</strong></span>; })}<button className="button small" onClick={() => setTargetsOpen(true)}><Icon name="calendar" size={13}/>版本总览</button></div><ProjectLinks project={project} run={run} busy={busy}/></div>
    {!!project.source_refresh?.length && <p className="source-refresh" role="status">{project.source_refresh.map(kind => kind === 'tests' ? '测试排期' : '版本记录').join('、')}后台更新中，当前显示上次结果</p>}
    {cache?.error && <p className="source-error" role="alert">{cache.error}{cache.updated_at ? '；保留上次读取结果' : ''}</p>}
    {targetsOpen && <VersionTargets key={project.id} project={project} tasks={tasks} run={run} busy={busy} onClose={() => setTargetsOpen(false)}/>}
  </section>;
}
