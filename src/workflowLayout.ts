import type { Task, WorkflowColumn } from './types';

export type WorkflowSystem = { module: string; stages: string[][]; branches?: Record<string, string[]> };
export function workflowIds(system: WorkflowSystem): string[] {
  const seen = new Set<string>();
  const visit = (id: string): string[] => { if (seen.has(id)) return []; seen.add(id); return [id, ...(system.branches?.[id] || []).flatMap(visit)]; };
  return system.stages.flatMap(stage => stage.flatMap(visit));
}
export const priorityNames: Record<string, string> = { high: '高', medium: '中', low: '低', '': '未设置' };

export function compareRequirementNames(tasks: Task[], columns: WorkflowColumn[]) {
  const weights: Record<string, number> = { high: 0, medium: 1, low: 2, '': 3 };
  const priorities = new Map(columns.map(column => [column.name, weights[column.priority || '']]));
  const active = new Set(tasks.filter(task => task.state === 'active').map(task => task.module || ''));
  return (a: string, b: string) => (priorities.get(a) ?? 3) - (priorities.get(b) ?? 3) || Number(active.has(b)) - Number(active.has(a));
}

export function archivedRequirementNames(tasks: Task[], columns: WorkflowColumn[]): Set<string> {
  const groups = new Map<string, Task[]>(columns.filter(column => column.name).map(column => [column.name, []]));
  for (const task of tasks) {
    if (!task.module) continue;
    const entries = groups.get(task.module) || [];
    entries.push(task); groups.set(task.module, entries);
  }
  return new Set([...groups].filter(([name, entries]) => {
    const saved = columns.find(column => column.name === name)?.archived_tasks;
    const accepted = entries.length > 0 && entries.every(task => task.acceptance === '验收通过' && !task.source?.missing);
    const manuallyArchived = saved?.length === entries.length && entries.every(task => ['done', 'closed'].includes(task.state) && saved.includes(task.id));
    return accepted || manuallyArchived;
  }).map(([name]) => name));
}

export function availableRequirementNames(tasks: Task[], columns: WorkflowColumn[]): string[] {
  const archived = archivedRequirementNames(tasks, columns);
  return workflowLayout(tasks, columns).map(system => system.module).filter(name => name && !archived.has(name));
}

export function workflowLayout(tasks: Task[], columns: WorkflowColumn[]): WorkflowSystem[] {
  const names = Array.from(new Set([...tasks.map(t => t.module || ''), ...columns.map(c => c.name)]));
  names.sort(compareRequirementNames(tasks, columns));
  return names.map(module => {
    const entries = tasks.filter(t => (t.module || '') === module);
    const byId = new Map(entries.map(t => [t.id, t]));
    const levels = new Map<string, number>();
    const explicitMax = Math.max(-1, ...entries.map(t => t.workflow_stage ?? -1));
    function level(id: string, visiting = new Set<string>()): number {
      if (levels.has(id)) return levels.get(id)!;
      const t = byId.get(id);
      if (!t || visiting.has(id)) return 0;
      if (t.workflow_stage != null) { levels.set(id, t.workflow_stage); return t.workflow_stage; }
      visiting.add(id);
      const parents = t.upstream.filter(i => byId.has(i));
      const rank = Math.max(explicitMax + 1, parents.length ? Math.max(...parents.map(i => level(i, visiting))) + 1 : 0);
      visiting.delete(id); levels.set(id, rank); return rank;
    }
    entries.forEach(t => level(t.id));
    const parents = new Map<string, string>();
    const ordered = [...entries].sort((a,b) => levels.get(a.id)! - levels.get(b.id)!);
    for (const task of ordered) {
      const internal = task.upstream.filter(id => byId.has(id));
      const saved = task.workflow_parent ?? (task.workflow_parent === undefined ? task.branch_of : null);
      if (saved && byId.has(saved) && internal.length === 1 && internal[0] === saved) parents.set(task.id, saved);
    }
    for (const task of ordered) {
      if (parents.has(task.id) || task.workflow_parent !== undefined) continue;
      const internal = task.upstream.filter(id => byId.has(id));
      if (internal.length !== 1) continue;
      const parent = internal[0];
      const peers = entries.filter(other => !parents.has(other.id) && levels.get(other.id) === levels.get(parent));
      if (parents.has(parent) || peers.length > 1 && levels.get(task.id)! > levels.get(parent)!) parents.set(task.id, parent);
    }
    for (const id of parents.keys()) {
      const seen = new Set([id]); let parent = parents.get(id);
      while (parent) { if (seen.has(parent)) { parents.delete(id); break; } seen.add(parent); parent = parents.get(parent); }
    }
    const roots = entries.filter(t => !parents.has(t.id));
    const ranks = Array.from(new Set(roots.map(t => levels.get(t.id)!))).sort((a,b) => a - b);
    const branches: Record<string,string[]> = {};
    for (const task of entries) { const parent = parents.get(task.id); if (parent) (branches[parent] ||= []).push(task.id); }
    return { module, stages: ranks.map(rank => roots.filter(t => levels.get(t.id) === rank).map(t => t.id)), branches };
  });
}

export function moveWorkflow(systems: WorkflowSystem[], ids: string[], target: { module: string; index: number; parallel: boolean; parent?: string }): WorkflowSystem[] | null {
  const moving = new Set(ids);
  const dest = systems.find(s => s.module === target.module);
  if (!dest || !moving.size) return null;
  const allIds = systems.flatMap(workflowIds);
  const parentOf = new Map(systems.flatMap(s => Object.entries(s.branches || {}).flatMap(([parent, children]) => children.map(child => [child,parent] as const))));
  const ordered = allIds.filter(id => moving.has(id) && !hasSelectedParent(id));
  function hasSelectedParent(id: string): boolean { const parent = parentOf.get(id); return !!parent && (moving.has(parent) || hasSelectedParent(parent)); }
  function descendants(id: string) { for (const child of systems.flatMap(s => s.branches?.[id] || [])) { moving.add(child); descendants(child); } }
  ordered.forEach(descendants);
  if (!ordered.length || target.parent && (moving.has(target.parent) || !workflowIds(dest).includes(target.parent))) return null;
  const touched = new Set([target.module, ...systems.filter(s => workflowIds(s).some(id => moving.has(id))).map(s => s.module)]);
  const retainedBranches: Record<string,string[]> = {};
  for (const system of systems) for (const [parent, children] of Object.entries(system.branches || {})) {
    if (moving.has(parent)) retainedBranches[parent] = [...children];
  }
  const result = systems.filter(s => touched.has(s.module)).map(s => ({ module: s.module, stages: s.stages.map(stage => stage.filter(id => !moving.has(id))).filter(stage => stage.length), branches: Object.fromEntries(Object.entries(s.branches || {}).filter(([parent]) => !moving.has(parent)).map(([parent, children]) => [parent, children.filter(id => !moving.has(id))]).filter(([,children]) => children.length)) as Record<string,string[]> }));
  const next = result.find(s => s.module === target.module)!;
  const insertion = dest.stages.slice(0, target.index).filter(stage => stage.some(id => !moving.has(id))).length;
  Object.assign(next.branches, retainedBranches);
  if (target.parent) (next.branches[target.parent] ||= []).push(...ordered);
  else if (target.parallel) {
    const remaining = dest.stages[target.index]?.filter(id => !moving.has(id));
    if (!remaining?.length) return null;
    next.stages[insertion].push(...ordered);
  } else next.stages.splice(insertion, 0, ordered);
  return result;
}
