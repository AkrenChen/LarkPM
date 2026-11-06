import type { Task, WorkflowColumn } from './types';

export type WorkflowSystem = { module: string; stages: string[][] };
export const priorityNames: Record<string, string> = { high: '高', medium: '中', low: '低', '': '未设置' };

export function workflowLayout(tasks: Task[], columns: WorkflowColumn[]): WorkflowSystem[] {
  const names = Array.from(new Set([...tasks.map(t => t.module || ''), ...columns.map(c => c.name)]));
  const weights: Record<string, number> = { high: 0, medium: 1, low: 2, '': 3 };
  names.sort((a, b) => weights[columns.find(c => c.name === a)?.priority || ''] - weights[columns.find(c => c.name === b)?.priority || '']);
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
    const ranks = Array.from(new Set(levels.values())).sort((a, b) => a - b);
    return { module, stages: ranks.map(rank => entries.filter(t => levels.get(t.id) === rank).map(t => t.id)) };
  });
}

export function moveWorkflow(systems: WorkflowSystem[], ids: string[], target: { module: string; index: number; parallel: boolean }): WorkflowSystem[] | null {
  const moving = new Set(ids);
  const dest = systems.find(s => s.module === target.module);
  if (!dest || !moving.size) return null;
  const ordered = systems.flatMap(s => s.stages.flat()).filter(id => moving.has(id));
  const touched = new Set([target.module, ...systems.filter(s => s.stages.flat().some(id => moving.has(id))).map(s => s.module)]);
  const result = systems.filter(s => touched.has(s.module)).map(s => ({ module: s.module, stages: s.stages.map(stage => stage.filter(id => !moving.has(id))).filter(stage => stage.length) }));
  const next = result.find(s => s.module === target.module)!;
  const insertion = dest.stages.slice(0, target.index).filter(stage => stage.some(id => !moving.has(id))).length;
  if (target.parallel) {
    const remaining = dest.stages[target.index]?.filter(id => !moving.has(id));
    if (!remaining?.length) return null;
    next.stages[insertion].push(...ordered);
  } else next.stages.splice(insertion, 0, ordered);
  return result;
}
