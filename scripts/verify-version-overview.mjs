import assert from 'node:assert/strict';
import { versionRows, versionOverviewPatch } from '../src/versionTargets.ts';

const source = (id, platform, submitted = '') => ({ id, platform, submitted, version: 'v1.0.1', status: '', released: '', description: '' });
let project = {
  targets: { 'v1.0.1（双端）': '2026-11-11' },
  source_cache: { versions: { rows: [source('android', '安卓'), source('ios', 'iOS')] } },
  version_overview: [{ id: 'source:android', origin: 'source', submitted: '2026-11-11', description: '投放版本' }],
};
let rows = versionRows(project);
assert.equal(rows.length, 2);
assert.ok(!rows.some(row => row.platform === '双端'));
const stableId = rows.find(row => row.platform === 'Android').id;
for (const date of ['2026-11-12', '2026-11-13', '2026-11-12']) {
  rows = rows.map(row => row.id === stableId ? { ...row, submitted: date } : row);
  project = { ...project, ...versionOverviewPatch(project, rows) };
  rows = versionRows(project);
  assert.equal(rows.length, 2);
  assert.equal(rows.find(row => row.id === stableId).submitted, date);
  assert.equal(rows.find(row => row.id === stableId).description, '投放版本');
  assert.deepEqual(project.targets, {});
}
project.source_cache.versions.rows[0].submitted = '2026-11-10';
assert.equal(versionRows(project).find(row => row.id === stableId).submitted, '2026-11-12');

let legacy = { targets: { 'v1.0.1（双端）': '2026-11-11' }, target_details: { 'v1.0.1（双端）': { description: '旧目标' } } };
rows = versionRows(legacy);
rows[0] = { ...rows[0], submitted: '2026-11-12', platform: 'Android' };
legacy = { ...legacy, ...versionOverviewPatch(legacy, rows) };
assert.equal(versionRows(legacy).length, 1);
assert.equal(versionRows(legacy)[0].platform, 'Android');
assert.equal(versionRows(legacy)[0].description, '旧目标');
legacy = { ...legacy, ...versionOverviewPatch(legacy, []) };
assert.deepEqual(versionRows(legacy), []);

const intentional = { ...project, version_overview: [...project.version_overview, { id: 'local:both', origin: 'local', version: 'v1.0.1', platform: '双端', submitted: '2026-11-11' }] };
assert.ok(versionRows(intentional).some(row => row.id === 'local:both'));
const removed = { ...project, ...versionOverviewPatch(project, versionRows(project).filter(row => row.id !== stableId)) };
assert.ok(removed.version_overview_removed.includes(stableId));
assert.ok(!versionRows(removed).some(row => row.id === stableId));
removed.source_cache.versions.rows[0].submitted = '2026-11-15';
assert.ok(!versionRows(removed).some(row => row.id === stableId));
console.log('Version edit: stable ID and row count, repeated dates, remote refresh, one-time legacy migration, removal and intentional local dual-platform plan passed.');
