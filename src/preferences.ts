export type GanttScale = 'week' | 'fortnight' | 'month';
const key = 'larkpm-gantt-scale';

export function readGanttScale(): GanttScale {
  const value = localStorage.getItem(key);
  return value === 'fortnight' || value === 'month' ? value : 'week';
}

export function saveGanttScale(value: GanttScale) {
  localStorage.setItem(key, value);
}
