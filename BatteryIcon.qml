import QtQuick
import "Model.js" as Model

Item {
  id: root
  property real percentage: 0
  property string state: "discharging"
  property color color: "white"
  implicitWidth: 18
  implicitHeight: 18
  Text {
    anchors.fill: parent
    text: Model.batteryIcon(root.percentage,root.state)
    textFormat: Text.PlainText
    color: root.color
    font.family: "Symbols Nerd Font"
    font.pixelSize: root.height
    horizontalAlignment: Text.AlignHCenter
    verticalAlignment: Text.AlignVCenter
  }
}
