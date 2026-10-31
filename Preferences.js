var defaults = {showPercentage:false,showPercentageWhenLow:false}
// foamy-kit FoamyPrefs schema (mirrors manifest.json barWidget.schema).
var fields = [
  {key:"showPercentage",type:"boolean",defaultValue:false},
  {key:"showPercentageWhenLow",type:"boolean",defaultValue:false}
]
function valid(key,value) { return ["showPercentage","showPercentageWhenLow"].indexOf(key)>=0 && typeof value === "boolean" }
function value(settings,key) { return settings && valid(key,settings[key]) ? settings[key] : defaults[key] }
function showBarPercentage(settings,fraction,discharging) {
  // Match Omarchy's warning: the rounded battery level is at most 10% while discharging.
  return value(settings,"showPercentage") && (!value(settings,"showPercentageWhenLow") || (discharging
    && typeof fraction === "number" && isFinite(fraction) && fraction >= 0 && fraction <= 1
    && Math.round(fraction*100) <= 10))
}

if (typeof module !== "undefined") module.exports={defaults:defaults,fields:fields,valid:valid,value:value,showBarPercentage:showBarPercentage}
