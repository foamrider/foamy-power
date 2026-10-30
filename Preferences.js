var defaults = {showPercentage:false,showPercentageWhenLow:false}
// foamy-kit FoamyPrefs schema (mirrors manifest.json barWidget.schema).
var fields = [
  {key:"showPercentage",type:"boolean",defaultValue:false},
  {key:"showPercentageWhenLow",type:"boolean",defaultValue:false}
]
// Queue a save: one pending entry per key (the newest value wins), in order.
function enqueue(queue,key,value) {
  return (queue || []).filter(function(item) { return item.key !== key }).concat([{key:key,value:value}])
}
// Settings as last saved by this widget: the shell entry plus values whose
// save succeeded but has not reached `settings` yet.
function withOverlay(settings,overlay) {
  var out = {}
  for (var k in settings || {}) out[k] = settings[k]
  for (var o in overlay || {}) out[o] = overlay[o]
  return out
}
function settledOverlay(settings,overlay) {
  var out = {}, changed = false
  for (var k in overlay || {}) {
    if (settings && JSON.stringify(settings[k]) === JSON.stringify(overlay[k])) changed = true
    else out[k] = overlay[k]
  }
  return changed ? out : overlay
}
function valid(key,value) { return ["showPercentage","showPercentageWhenLow"].indexOf(key)>=0 && typeof value === "boolean" }
function value(settings,key) { return settings && valid(key,settings[key]) ? settings[key] : defaults[key] }
function showBarPercentage(settings,fraction,discharging) {
  // Match Omarchy's warning: the rounded battery level is at most 10% while discharging.
  return value(settings,"showPercentage") && (!value(settings,"showPercentageWhenLow") || (discharging
    && typeof fraction === "number" && isFinite(fraction) && fraction >= 0 && fraction <= 1
    && Math.round(fraction*100) <= 10))
}

if (typeof module !== "undefined") module.exports={defaults:defaults,fields:fields,enqueue:enqueue,withOverlay:withOverlay,settledOverlay:settledOverlay,valid:valid,value:value,showBarPercentage:showBarPercentage}
