import assert from 'node:assert/strict';
import { orderParallelTasks } from '../src/taskPriority.ts';
const task = (id, state, priority, readiness = 'ready') => ({ id, state, priority, readiness });
const tasks = [task('low','todo','低'),task('active','active','低'),task('high','todo','高'),task('blocked','todo','高','blocked'),task('mid','todo','中'),task('empty','todo','')];
assert.deepEqual(orderParallelTasks(tasks).map(t=>t.id), ['high','active','mid','blocked','low','empty']);
assert.deepEqual(tasks.map(t=>t.id), ['low','active','high','blocked','mid','empty']);
assert.deepEqual(orderParallelTasks([task('a','todo','P1'),task('b','todo','P0')],['P0','P1']).map(t=>t.id), ['b','a']);
console.log('Parallel priority: exact source option order; state/readiness slots preserved; empty last; no dependency mutation passed');
