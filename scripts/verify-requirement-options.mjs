import assert from 'node:assert/strict';
import { archivedRequirementNames, availableRequirementNames } from '../src/workflowLayout.ts';

const task = (id, module, extra = {}) => ({ id, module, state: 'todo', upstream: [], ...extra });
const source = { record_id: 'remote', scope: 'table', base: {} };
const tasks = [
  task('active', '开发中'),
  task('done', '待验收', { state: 'done' }),
  task('manual', '手动归档', { state: 'done' }),
  task('accepted', '验收归档', { state: 'active', acceptance: '验收通过', source }),
  task('missing', '源记录缺失', { acceptance: '验收通过', source: { ...source, missing: true } }),
];
const columns = [
  { id: 'manual', name: '手动归档', priority: 'high', archived_tasks: ['manual'] },
  { id: 'empty', name: '空需求列', priority: '' },
];
assert.deepEqual([...archivedRequirementNames(tasks, columns)].sort(), ['手动归档', '验收归档']);
const options = availableRequirementNames(tasks, columns);
for (const name of ['开发中', '待验收', '源记录缺失', '空需求列']) assert.ok(options.includes(name));
for (const name of ['手动归档', '验收归档', '']) assert.ok(!options.includes(name));
assert.ok(availableRequirementNames([...tasks, task('new', '手动归档')], columns).includes('手动归档'));
assert.ok(availableRequirementNames(tasks.map(t => t.id === 'manual' ? { ...t, state: 'active' } : t), columns).includes('手动归档'));
console.log('Requirement options: manual/automatic archives hidden, waiting acceptance retained, reopened requirements restored.');
