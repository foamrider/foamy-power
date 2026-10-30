// Battery and power-profile readings, from Quickshell's UPower and
// PowerProfiles services (no helper process). Pure functions so node can
// test them; QML passes plain objects and the translation functions.

var PROFILES = ["power-saver", "balanced", "performance"]
// UPower device states (same numbers as Quickshell's UPowerDeviceState).
var CHARGING = 1, DISCHARGING = 2, FULLY_CHARGED = 4, PENDING_CHARGE = 5

function finite(value, minimum, maximum) {
  return typeof value === "number" && isFinite(value) && value >= minimum && value <= maximum
}
function number(value, maximum) {
  return finite(value, 0, maximum === undefined ? Number.MAX_VALUE : maximum) ? value : null
}

// A sysfs reading: one non-negative number, or null.
function sysfsNumber(text) {
  var raw = String(text === undefined || text === null ? "" : text).trim()
  if (!/^[0-9]+(\.[0-9]+)?$/.test(raw)) return null
  return number(Number(raw))
}
// UPower native paths must name one local supply, never traverse the filesystem.
function safeNative(native) {
  var name = String(native || "")
  return name !== "" && name !== "." && name !== ".." && name.indexOf("/") < 0 && name.indexOf("\0") < 0 ? name : ""
}

// device: { state, percentage (0-100), rate (W), timeToFull (s) }
function batteryState(device, source, threshold) {
  var state = device.state
  var percentage = number(device.percentage, 100)
  var rate = number(device.rate)
  var fullTime = number(device.timeToFull)
  if (source === "battery" || state === DISCHARGING) return "discharging"
  if (threshold !== null && threshold !== undefined && threshold > 0 && threshold < 100) {
    if (state === PENDING_CHARGE) return "holding"
    if (state === FULLY_CHARGED && percentage !== null && percentage >= threshold - 3) return "holding"
    if (state === CHARGING && percentage !== null && percentage >= threshold - 1
        && ((rate !== null && rate <= 0.2) || (fullTime !== null && fullTime >= 28800)))
      return "holding"
  }
  return ({ 1: "charging", 4: "charged", 5: "connected", 6: "connected" })[state] || "connected"
}

// display: { present, isBattery, percentage (0-100), state, capacity (Wh),
//            rate (W), timeToEmpty, timeToFull }
// packs:   [{ threshold, cycles }] for every present power-supply battery
function normalizeBattery(display, packs, source) {
  if (!display || display.present !== true || display.isBattery !== true) return { present: false }
  packs = packs || []
  var thresholds = packs.map(function(p) { var t = number(p.threshold, 100); return t ? t : null })
  // An aggregate battery must not inherit the first pack's limit or cycle count.
  var threshold = thresholds.length && thresholds.every(function(t) { return t === thresholds[0] }) ? thresholds[0] : null
  var cycles = packs.length === 1 ? number(packs[0].cycles) : null
  var state = batteryState(display, source, threshold)
  return {
    present: true,
    percentage: number(display.percentage, 100),
    state: state,
    capacity: number(display.capacity) || null,
    rate: number(display.rate),
    seconds: number(state === "discharging" ? display.timeToEmpty : display.timeToFull),
    cycles: cycles,
    threshold: threshold,
    count: packs.length
  }
}

// `busctl --json=short get-property … ActiveProfile Profiles` prints two
// JSON lines. Throws when the daemon's reply is unusable.
function parseProfiles(text) {
  var lines = String(text || "").trim().split("\n")
  if (lines.length < 2) throw new Error("Invalid power profiles")
  var active = JSON.parse(lines[0]).data
  var listed = JSON.parse(lines[1]).data
  if (typeof active !== "string" || !Array.isArray(listed)) throw new Error("Invalid power profiles")
  var names = listed.map(function(p) { return p && p.Profile ? p.Profile.data : "" })
  var profiles = PROFILES.filter(function(p) { return names.indexOf(p) >= 0 })
  if (!profiles.length || profiles.indexOf(active) < 0) throw new Error("Invalid power profiles")
  return { profiles: profiles, active: active }
}

