function finite(value, minimum, maximum) {
  return typeof value === "number" && isFinite(value) && value >= minimum && value <= maximum
}
function parsePayload(raw) {
  var value = JSON.parse(raw)
  if (!value || !Array.isArray(value.profiles) || !Array.isArray(value.errors)
      || !value.defaults || typeof value.defaults !== "object"
      || [null,"ac","battery"].indexOf(value.source) < 0)
    throw new Error("Invalid power status")
  var known = ["power-saver","balanced","performance"]
  if (value.profiles.some(function(p) { return known.indexOf(p) < 0 })
      || typeof value.active !== "string"
      || (value.active !== "" && value.profiles.indexOf(value.active) < 0)
      || value.errors.some(function(e) { return !e || typeof e.code !== "string" || typeof e.message !== "string" }))
    throw new Error("Invalid power profiles")
  for (var key in value.defaults) {
    if (["ac","battery"].indexOf(key) < 0 || known.indexOf(value.defaults[key]) < 0)
      throw new Error("Invalid power defaults")
  }
  var b = value.battery
  if (b !== null) {
    if (!b || typeof b.present !== "boolean") throw new Error("Invalid battery")
    if (b.present) {
      if (["charging","discharging","holding","charged","connected"].indexOf(b.state) < 0)
        throw new Error("Invalid battery state")
      for (var i=0;i<6;i++) {
        var field=["percentage","capacity","rate","seconds","cycles","threshold"][i]
        var max=field === "percentage" || field === "threshold" ? 100 : Number.MAX_VALUE
        if (b[field] !== null && !finite(b[field],0,max)) throw new Error("Invalid battery reading")
      }
      if (!finite(b.count,0,128)) throw new Error("Invalid battery count")
    }
  }
  return value
}
function statusLabel(state) {
  return {charging:"Charging",discharging:"On battery",holding:"Charge limit",charged:"Fully charged",connected:"Connected"}[state] || "Battery unavailable"
}
function profileLabel(profile) {
  return {"power-saver":"Power saver",balanced:"Balanced",performance:"Performance"}[profile] || "Unavailable"
}
function duration(seconds) {
  if (!finite(seconds,1,Number.MAX_VALUE)) return "—"
  var minutes = Math.max(1,Math.round(seconds/60))
  return minutes >= 60 ? Math.floor(minutes/60) + " h " + minutes%60 + " min" : minutes + " min"
}
function measurement(value,unit) { return value === null || value === undefined ? "—" : Number(value.toFixed(1)) + (unit ? " " + unit : "") }
if (typeof module !== "undefined") module.exports={parsePayload:parsePayload,statusLabel:statusLabel,profileLabel:profileLabel,duration:duration,measurement:measurement}
