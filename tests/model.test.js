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
const levels = ['󰁺','󰁻','󰁼','󰁽','󰁾','󰁿','󰂀','󰂁','󰂂','󰁹']
const charging = ['󰢜','󰂆','󰂇','󰂈','󰢝','󰂉','󰢞','󰂊','󰂋','󰂅']
for (let i=0;i<10;i++) {
  for (const percentage of [i*10,i*10+9.99]) {
    assert.equal(Model.batteryIcon(percentage,'discharging'),levels[i])
    assert.equal(Model.batteryIcon(percentage,'charging'),charging[i])
  }
}
assert.equal(Model.batteryIcon(100,'charging'),charging[9])
assert.equal(Model.batteryIcon(100,'discharging'),levels[9])
for (const state of ['charged','holding','connected']) assert.equal(Model.batteryIcon(80,state),'󱟢')
assert.equal(Model.batteryIcon(null,'discharging'),levels[0])
console.log('Model and preference tests passed')
