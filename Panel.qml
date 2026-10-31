import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Commons as Commons
import qs.Ui
import "kit"
import "Preferences.js" as Preferences

Panel {
  id: root
  ipcTarget: "foamy.power"
  manageIpc: false

  readonly property bool vertical: bar && (bar.position === "left" || bar.position === "right")
  readonly property alias popup: popup
  readonly property alias prefs: prefs
  // Saved values (including ones the shell has not reflected yet).
  readonly property var preferences: prefs.effectiveSettings
  readonly property bool showPercentage: Preferences.value(preferences, "showPercentage")
  readonly property var battery: PowerService.battery
  readonly property string barBatteryState: !PowerService.batteryPresent || PowerService.source === "battery" ? "discharging"
    : battery.state === "charging" ? "charging" : "connected"
  readonly property bool percentageVisible: Preferences.showBarPercentage(preferences, PowerService.fraction, barBatteryState === "discharging")
  readonly property color foreground: bar ? bar.barForeground : Commons.Color.foreground
  readonly property bool editingSettings: settingsState.editing
  readonly property bool saving: prefs.busy
  readonly property string errors: [PowerService.profilesError, PowerService.actionError]
    .filter(function(e) { return e !== "" }).map(function(e) { return FoamyI18n.t(e) }).join("\n")

  visible: PowerService.batteryPresent || opened
  implicitWidth: visible ? button.implicitWidth : 0
  implicitHeight: visible ? button.implicitHeight : 0

  // Once per shell: readings live in PowerService; the leader owns IPC and
  // tells the service when any panel is open.
  FoamyMember { id: member; scope: "power"; demanding: root.opened }
  Binding { target: PowerService; property: "demanded"; value: member.demanded; when: member.isLeader }

  onOpenedChanged: if (opened) Qt.callLater(function() { if (popup.bodyItem) popup.bodyItem.panelOpened() })

  // Settings page state: lands on Settings even when the popup was closed,
  // resets only when the popup closes.
  FoamySettingsState {
    id: settingsState
    panel: root
    onShown: Qt.callLater(function() { if (popup.bodyItem) popup.bodyItem.settingsOpened() })
    onHidden: Qt.callLater(function() { if (popup.bodyItem) popup.bodyItem.settingsClosed() })
  }
  function openSettings() { settingsState.show() }
  function closeSettings() { settingsState.hide() }
  function retry() {
    if (prefs.canRetry) prefs.retry()
    PowerService.refresh()
  }

  // Settings saves: in order, newest value per key, never over a stale entry.
  FoamyPrefsQueue {
    id: prefs
    bar: root.bar
    moduleName: root.moduleName
    fields: Preferences.fields
    settings: root.settings || ({})
  }
  function savePreference(key, value) { return prefs.save(key, value) }

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
        settingsError: [prefs.error ? FoamyI18n.t(prefs.error) : "", root.errors].filter(function(e) { return e !== "" }).join("\n")
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
