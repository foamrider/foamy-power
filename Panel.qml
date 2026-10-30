import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Commons as Commons
import qs.Ui
import "kit"
import "kit/FoamyPrefs.js" as Prefs
import "Preferences.js" as Preferences

Panel {
  id: root
  ipcTarget: "foamy.power"
  manageIpc: false

  readonly property bool vertical: bar && (bar.position === "left" || bar.position === "right")
  readonly property alias popup: popup
  // Saved values that have not reached `settings` yet, so a second save
  // never merges over a stale entry.
  property var savedOverlay: ({})
  readonly property var preferences: Preferences.withOverlay(root.settings || {}, savedOverlay)
  readonly property bool showPercentage: Preferences.value(preferences, "showPercentage")
  readonly property var battery: PowerService.battery
  readonly property string barBatteryState: !PowerService.batteryPresent || PowerService.source === "battery" ? "discharging"
    : battery.state === "charging" ? "charging" : "connected"
  readonly property bool percentageVisible: Preferences.showBarPercentage(preferences, PowerService.fraction, barBatteryState === "discharging")
  readonly property color foreground: bar ? bar.barForeground : Commons.Color.foreground
  property bool editingSettings: false
  property string settingsError: ""
  property var saveQueue: []
  property bool savingCommand: false
  property var lastFailedSave: null
  readonly property bool saving: savingCommand || saveQueue.length > 0
  readonly property string errors: [PowerService.profilesError, PowerService.actionError]
    .filter(function(e) { return e !== "" }).map(function(e) { return FoamyI18n.t(e) }).join("\n")

  visible: PowerService.batteryPresent || opened
  implicitWidth: visible ? button.implicitWidth : 0
  implicitHeight: visible ? button.implicitHeight : 0

  // Once per shell: readings live in PowerService; the leader owns IPC and
  // tells the service when any panel is open.
  FoamyMember { id: member; scope: "power"; demanding: root.opened }
  Binding { target: PowerService; property: "demanded"; value: member.demanded; when: member.isLeader }

  onSettingsChanged: savedOverlay = Preferences.settledOverlay(root.settings || {}, savedOverlay)
  onOpenedChanged: {
    if (opened) Qt.callLater(function() { if (popup.bodyItem) popup.bodyItem.panelOpened() })
    else {
      editingSettings = false
      if (!saving) savedOverlay = ({})
    }
  }

  function openSettings() {
    editingSettings = true
    open()
    Qt.callLater(function() { if (popup.bodyItem) popup.bodyItem.settingsOpened() })
  }
  function closeSettings() {
    editingSettings = false
    Qt.callLater(function() { if (popup.bodyItem) popup.bodyItem.settingsClosed() })
  }
  function retry() {
    settingsError = ""
    if (lastFailedSave) savePreference(lastFailedSave.key, lastFailedSave.value)
    PowerService.refresh()
  }

  // Saves run one at a time; later changes wait (newest value per key).
  function savePreference(key, value) {
    if (!Preferences.valid(key, value)) return
    settingsError = ""
    lastFailedSave = null
    saveQueue = Preferences.enqueue(saveQueue, key, value)
    flushSaves()
  }
  function flushSaves() {
    while (!savingCommand && saveQueue.length > 0) {
      var item = saveQueue[0]
      saveQueue = saveQueue.slice(1)
      var result = Prefs.save(root.bar, root.moduleName, Preferences.fields, root.preferences, item.key, item.value)
      if (!result.ok) { failSave(item, result.error); continue }
      if (!result.changed) continue
      var overlay = Object.assign({}, savedOverlay)
      overlay[item.key] = item.value
      savedOverlay = overlay
      if (result.command.length === 0) continue
      savingCommand = true
      saveProcess.item = item
      saveProcess.command = result.command
      saveProcess.running = true
    }
  }
  function failSave(item, message) {
    var overlay = Object.assign({}, savedOverlay)
    delete overlay[item.key]
    savedOverlay = overlay
    lastFailedSave = item
    settingsError = FoamyI18n.t(message || "Could not save settings.")
  }

  Process {
    id: saveProcess
    property var item: null
    onExited: function(code) {
      root.savingCommand = false
      if (code !== 0) root.failSave(item, "Could not save settings.")
      Qt.callLater(root.flushSaves)
    }
  }

  FoamyIpc {
    target: "foamy.power"
    enabled: member.isLeader
    function open(): void { root.open() }
    function close(): void { root.close() }
    function toggle(): void { root.toggle() }
    function settings(): void { root.openSettings() }
    function refresh(): void { PowerService.refresh() }
    function togglePercentage(): void { root.savePreference("showPercentage", !root.showPercentage) }
  }

  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: ""
    labelVisible: false
    hasVisualContent: true
    fixedWidth: root.vertical ? -1 : Math.max(Style.bar.iconSlot, barContent.implicitWidth + Style.bar.iconSlot - Style.bar.iconCanvas)
    tooltipText: ""
    PowerBarContent {
      id: barContent
      anchors.centerIn: parent
      fraction: PowerService.fraction
      batteryState: root.barBatteryState
      showPercentage: root.percentageVisible && !root.vertical
      foreground: root.foreground
      fontFamily: button.fontFamily
      fontSize: button.fontSize
    }
    onPressed: function(b) { if (b === Qt.RightButton) root.savePreference("showPercentage", !root.showPercentage); else root.toggle() }
  }

  FoamyPopup {
    id: popup
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    body: Component {
      PowerView {
        battery: PowerService.battery
        ready: PowerService.ready
        profiles: PowerService.profiles
        activeProfile: PowerService.active
        defaults: PowerService.defaults
        settings: root.preferences
        error: root.errors
        busy: PowerService.busy
        editingSettings: root.editingSettings
        saving: root.saving || PowerService.busy
        settingsError: [root.settingsError, root.errors].filter(function(e) { return e !== "" }).join("\n")
        onSettingsRequested: root.openSettings()
        onSettingsBack: root.closeSettings()
        onCloseRequestedByView: root.close()
        onSwitchPanelRequested: function(direction) { root.switchPanel(direction) }
        onProfileRequested: function(profile) { PowerService.setProfile(profile) }
        onDefaultRequested: function(source, profile) { PowerService.setDefault(source, profile) }
        onSaveRequested: function(key, value) { root.savePreference(key, value) }
        onRetryRequested: root.retry()
      }
    }
  }
}
