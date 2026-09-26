const assert = require('node:assert/strict')
const Model = require('../Model.js')
const Preferences = require('../Preferences.js')
const payload = {battery:{present:true,percentage:68,state:'charging',capacity:57,rate:24.6,seconds:2520,cycles:186,threshold:null,count:1},source:'ac',profiles:['balanced'],active:'balanced',defaults:{ac:'balanced',battery:'balanced'},errors:[]}
assert.deepEqual(Model.parsePayload(JSON.stringify(payload)),payload)
for(const field of ['percentage','capacity','rate','cycles','seconds','threshold']) {
  const invalid = JSON.parse(JSON.stringify(payload))
  invalid.battery[field] = 'unknown'
  assert.throws(()=>Model.parsePayload(JSON.stringify(invalid)))
}
assert.throws(()=>Model.parsePayload(JSON.stringify({...payload,active:'performance'})))
assert.throws(()=>Model.parsePayload(JSON.stringify({...payload,errors:[{}]})))
assert.equal(Model.duration(2520),'42 min')
assert.equal(Model.duration(11520),'3 h 12 min')
assert.equal(Model.duration(0),'—')
assert.equal(Model.measurement(null,'W'),'—')
assert.equal(Preferences.value({showPercentage:'true'},'showPercentage'),false)
assert.equal(Preferences.language('system','nb_NO'),'nb')
assert.equal(Preferences.text('Settings','nb'),'Innstillinger')
console.log('Model and preference tests passed')
