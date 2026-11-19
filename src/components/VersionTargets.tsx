import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import type { Project, Run, Task, VersionOverviewRow } from '../types';
import { platformName, versionOverviewPatch, versionRows } from '../versionTargets';
import Icon from './Icon';
import ListSelect from './ListSelect';
import './VersionTargets.css';

export default function VersionTargets({ project, run, busy, onClose }: { project: Project; tasks: Task[]; run: Run; busy: boolean; onClose: () => void }) {
  const [base, setBase] = useState(() => versionRows(project)), [rows, setRows] = useState(() => versionRows(project));
  const [error, setError] = useState('');
  const [context, setContext] = useState<{ id: string; x: number; y: number } | null>(null);
  const menu = useRef<HTMLDivElement>(null);
  const panel = useRef<HTMLElement>(null), trigger = useRef(document.activeElement as HTMLElement | null), close = useRef(onClose);
  const dirty = JSON.stringify(base) !== JSON.stringify(rows);
  const sourceKey = JSON.stringify(versionRows(project));
  const stale = sourceKey !== JSON.stringify(base);
  useEffect(() => {
    if (!context) return;
    menu.current?.querySelector('button')?.focus();
    const dismiss = () => setContext(null);
    const key = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.stopImmediatePropagation(); event.preventDefault(); dismiss(); }
    };
    document.addEventListener('click', dismiss);
    document.addEventListener('keydown', key, true);
    window.addEventListener('resize', dismiss);
    window.addEventListener('scroll', dismiss, true);
    return () => { document.removeEventListener('click', dismiss); document.removeEventListener('keydown', key, true); window.removeEventListener('resize', dismiss); window.removeEventListener('scroll', dismiss, true); };
  }, [context]);
  close.current = onClose;
  function load(next: Project) { const values = versionRows(next); setBase(values); setRows(values); setError(''); }
  useEffect(() => { if (!dirty) load(project); }, [sourceKey]);
  useEffect(() => {
    panel.current?.querySelector('button')?.focus();
    const key = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.stopPropagation(); close.current(); }
      if (event.key !== 'Tab') return;
      const controls = Array.from(panel.current?.querySelectorAll<HTMLElement>('input,textarea,button:not(:disabled)') || []);
      const first = controls[0], last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    };
    window.addEventListener('keydown', key);
    return () => { window.removeEventListener('keydown', key); trigger.current?.focus(); };
  }, []);
  function update(id: string, patch: Partial<VersionOverviewRow>) { setRows(previous => previous.map(row => row.id === id ? { ...row, ...patch } : row)); setError(''); }
  async function save() {
    const cleaned = rows.map(row => ({ ...row, version: row.version.trim(), platform: platformName(row.platform.trim()), description: row.description.trim() }));
    if (cleaned.some(row => !row.version)) { setError('请填写每一行的版本号。'); return; }
    const identities = cleaned.map(row => `${row.version.toLowerCase()}|${row.platform}`);
    if (new Set(identities).size !== identities.length) { setError('同一平台的版本号重复，请合并或修改后保存。'); return; }
    const result = await run<Project>('project_save', { ...project, ...versionOverviewPatch(project, cleaned) }, '版本总览已保存于本地');
    if (result) load(result);
  }
  const cache = project.source_cache?.versions;
  return <div className="modal-backdrop" onMouseDown={event => { if (event.target === event.currentTarget && !busy) onClose(); }}>
    <section className="modal version-overview" ref={panel} role="dialog" aria-modal="true" aria-labelledby="version-overview-heading">
      <header><div><h2 id="version-overview-heading">版本总览</h2><span>按版本倒序 · {rows.length} 个版本</span></div><div className="button-row"><button className="button small" disabled={busy || dirty || !project.sources?.versions} onClick={() => void run('project_sources_refresh', { project: project.id, kinds: ['versions'] }, '版本记录正在后台更新')}>读取版本记录</button><button className="button small" disabled={busy} onClick={() => { setRows(previous => [{ id: `local:${crypto.randomUUID()}`, version: '', platform: '双端', submitted: '', description: '', status: '', origin: 'local' }, ...previous]); }}>新增版本</button><button className="icon-button" aria-label="关闭版本总览" disabled={busy} onClick={onClose}><Icon name="close"/></button></div></header>
      {cache?.error && <p className="source-error" role="alert">{cache.error}；保留上次读取结果</p>}
      {stale && dirty && <div className="banner warning"><span>版本记录已更新，当前输入保留。</span><button className="button small" onClick={() => load(project)}>重新载入</button></div>}
      <div className="version-overview-scroll"><table><thead><tr><th>版本号</th><th>平台</th><th>提审时间</th><th>版本目标</th></tr></thead><tbody>{rows.map((row, index) => <tr key={row.id} data-version-id={row.id} onContextMenu={event => { event.preventDefault(); if (!busy) setContext({ id: row.id, x: Math.max(8, Math.min(event.clientX, window.innerWidth - 190)), y: Math.max(8, Math.min(event.clientY, window.innerHeight - 54)) }); }}>
        <td><input aria-label={`版本号 第${index + 1}行`} value={row.version} maxLength={200} placeholder="v1.0.1" disabled={busy} onChange={event => update(row.id, { version: event.target.value })}/>{row.status && <small className="version-source-status">{row.status}</small>}</td>
        <td><ListSelect aria-label={`平台 第${index + 1}行`} value={row.platform} disabled={busy} onChange={event => update(row.id, { platform: event.target.value })}>{Array.from(new Set(['双端', 'Android', 'iOS', row.platform])).map(value => <option value={value} key={value}>{value}</option>)}</ListSelect></td>
        <td><input aria-label={`提审时间 第${index + 1}行`} type="date" value={row.submitted} disabled={busy} onChange={event => update(row.id, { submitted: event.target.value })}/></td>
        <td><textarea aria-label={`版本目标 第${index + 1}行`} rows={2} maxLength={2000} placeholder="填写版本目标" value={row.description} disabled={busy} onChange={event => update(row.id, { description: event.target.value })}/></td>
      </tr>)}</tbody></table>{!rows.length && <p className="version-overview-empty">暂无版本记录，可读取关联表或新增版本。</p>}</div>
      {error && <p className="source-error" role="alert">{error}</p>}
      <footer><span>{dirty ? '有未保存的修改' : '修改已保存'} · 新增与编辑保存在本地</span><div className="button-row"><button className="button small" disabled={!dirty || busy} onClick={() => load(project)}>放弃修改</button><button className="button primary small" disabled={!dirty || busy || stale} onClick={() => void save()}>保存修改</button></div></footer>
    </section>
    {context && createPortal(<div ref={menu} className="version-context-menu" role="menu" aria-label="版本操作" style={{ left: context.x, top: context.y }} onMouseDown={event => event.stopPropagation()}><button type="button" role="menuitem" disabled={busy} onClick={() => { setRows(previous => previous.filter(row => row.id !== context.id)); setContext(null); }}>删除此版本</button></div>, document.body)}
  </div>;
}