// The profile list as power-profiles-daemon offers it: performance only
// when the hardware has one.
function availableProfiles(hasPerformance) {
  return hasPerformance ? PROFILES.slice() : ["power-saver", "balanced"]
}

// What omarchy-powerprofiles-set applies for `source` given the saved file.
function effectiveDefault(saved, source, available) {
  var value = String(saved || "").trim()
  if (available.indexOf(value) >= 0) return value
  return source === "ac" && available.indexOf("performance") >= 0 ? "performance" : "balanced"
}

function statusLabel(state) {
  return { charging: "Charging", discharging: "On battery", holding: "Charge limit", charged: "Fully charged", connected: "Connected" }[state] || "Battery unavailable"
}
function batteryIcon(percentage, state) {
  var charging = ["\u{f089c}", "\u{f0086}", "\u{f0087}", "\u{f0088}", "\u{f089d}", "\u{f0089}", "\u{f089e}", "\u{f008a}", "\u{f008b}", "\u{f0085}"]
  var levels = ["\u{f007a}", "\u{f007b}", "\u{f007c}", "\u{f007d}", "\u{f007e}", "\u{f007f}", "\u{f0080}", "\u{f0081}", "\u{f0082}", "\u{f0079}"]
  if (["charged", "holding", "connected"].indexOf(state) >= 0) return "\u{f17e2}"
  var index = finite(percentage, 0, 100) ? Math.min(9, Math.floor(percentage / 10)) : 0
  return state === "charging" ? charging[index] : levels[index]
}
function profileLabel(profile) {
  return { "power-saver": "Power saver", balanced: "Balanced", performance: "Performance" }[profile] || "Unavailable"
}
// FoamyIcon for the popup header: charging, low/warning, or the charge level.
function headerIcon(battery) {
  if (!battery || !battery.present) return "battery"
  if (battery.state === "charging") return "battery-charging"
  var p = battery.percentage
  if (!finite(p, 0, 100)) return "battery"
  if (battery.state === "discharging" && Math.round(p) <= 10) return "battery-warning"
  return p <= 25 ? "battery-low" : p <= 65 ? "battery-medium" : "battery-full"
}
function profileIcon(profile) {
  return { "power-saver": "leaf", balanced: "scale", performance: "gauge" }[profile] || "gauge"
}

// Localized readings. t(key, values) is FoamyI18n.t; num(value, decimals)
// is FoamyI18n.number (language digits and decimal separator).
function duration(seconds, t, num) {
  if (!finite(seconds, 1, Number.MAX_VALUE)) return "—"
  var minutes = Math.max(1, Math.round(seconds / 60))
  return minutes >= 60
    ? t("%1 h %2 min", [num(Math.floor(minutes / 60), 0), num(minutes % 60, 0)])
    : t("%1 min", [num(minutes, 0)])
}
// key is a catalog unit pattern ("%1 W", "%1 Wh", "%1%", "%1"); one decimal
// at most, none for whole numbers.
function measurement(value, key, t, num) {
  if (value === null || value === undefined || !isFinite(value)) return "—"
  var rounded = Math.round(value * 10) / 10
  return t(key, [num(rounded, rounded === Math.floor(rounded) ? 0 : 1)])
}

if (typeof module !== "undefined") module.exports = {
  PROFILES: PROFILES, sysfsNumber: sysfsNumber, safeNative: safeNative, batteryState: batteryState,
  normalizeBattery: normalizeBattery, parseProfiles: parseProfiles, availableProfiles: availableProfiles,
  effectiveDefault: effectiveDefault, statusLabel: statusLabel, batteryIcon: batteryIcon,
  profileLabel: profileLabel, headerIcon: headerIcon, profileIcon: profileIcon, duration: duration, measurement: measurement
}
