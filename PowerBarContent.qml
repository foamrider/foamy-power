import QtQuick
import qs.Commons
import "kit"

// The bar button's content: the battery glyph and, when enabled, the
// percentage in the Omarchy language's digits.
Row {
  id: root

  property real fraction: 0
  property string batteryState: "discharging"
  property bool showPercentage: false
  property color foreground: "white"
  property string fontFamily: Style.font.family
  property real fontSize: Style.font.body

  spacing: Style.space(1)

  BatteryIcon {
    percentage: root.fraction * 100
    state: root.batteryState
    width: Style.bar.iconCanvas
    height: width
    color: root.foreground
    anchors.verticalCenter: parent.verticalCenter
  }
  Text {
    visible: root.showPercentage
    text: FoamyI18n.t("%1%", [FoamyI18n.number(Math.round(root.fraction * 100), 0)])
    textFormat: Text.PlainText
    color: root.foreground
    font.family: root.fontFamily
    font.pixelSize: root.fontSize
    anchors.verticalCenter: parent.verticalCenter
  }
}
