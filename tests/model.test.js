const I18n = require('./i18n.cjs');
const assert = require('node:assert/strict')
const Model = require('../Model.js')
const Preferences = require('../Preferences.js')
const t=(key,values)=>I18n.text(key,'en',values)
const tNo=(key,values)=>I18n.text(key,'no',values)
const num=(v,d)=>d===undefined?String(v):Number(v).toFixed(d)
const comma=(v,d)=>num(v,d).replace('.',',')
// Units and decimals go through the catalogs and the language's number format.
assert.equal(Model.duration(2520,t,num),'42 min')
assert.equal(Model.duration(11520,t,num),'3 h 12 min')
assert.equal(Model.duration(11520,tNo,num),'3 t 12 min')
assert.equal(Model.duration(0,t,num),'—')
assert.equal(Model.measurement(null,'%1 W',t,num),'—')
assert.equal(Model.measurement(24.63,'%1 W',t,num),'24.6 W')
assert.equal(Model.measurement(24.63,'%1 W',tNo,comma),'24,6 W')
assert.equal(Model.measurement(57,'%1 Wh',t,num),'57 Wh')
assert.equal(Model.measurement(68,'%1%',tNo,num),'68 %')
// Battery readings from UPower device properties (ported from the old helper).
const device=(v={})=>({present:true,isBattery:true,percentage:68,state:1,rate:24.6,capacity:57,timeToFull:2520,timeToEmpty:11520,...v})
for (const charge of [97,98,99,100]) {
  assert.equal(Model.batteryState(device({state:4,percentage:charge}),'ac',100),'charged')
  assert.equal(Model.batteryState(device({state:4,percentage:charge}),'ac',null),'charged')
}
assert.equal(Model.batteryState(device({state:4,percentage:80}),'ac',80),'holding')
assert.equal(Model.batteryState(device({state:5}),'ac',null),'connected')
assert.equal(Model.batteryState(device({percentage:80,rate:null,timeToFull:null}),'ac',80),'charging')
assert.equal(Model.batteryState(device({percentage:80,rate:0.1}),'ac',80),'holding')
assert.equal(Model.batteryState(device({state:4,percentage:80}),'battery',80),'discharging')
let battery=Model.normalizeBattery(device({state:4,percentage:97}),[{threshold:80,cycles:186},{threshold:100,cycles:45}],'ac')
assert.equal(battery.threshold,null); assert.equal(battery.cycles,null); assert.equal(battery.state,'charged'); assert.equal(battery.capacity,57); assert.equal(battery.count,2)
battery=Model.normalizeBattery(device(),[{threshold:null,cycles:186}],'ac')
assert.deepEqual(battery,{present:true,percentage:68,state:'charging',capacity:57,rate:24.6,seconds:2520,cycles:186,threshold:null,count:1})
assert.equal(Model.normalizeBattery(device(),[{}],'battery').seconds,11520)
assert.deepEqual(Model.normalizeBattery(null,[],'ac'),{present:false})
assert.deepEqual(Model.normalizeBattery(device({isBattery:false}),[],'ac'),{present:false})
for (const value of ['', 'x', '-1', '1e3', 'NaN', null, undefined]) assert.equal(Model.sysfsNumber(value),null)
assert.equal(Model.sysfsNumber('186\n'),186)
for (const native of ['', '.', '..', '../../etc', 'a/b']) assert.equal(Model.safeNative(native),'')
assert.equal(Model.safeNative('BAT0'),'BAT0')
// Profiles from busctl (the daemon), never powerprofilesctl.
const reply='{"type":"s","data":"performance"}\n{"type":"aa{sv}","data":[{"Profile":{"type":"s","data":"power-saver"}},{"Profile":{"type":"s","data":"balanced"}},{"Profile":{"type":"s","data":"performance"}}]}\n'
assert.deepEqual(Model.parseProfiles(reply),{profiles:['power-saver','balanced','performance'],active:'performance'})
for (const bad of ['', '{}', '{"type":"s","data":"turbo"}\n{"type":"aa{sv}","data":[]}']) assert.throws(()=>Model.parseProfiles(bad))
assert.deepEqual(Model.availableProfiles(false),['power-saver','balanced'])
// Effective defaults match omarchy-powerprofiles-set.
assert.equal(Model.effectiveDefault('','ac',Model.PROFILES),'performance')
assert.equal(Model.effectiveDefault('','battery',Model.PROFILES),'balanced')
assert.equal(Model.effectiveDefault('performance\n','ac',['power-saver','balanced']),'balanced')
assert.equal(Model.effectiveDefault('power-saver\n','battery',Model.PROFILES),'power-saver')
// Saves queue (newest value per key) and survive a stale entry.
let q=Preferences.enqueue([],'showPercentage',true)
q=Preferences.enqueue(q,'showPercentageWhenLow',true)
q=Preferences.enqueue(q,'showPercentage',false)
assert.deepEqual(q,[{key:'showPercentageWhenLow',value:true},{key:'showPercentage',value:false}])
assert.deepEqual(Preferences.withOverlay({showPercentage:false},{showPercentage:true}),{showPercentage:true})
assert.deepEqual(Preferences.settledOverlay({showPercentage:true},{showPercentage:true}),{})
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
for (const field of Preferences.fields) assert.equal(field.defaultValue,Preferences.defaults[field.key])
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
