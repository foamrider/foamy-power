// foamy-kit FoamyPrefs schema (mirrors manifest.json barWidget.schema). Every
// read goes through it (kit/FoamyPrefs.js): an invalid value is the default.
var fields = [
  {key:"showPercentage",type:"boolean",defaultValue:false},
  {key:"showPercentageWhenLow",type:"boolean",defaultValue:false}
]
// `values`: Prefs.values(fields, settings), already validated.
function showBarPercentage(values,fraction,discharging) {
  // Match Omarchy's warning: the rounded battery level is at most 10% while discharging.
  return values.showPercentage && (!values.showPercentageWhenLow || (discharging
    && typeof fraction === "number" && isFinite(fraction) && fraction >= 0 && fraction <= 1
    && Math.round(fraction*100) <= 10))
}

if (typeof module !== "undefined") module.exports={fields:fields,showBarPercentage:showBarPercentage}
