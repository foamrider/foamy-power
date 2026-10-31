import QtQuick
import Quickshell.Io
import "Model.js" as Model

// Charge limit and cycle count of one battery, from sysfs (UPower reads the
// same files; Quickshell does not expose them). Values are published from the
// FileViews' load handlers, never read right after reload(): a reload
// completes asynchronously, so text() would still hold the previous reading.
//
//   BatteryFacts { supply: "BAT0"; onUpdated: service.collect() }
//   facts.reload()          // re-read; `updated` fires when each file is done
QtObject {
  id: root

  // UPower native path (one power-supply name); anything else reads nothing.
  property string supply: ""
  property string base: "/sys/class/power_supply"
  readonly property string safeSupply: Model.safeNative(supply)
  property var threshold: null
  property var cycles: null

  signal updated()

  function reload() {
    if (!safeSupply) return
    thresholdFile.reload()
    cyclesFile.reload()
  }

  property FileView thresholdFile: FileView {
    path: root.safeSupply ? root.base + "/" + root.safeSupply + "/charge_control_end_threshold" : ""
    printErrors: false
    onLoaded: { root.threshold = Model.sysfsNumber(text()); root.updated() }
    onLoadFailed: { root.threshold = null; root.updated() }
  }
  property FileView cyclesFile: FileView {
    path: root.safeSupply ? root.base + "/" + root.safeSupply + "/cycle_count" : ""
    printErrors: false
    onLoaded: { root.cycles = Model.sysfsNumber(text()); root.updated() }
    onLoadFailed: { root.cycles = null; root.updated() }
  }
}
