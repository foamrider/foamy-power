const I18n = require('./i18n.cjs');
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
assert.equal(Preferences.value({},'showPercentageWhenLow'),false)
assert.equal(Preferences.value({showPercentageWhenLow:'true'},'showPercentageWhenLow'),false)
assert.equal(Preferences.valid('showPercentageWhenLow',true),true)
assert.equal(Preferences.valid('unknown',true),false)
// The main switch gates both modes; the low-only choice is retained while it is off.
for (const showPercentage of [false,true]) {
  for (const showPercentageWhenLow of [false,true]) {
    for (const fraction of [0,0.1,0.104,0.105,0.5,1]) {
      for (const discharging of [false,true]) {
        assert.equal(Preferences.showBarPercentage({showPercentage,showPercentageWhenLow},fraction,discharging),
          showPercentage && (!showPercentageWhenLow || (discharging && fraction < 0.105)))
      }
    }
  }
}
for (const fraction of [null,undefined,NaN,Infinity,-0.1,1.1,'0.1']) {
  assert.equal(Preferences.showBarPercentage({showPercentage:true,showPercentageWhenLow:true},fraction,true),false)
}
assert.equal(Preferences.showBarPercentage({showPercentageWhenLow:'true'},0.05,true),false)
assert.equal(Preferences.showBarPercentage({showPercentage:true,showPercentageWhenLow:'true'},0.5,true),true)
assert.equal(I18n.text('Show only when battery is low','nb'),'Vis bare ved lavt batterinivå')
const manifest = require('../manifest.json')
assert.deepEqual(manifest.barWidget.defaults,Preferences.defaults)
for (const field of manifest.barWidget.schema) assert.equal(field.defaultValue,Preferences.defaults[field.key])
assert.equal(I18n.text('Settings','nb'),'Innstillinger')
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
