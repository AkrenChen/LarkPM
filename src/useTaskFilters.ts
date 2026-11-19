import { useEffect, useState } from 'react';

type TaskFilters = { search: string; department: string; owner: string; version: string; showDone: boolean };
const defaults: TaskFilters = { search: '', department: '', owner: '', version: '', showDone: false };
const storageKey = 'larkpm-task-filters';

function readFilters(): Record<string, TaskFilters> {
  try {
    const raw: unknown = JSON.parse(localStorage.getItem(storageKey) || '{}');
    if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return {};
    return Object.fromEntries(Object.entries(raw).map(([key, value]) => {
      const filter = value && typeof value === 'object' ? value : {};
      return [key, { ...Object.fromEntries(['search', 'department', 'owner', 'version'].map(name => [name, typeof filter[name] === 'string' ? filter[name] : ''])), showDone: filter.showDone === true } as TaskFilters];
    }));
  } catch { return {}; }
}

export default function useTaskFilters(projectId: string, view: string) {
  const [memory, setMemory] = useState(readFilters);
  const key = JSON.stringify([projectId, view === 'gantt' ? 'gantt' : 'board']);
  const value = memory[key] || defaults;
  useEffect(() => { localStorage.setItem(storageKey, JSON.stringify(memory)); }, [memory]);
  function change(patch: Partial<TaskFilters>) {
    setMemory(previous => ({ ...previous, [key]: { ...defaults, ...previous[key], ...patch } }));
  }
  return { ...value, setSearch: (search: string) => change({ search }), setDepartment: (department: string) => change({ department }), setOwner: (owner: string) => change({ owner }), setVersion: (version: string) => change({ version }), setShowDone: (showDone: boolean) => change({ showDone }) };
}
