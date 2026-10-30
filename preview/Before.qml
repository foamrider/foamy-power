import QtQuick
import qs.Commons
import qs.Commons as Commons
import ".." as Dev

// The dev-branch UI for the --trio "Before" column (rendered from origin/dev).
Item {
  id: preview
  required property QtObject bar
  required property Item anchorItem
  property var previewStates: ["discharging", "charging", "holding", "unavailable", "settings"]
  property string previewState: "charging"
  readonly property Item popup: popup

  readonly property var batteries: ({
    discharging: { present: true, percentage: 68, state: "discharging", capacity: 57, rate: 9.4, seconds: 11520, cycles: 186, threshold: null, count: 1 },
    charging: { present: true, percentage: 41, state: "charging", capacity: 57, rate: 24.6, seconds: 2520, cycles: 186, threshold: null, count: 1 },
    holding: { present: true, percentage: 80, state: "holding", capacity: 57, rate: 0, seconds: null, cycles: 186, threshold: 80, count: 1 },
    unavailable: { present: true, percentage: 55, state: "connected", capacity: 57, rate: null, seconds: null, cycles: null, threshold: null, count: 2 }
  })
  readonly property bool settingsState: previewState === "settings"
  readonly property bool noProfiles: previewState === "unavailable"

  Dev.PowerPopup {
    id: popup
    anchorItem: preview.anchorItem; bar: preview.bar; open: true; padding: 0
    borderSpec: Border.flat(Qt.alpha(Commons.Color.popups.text, 0.15), 1)
    contentWidth: popup.fittedContentWidth(Style.space(420))
    contentHeight: popup.fittedContentHeight(preview.settingsState ? pane.implicitHeight : view.implicitHeight)
    Dev.PowerView {
      id: view
      visible: !preview.settingsState
      width: parent.width
      battery: preview.batteries[preview.previewState] || preview.batteries.charging
      profiles: preview.noProfiles ? [] : ["power-saver", "balanced", "performance"]
      activeProfile: preview.noProfiles ? "" : "balanced"
      error: preview.noProfiles ? "Power profiles are unavailable. Check power-profiles-daemon." : ""
    }
    Dev.SettingsPane {
      id: pane
      visible: preview.settingsState
      width: parent.width
      settings: ({ showPercentage: true, showPercentageWhenLow: false })
      profiles: ["power-saver", "balanced", "performance"]
      defaults: ({ ac: "performance", battery: "power-saver" })
    }
  }
}
