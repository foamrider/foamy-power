pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Services.UPower
import "Model.js" as Model

// Power state for every bar instance (one per monitor on 4.5), read in
// process like Omarchy 4.5's battery service:
//   battery   UPower display device + batteries (signals, no polling); charge
//             limit and cycle count from sysfs, re-read when a panel opens
//   profiles  PowerProfiles change signals, plus one `busctl` read at start,
//             after an action, on a power-source change and on Retry (the
//             daemon may have been down when the shell started)
//   defaults  Omarchy's ac/battery state files, watched
// Actions run power_action.py, once, from here.
QtObject {
  id: root

  // A panel is open somewhere (set by the leader); refreshes sysfs facts.
  property bool demanded: false

  readonly property string source: UPower.onBattery ? "battery" : "ac"
  readonly property var display: UPower.displayDevice
  readonly property bool batteryPresent: !!(display && display.isPresent && display.type === UPowerDeviceType.Battery)
  readonly property real fraction: batteryPresent ? Math.max(0, Math.min(1, display.percentage)) : 0
  readonly property bool ready: !display || display.ready !== false

  // Present power-supply batteries (the display device aggregates them).
  readonly property var packs: {
    var list = UPower.devices ? UPower.devices.values : []
    return list.filter(function(d) { return d && d.type === UPowerDeviceType.Battery && d.powerSupply && d.isPresent })
  }
  property var packFacts: []

  readonly property var battery: Model.normalizeBattery(batteryPresent ? {
    present: true,
    isBattery: true,
    percentage: display.percentage * 100,
    state: display.state,
    capacity: display.energyCapacity,
    rate: display.changeRate,
    timeToEmpty: display.timeToEmpty,
    timeToFull: display.timeToFull
  } : null, packFacts, source)

  property var profiles: []
  property string active: ""
  property bool profilesKnown: false
  property string profilesError: ""
  property bool probePending: false
  property int profileSignals: 0
  property int probeSignals: 0

  readonly property string stateDir: {
    var override = Quickshell.env("OMARCHY_POWERPROFILES_STATE_DIR")
    if (override) return override
    var state = Quickshell.env("XDG_STATE_HOME") || (Quickshell.env("HOME") + "/.local/state")
    return state + "/omarchy/powerprofiles"
  }
  readonly property var defaults: profiles.length ? {
    ac: Model.effectiveDefault(acFile.loadedText, "ac", profiles),
    battery: Model.effectiveDefault(batteryFile.loadedText, "battery", profiles)
  } : ({})

  property string actionError: ""
  readonly property bool busy: actionProcess.running
  readonly property string helperPath: decodeURIComponent(Qt.resolvedUrl("power_action.py").toString().replace(/^file:\/\//, ""))

  function profileName(profile) {
    if (profile === PowerProfile.PowerSaver) return "power-saver"
    if (profile === PowerProfile.Performance) return "performance"
    return "balanced"
  }

  function refreshProfiles() {
    // A read already running may predate the change this refresh is for.
    if (probe.running) { probePending = true; return }
    probePending = false
    probeSignals = profileSignals
    probe.running = true
  }

  function applyProbe(text) {
    try {
      var parsed = Model.parseProfiles(text)
      profiles = parsed.profiles
      // A change signal that arrived during the read is newer than its reply.
      if (probeSignals === profileSignals || !profilesKnown) active = parsed.active
      profilesKnown = true
      profilesError = ""
    } catch (error) {
      profilesKnown = false
      profiles = []
      active = ""
      profilesError = "Power profiles are unavailable. Check power-profiles-daemon."
    }
  }

  function reloadFacts() {
    acFile.reload()
    batteryFile.reload()
    var facts = []
    for (var i = 0; i < factReaders.count; i++) {
      var reader = factReaders.objectAt(i)
      if (reader) facts.push(reader.read())
    }
    packFacts = facts
  }

  function refresh() {
    actionError = ""
    reloadFacts()
    refreshProfiles()
  }

  function setProfile(profile) { runAction(["set", profile]) }
  function setDefault(source, profile) { runAction(["default", source, profile]) }

  function runAction(args) {
    if (actionProcess.running) return
    actionError = ""
    actionProcess.command = ["timeout", "--kill-after=1s", "30s", "python3", helperPath].concat(args)
    actionProcess.running = true
  }

  onDemandedChanged: if (demanded) refresh()
  onPacksChanged: Qt.callLater(reloadFacts)
  Component.onCompleted: { reloadFacts(); refreshProfiles() }

  property Process probe: Process {
    command: ["busctl", "--json=short", "get-property", "net.hadess.PowerProfiles", "/net/hadess/PowerProfiles", "net.hadess.PowerProfiles", "ActiveProfile", "Profiles"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.applyProbe(text)
    }
    onExited: function(code) {
      if (code !== 0) root.applyProbe("")
      // Deferred: the process still reports running while it signals exit.
      if (root.probePending) Qt.callLater(root.refreshProfiles)
    }
  }

  property Process actionProcess: Process {
    stdout: StdioCollector { id: actionOutput; waitForEnd: true }
    onExited: function(code) {
      try {
        var response = JSON.parse(actionOutput.text)
        if (code !== 0 || response.ok !== true)
          root.actionError = response.error && typeof response.error.message === "string" ? response.error.message : "Power action failed. Try again."
      } catch (error) {
        root.actionError = "Power action failed. Try again."
      }
      acFile.reload()
      batteryFile.reload()
      Qt.callLater(root.refreshProfiles)
    }
  }

  property Connections profileWatcher: Connections {
    target: PowerProfiles
    function onProfileChanged() {
      root.profileSignals++
      root.active = root.profileName(PowerProfiles.profile)
      if (!root.profilesKnown) root.refreshProfiles()
    }
    function onHasPerformanceProfileChanged() {
      if (root.profilesKnown) root.profiles = Model.availableProfiles(PowerProfiles.hasPerformanceProfile)
    }
  }

  // Let Omarchy's battery service finish restoring the source default first.
  property Timer transition: Timer {
    interval: 650
    onTriggered: { root.refreshProfiles(); root.reloadFacts() }
  }
  property Connections sourceWatcher: Connections {
    target: UPower
    function onOnBatteryChanged() { root.transition.restart() }
  }

  property FileView acFile: FileView {
    property string loadedText: ""
    path: root.stateDir + "/ac"
    watchChanges: true
    printErrors: false
    onLoaded: loadedText = text()
    onLoadFailed: loadedText = ""
    onFileChanged: reload()
  }
  property FileView batteryFile: FileView {
    property string loadedText: ""
    path: root.stateDir + "/battery"
    watchChanges: true
    printErrors: false
    onLoaded: loadedText = text()
    onLoadFailed: loadedText = ""
    onFileChanged: reload()
  }

  // Charge limit and cycle count per battery, from sysfs (UPower reads the
  // same files; Quickshell does not expose them).
  property Instantiator factReaders: Instantiator {
    model: root.packs
    delegate: QtObject {
      id: reader
      required property var modelData
      readonly property string supply: Model.safeNative(modelData.nativePath)
      function read() {
        if (!supply) return { threshold: null, cycles: null }
        threshold.reload()
        cycles.reload()
        return { threshold: Model.sysfsNumber(threshold.text()), cycles: Model.sysfsNumber(cycles.text()) }
      }
      property FileView threshold: FileView {
        path: reader.supply ? "/sys/class/power_supply/" + reader.supply + "/charge_control_end_threshold" : ""
        blockLoading: true
        printErrors: false
      }
      property FileView cycles: FileView {
        path: reader.supply ? "/sys/class/power_supply/" + reader.supply + "/cycle_count" : ""
        blockLoading: true
        printErrors: false
      }
    }
  }
}
