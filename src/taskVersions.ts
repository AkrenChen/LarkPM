import type { Project, Task } from './types';

export function taskVersionOptions(project: Project | undefined, tasks: Task[], current = ''): string[] {
  const values = project?.version_catalog?.selectable ? project.version_catalog.options : [current, ...tasks.map(task => task.version)];
  return [...new Set(values.filter(Boolean))];
}
