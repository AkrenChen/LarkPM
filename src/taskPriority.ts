import type { Task } from './types';

export function orderParallelTasks(tasks: Task[], options: string[] = ['高', '中', '低']): Task[] {
  const groups = new Map<string, Task[]>();
  const status = (task: Task) => task.state === 'todo' ? `${task.state}:${task.readiness}` : task.state;
  const rank = (task: Task) => task.priority ? options.indexOf(task.priority) : -1;
  for (const task of tasks) { const key = status(task); if (!groups.has(key)) groups.set(key, []); groups.get(key)!.push(task); }
  for (const group of groups.values()) group.sort((a, b) => (rank(a) < 0 ? options.length : rank(a)) - (rank(b) < 0 ? options.length : rank(b)));
  const offsets = new Map<string, number>();
  return tasks.map(task => { const key = status(task), index = offsets.get(key) || 0; offsets.set(key, index + 1); return groups.get(key)![index]; });
}
