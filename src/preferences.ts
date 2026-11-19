export type GanttScale = 'week' | 'fortnight' | 'month';
export type BoardMode = 'horizontal' | 'feed';
export function readBoardMode(): BoardMode {
  return localStorage.getItem('larkpm-board-mode') === 'feed' ? 'feed' : 'horizontal';
}
export function saveBoardMode(value: BoardMode) {
  localStorage.setItem('larkpm-board-mode', value);
}
const key = 'larkpm-gantt-scale';

export function readGanttScale(): GanttScale {
  const value = localStorage.getItem(key);
  return value === 'fortnight' || value === 'month' ? value : 'week';
}

export function saveGanttScale(value: GanttScale) {
  localStorage.setItem(key, value);
}
