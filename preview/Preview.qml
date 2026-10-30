import QtQuick
import qs.Commons
import qs.Commons as Commons
import "../kit"
import ".." as Power

// Preview states for the foamy-kit preview harness (mock data, no processes).
Item {
  id: preview
  required property QtObject bar
  required property Item anchorItem
  property var previewStates: ["discharging", "charging", "holding", "unavailable", "settings", "bar"]
  property string previewState: "discharging"
  readonly property Item popup: popup

  readonly property var batteries: ({
    discharging: { present: true, percentage: 68, state: "discharging", capacity: 57, rate: 9.4, seconds: 11520, cycles: 186, threshold: null, count: 1 },
    charging: { present: true, percentage: 41, state: "charging", capacity: 57, rate: 24.6, seconds: 2520, cycles: 186, threshold: null, count: 1 },
    holding: { present: true, percentage: 80, state: "holding", capacity: 57, rate: 0, seconds: null, cycles: 186, threshold: 80, count: 1 },
    unavailable: { present: true, percentage: 55, state: "connected", capacity: 57, rate: null, seconds: null, cycles: null, threshold: null, count: 2 }
  })
  readonly property bool noProfiles: previewState === "unavailable"

  FoamyPopup {
    id: popup
    anchorItem: preview.anchorItem
    bar: preview.bar
    open: true
    body: Component {
      Item {
        implicitHeight: preview.previewState === "bar" ? barStrip.height : view.implicitHeight
        Power.PowerView {
          id: view
          visible: preview.previewState !== "bar"
          width: parent.width
          height: parent.height
          battery: preview.batteries[preview.previewState] || preview.batteries.discharging
          profiles: preview.noProfiles ? [] : ["power-saver", "balanced", "performance"]
          activeProfile: preview.noProfiles ? "" : "balanced"
          defaults: ({ ac: "performance", battery: "power-saver" })
          settings: ({ showPercentage: true, showPercentageWhenLow: false })
          error: preview.noProfiles ? FoamyI18n.t("Power profiles are unavailable. Check power-profiles-daemon.") : ""
          editingSettings: preview.previewState === "settings"
        }
        // Bar widget: discharging, charging and holding, with the percentage.
        Rectangle {
          id: barStrip
          visible: preview.previewState === "bar"
          width: parent.width
          height: 64
          color: Commons.Color.bar.background
          Row {
            anchors.centerIn: parent
            spacing: 40
            Repeater {
              model: [{ f: 0.68, s: "discharging", p: false }, { f: 0.68, s: "discharging", p: true }, { f: 0.41, s: "charging", p: true }, { f: 0.08, s: "discharging", p: true }, { f: 0.8, s: "connected", p: false }]
              Power.PowerBarContent {
                required property var modelData
                fraction: modelData.f
                batteryState: modelData.s
                showPercentage: modelData.p
                foreground: Commons.Color.bar.text
              }
            }
          }
        }
      }
    }
  }
}
