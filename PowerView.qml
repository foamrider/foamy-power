import QtQuick
import QtQuick.Controls as Controls
import QtQuick.Layouts
import qs.Commons
import qs.Commons as Commons
import qs.Ui
import "kit"
import "Model.js" as Model

// The popup body: header, battery ring and readings, power-profile choices
// and battery details on one keyboard/pointer cursor, plus the settings page.
// Data comes in through properties so the preview can feed mock states.
PanelKeyCatcher {
  id: root

  property var battery: null
  property bool ready: true
  property var profiles: []
  property string activeProfile: ""
  property var defaults: ({})
  property var settings: ({})
  property string error: ""
  property bool busy: false
  property bool editingSettings: false
  property bool saving: false
  property string settingsError: ""

  signal settingsRequested()
  signal settingsBack()
  signal closeRequestedByView()
  signal switchPanelRequested(int direction)
  signal profileRequested(string profile)
  signal defaultRequested(string source, string profile)
  signal saveRequested(string key, var value)
  signal retryRequested()

  readonly property bool present: !!(battery && battery.present)
  readonly property string batteryState: present ? battery.state : ""
  readonly property bool flowing: ["charging", "discharging"].indexOf(batteryState) >= 0
  // Cursor stops: profiles, then Retry (when there is an error), then Settings.
  readonly property int retryStop: error !== "" ? profiles.length : -1
  readonly property int settingsStop: profiles.length + (error !== "" ? 1 : 0)

  function t(key, values) { return FoamyI18n.t(key, values) }
  function num(value, decimals) { return FoamyI18n.number(value, decimals) }
  function measure(value, key) { return Model.measurement(value, key, t, num) }
  readonly property string timeText: present ? Model.duration(battery.seconds, t, num) : "—"
  readonly property string statusText: !ready && !present ? t("Reading battery…")
    : present ? t(Model.statusLabel(batteryState)) : t("No battery detected")
  readonly property string timeSummary: {
    if (!present) return ""
    if (batteryState === "charging") return timeText === "—" ? "—" : t("%1 to full", [timeText])
    if (batteryState === "discharging") return timeText === "—" ? "—" : t("%1 left", [timeText])
    if (batteryState === "holding") return t("Holding at %1", [measure(battery.threshold, "%1%")])
    return t("Connected to power")
  }

  function panelOpened() {
    cursor.reset()
    if (editingSettings) settingsPage.focusBack()
    else root.forceActiveFocus()
  }
  function settingsOpened() { settingsPage.resetScroll(); settingsPage.focusBack() }
  function settingsClosed() { root.forceActiveFocus() }
  function activateCursor() {
    var i = cursor.index
    if (i >= 0 && i < profiles.length) { if (!busy) root.profileRequested(profiles[i]) }
    else if (i === retryStop) root.retryRequested()
    else if (i === settingsStop) root.settingsRequested()
  }

  implicitWidth: FoamyStyle.popupWidth
  implicitHeight: editingSettings ? settingsPage.implicitHeight : content.implicitHeight
  blocked: editingSettings

  FoamyCursor { id: cursor; count: root.settingsStop + 1 }

  onMoveRequested: function(dx, dy) { cursor.move(dy !== 0 ? dy : dx) }
  onActivateRequested: root.activateCursor()
  onCloseRequested: root.closeRequestedByView()
  onTabRequested: function(direction) { root.switchPanelRequested(direction) }
  onTextKey: function(text) {
    if (text === "s" || text === "S") root.settingsRequested()
    else if (text === "r" || text === "R") root.retryRequested()
  }

  component Label: Text {
    textFormat: Text.PlainText
    horizontalAlignment: Text.AlignLeft
    color: FoamyPalette.text
    font.family: FoamyStyle.fontFamily
    font.pixelSize: FoamyStyle.font.body
    wrapMode: Text.WordWrap
  }
  component SectionTitle: Label {
    width: parent.width
    color: FoamyPalette.secondaryText
    font.pixelSize: FoamyStyle.font.bodySmall
    font.weight: Font.DemiBold
    Accessible.role: Accessible.Heading
  }
  component Fact: Column {
    property string label: ""
    property string value: ""
    Layout.fillWidth: true
    Layout.preferredWidth: 1
    spacing: FoamyStyle.gapSmall
    Label { width: parent.width; text: parent.label; color: FoamyPalette.secondaryText; font.pixelSize: FoamyStyle.font.bodySmall }
    Label { width: parent.width; text: parent.value; font.pixelSize: FoamyStyle.font.heading }
  }

  Flickable {
    id: list
    visible: !root.editingSettings
    anchors.fill: parent
    contentWidth: width
    contentHeight: content.implicitHeight
    clip: true
    boundsBehavior: Flickable.StopAtBounds
    flickableDirection: Flickable.VerticalFlick
    Controls.ScrollBar.vertical: Controls.ScrollBar { policy: Controls.ScrollBar.AsNeeded }

    Column {
      id: content
      width: list.width
      bottomPadding: FoamyStyle.padding

      FoamyHeader {
        width: parent.width
        iconName: "plug"
        title: root.t("Power")
        meta: root.present ? root.measure(root.battery.percentage, "%1%") + " · " + root.statusText : root.statusText
        settingsHasCursor: cursor.at(root.settingsStop)
        onSettingsClicked: root.settingsRequested()
        onSettingsHovered: function(hovered) { if (hovered) cursor.hover(root.settingsStop) }
      }

      Column {
        x: FoamyStyle.padding
        width: parent.width - FoamyStyle.padding * 2
        spacing: Style.space(22)

        // Ring gauge and the current readings.
        RowLayout {
          visible: root.present
          width: parent.width
          spacing: Style.space(24)
          Item {
            Layout.preferredWidth: Style.space(112)
            Layout.preferredHeight: width
            Canvas {
              id: ring
              anchors.fill: parent
              property real fraction: root.present && root.battery.percentage !== null ? root.battery.percentage / 100 : 0
              property color accent: FoamyPalette.accent
              property color track: FoamyPalette.divider
              onFractionChanged: requestPaint()
              onAccentChanged: requestPaint()
              onTrackChanged: requestPaint()
              onWidthChanged: requestPaint()
              onHeightChanged: requestPaint()
              onPaint: {
                var ctx = getContext("2d"), line = Style.space(6), radius = (Math.min(width, height) - line) / 2
                ctx.reset(); ctx.lineWidth = line; ctx.lineCap = "round"
                ctx.strokeStyle = track; ctx.beginPath(); ctx.arc(width / 2, height / 2, radius, 0, Math.PI * 2); ctx.stroke()
                if (fraction > 0) { ctx.strokeStyle = accent; ctx.beginPath(); ctx.arc(width / 2, height / 2, radius, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * Math.min(1, fraction)); ctx.stroke() }
              }
              Accessible.role: Accessible.ProgressBar
              Accessible.name: root.t("Battery")
              Accessible.description: root.present ? root.measure(root.battery.percentage, "%1%") : ""
            }
            Label {
              anchors.centerIn: parent
              text: root.present && root.battery.percentage !== null ? root.measure(Math.round(root.battery.percentage), "%1%") : "—"
              wrapMode: Text.NoWrap
              font.pixelSize: FoamyStyle.font.displayLarge
              font.weight: Font.DemiBold
            }
          }
          Column {
            Layout.fillWidth: true
            spacing: FoamyStyle.gapSmall
            Label { width: parent.width; text: root.statusText; font.pixelSize: FoamyStyle.font.heading }
            Label { width: parent.width; text: root.timeSummary; color: FoamyPalette.secondaryText; font.pixelSize: FoamyStyle.font.subtitle }
            Label { visible: root.flowing; width: parent.width; text: root.measure(root.battery.rate, "%1 W"); color: FoamyPalette.secondaryText }
          }
        }
        Label {
          visible: !root.present
          width: parent.width
          text: root.statusText
          color: FoamyPalette.mutedText
          font.pixelSize: FoamyStyle.font.bodySmall
        }

        Column {
          width: parent.width
          spacing: FoamyStyle.gap
          SectionTitle { text: root.t("Power profile") }
          RowLayout {
            width: parent.width
            spacing: FoamyStyle.gap
            Repeater {
              model: root.profiles
              FoamyCursorSurface {
                id: profileButton
                required property string modelData
                required property int index
                readonly property bool selected: root.activeProfile === modelData
                Layout.fillWidth: true
                Layout.preferredWidth: 1
                implicitHeight: Style.space(40)
                foreground: FoamyPalette.text
                bordered: true
                current: selected
                hasCursor: cursor.at(index)
                opacity: root.busy ? FoamyStyle.disabledOpacity : 1
                onHovered: cursor.hover(index)
                onClicked: if (!root.busy) root.profileRequested(modelData)
                Accessible.role: Accessible.RadioButton
                Accessible.name: root.t(Model.profileLabel(modelData))
                Accessible.checked: selected
                Row {
                  anchors.centerIn: parent
                  spacing: FoamyStyle.gapSmall
                  FoamyIcon { name: Model.profileIcon(profileButton.modelData); color: FoamyPalette.text; width: FoamyStyle.iconSize; height: width; anchors.verticalCenter: parent.verticalCenter }
                  Label {
                    text: root.t(Model.profileLabel(profileButton.modelData))
                    wrapMode: Text.NoWrap
                    elide: Text.ElideRight
                    width: Math.min(implicitWidth, profileButton.width - FoamyStyle.iconSize - FoamyStyle.gap * 3)
                    font.pixelSize: FoamyStyle.font.bodySmall
                    anchors.verticalCenter: parent.verticalCenter
                  }
                }
              }
            }
          }
          Label { visible: root.profiles.length === 0; width: parent.width; text: root.t("Unavailable"); color: FoamyPalette.mutedText; font.pixelSize: FoamyStyle.font.bodySmall }
        }

        Column {
          visible: root.present
          width: parent.width
          spacing: FoamyStyle.gapLarge
          SectionTitle { text: root.t("Battery details") }
          GridLayout {
            width: parent.width
            columns: 2
            columnSpacing: Style.space(24)
            rowSpacing: FoamyStyle.sectionGap
            Fact { label: root.t("Full capacity"); value: root.present ? root.measure(root.battery.capacity, "%1 Wh") : "—" }
            Fact { label: root.t("Charge cycles"); value: root.present ? root.measure(root.battery.cycles, "%1") : "—" }
            Fact {
              label: root.t(root.batteryState === "charging" ? "Charging at" : root.batteryState === "discharging" ? "Discharging at" : "Battery state")
              value: !root.present ? "—" : root.flowing ? root.measure(root.battery.rate, "%1 W")
                : root.t(root.batteryState === "holding" ? "Holding" : Model.statusLabel(root.batteryState))
            }
            Fact {
              label: root.t(root.batteryState === "holding" ? "Charge limit" : root.batteryState === "discharging" ? "Time left" : "Time to full")
              value: root.batteryState === "holding" ? root.measure(root.battery.threshold, "%1%") : root.flowing ? root.timeText : "—"
            }
          }
          Label {
            visible: root.present && root.battery.count > 1
            width: parent.width
            text: root.t("Cycle counts are per battery; no combined value is available.")
            color: FoamyPalette.mutedText
            font.pixelSize: FoamyStyle.font.bodySmall
          }
        }

        RowLayout {
          visible: root.error !== ""
          width: parent.width
          spacing: FoamyStyle.gap
          Label {
            Layout.fillWidth: true
            text: root.error
            color: Commons.Color.urgent
            font.pixelSize: FoamyStyle.font.bodySmall
            Accessible.role: Accessible.AlertMessage
            Accessible.name: text
          }
          FoamyAction {
            label: root.t("Retry")
            iconName: "refresh-cw"
            foreground: FoamyPalette.secondaryText
            hasCursor: cursor.at(root.retryStop)
            enabled: !root.busy
            onHoveredChanged: if (hovered) cursor.hover(root.retryStop)
            onClicked: root.retryRequested()
          }
        }
      }
    }
  }

  SettingsPane {
    id: settingsPage
    visible: root.editingSettings
    width: parent.width
    height: parent.height
    settings: root.settings
    profiles: root.profiles
    defaults: root.defaults
    saving: root.saving
    error: root.settingsError
    retryable: root.settingsError !== ""
    onBack: root.settingsBack()
    onRetry: root.retryRequested()
    onSave: function(key, value) { root.saveRequested(key, value) }
    onSaveDefault: function(source, profile) { root.defaultRequested(source, profile) }
  }
}
