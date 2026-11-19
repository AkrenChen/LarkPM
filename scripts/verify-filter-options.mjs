import assert from 'node:assert/strict';
import { availableFilterOwners, isApprovedFilterVersion } from '../src/filterOptions.ts';

const owners = [{id:'active'}, {id:'resigned'}, {id:'unused'}, {id:'unknown'}, {id:'unlisted'}, {id:'active'}];
const people = ['active','resigned','unused','unknown'].map(id => ({id,employment_status:id}));
assert.deepEqual(availableFilterOwners(owners,people).map(p=>p.id),['active','unknown','unlisted']);
const row = (platform,status='已过审',version='v1.0.1') => ({platform,status,version});
const project = {source_cache:{versions:{rows:[row('安卓'),row('iOS','已提审'),row('安卓','已过审','v1.0.2')]}}};
assert.equal(isApprovedFilterVersion('v1.0.1（安卓）',project),true);
for(const value of ['v1.0.1（双端）','v1.0.1 (iOS)','v1.0.1','v1.0.0（安卓）','v1.0.1-beta（安卓）','待规划']) assert.equal(isApprovedFilterVersion(value,project),false,value);
project.source_cache.versions.rows.push(row('iOS'));
for(const value of ['v1.0.1（双端）','v1.0.1 (iOS)','v1.0.1','1.0.1（Android）']) assert.equal(isApprovedFilterVersion(value,project),true,value);
assert.equal(isApprovedFilterVersion('v1.0.2（双端）',project),false);
assert.equal(isApprovedFilterVersion('v1.0.1（双端）'),false);
assert.equal(isApprovedFilterVersion('v1.0.1（双端）',{source_cache:{versions:{rows:[row('未知平台')]}}}),false);
assert.equal(isApprovedFilterVersion('v1.0.1（双端）',{sources:{versions:{online_value:'上线'}},source_cache:{versions:{rows:[row('双端','上线')]}}}),true);
console.log('Filter options: unavailable people excluded, exact version approval per platform, partial dual-platform retained, unknown status retained.');
