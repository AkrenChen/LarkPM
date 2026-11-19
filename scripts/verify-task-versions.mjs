import assert from 'node:assert/strict';
import { taskVersionOptions } from '../src/taskVersions.ts';

const tasks = [{ version: 'v1.0.2（安卓）' }, { version: 'v1.0.1（双端）' }, { version: '待规划' }];
const overview = [{ id: 'android', origin: 'local', version: 'v1.0.2', platform: 'Android' }, { id: 'both', origin: 'local', version: 'v1.0.1', platform: '双端' }];
assert.deepEqual(taskVersionOptions({ version_overview: overview }, tasks), ['v1.0.2（安卓）', 'v1.0.1（双端）', '待规划']);
const options = ['v1.0.2（安卓）', 'v1.0.2 (iOS)', 'v1.0.1（双端）', '研发/初审版本', '待规划'];
const project = { version_catalog: { selectable: true, options }, version_overview: overview };
assert.deepEqual(taskVersionOptions(project, tasks, 'obsolete'), options);
assert.deepEqual(taskVersionOptions(project, tasks, 'v1.0.2（安卓）'), options);
assert.deepEqual(taskVersionOptions({ version_catalog: { selectable: true, options: [] } }, tasks), []);
assert.deepEqual(taskVersionOptions({ version_catalog: { selectable: false, options: [] } }, tasks, 'custom'), ['custom', ...tasks.map(t => t.version)]);
console.log('Task version options preserve exact demand-table labels/order, include unused schema options, exclude overview and stale local options.');
