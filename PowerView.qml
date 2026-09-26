import QtQuick
import QtQuick.Controls as Controls
import QtQuick.Layouts
import qs.Commons
import "Model.js" as Model
import "Preferences.js" as Preferences

Column {
  id: root
  required property var battery
  required property var profiles
  required property string activeProfile
  property string language: "en"
  property string error: ""
  property bool loading: false
  property bool busy: false
  property alias settingsTarget: settingsButton
  signal settingsRequested()
  signal profileRequested(string profile)
  signal retryRequested()
  function tr(label) { return Preferences.text(label,language) }
  readonly property bool present: !!(battery && battery.present)
  readonly property string batteryState: present ? battery.state : ""
  readonly property string timeText: present ? Model.duration(battery.seconds) : "—"
  readonly property color secondary: Qt.tint(Color.popups.background,Qt.alpha(Color.popups.text,0.7))
  readonly property color heroColor: Qt.tint(Color.popups.background,Qt.alpha(Color.accent,0.075))
  readonly property string statusText: loading && !battery ? tr("Reading battery…") : present ? tr(Model.statusLabel(batteryState)) : battery ? tr("No battery detected") : tr("Battery unavailable")
  readonly property string timeSummary: {
    if (!present) return ""
    if (batteryState === "charging") return timeText === "—" ? "—" : tr("%1 to full").replace("%1",timeText)
    if (batteryState === "discharging") return timeText === "—" ? "—" : tr("%1 left").replace("%1",timeText)
    if (batteryState === "holding") return tr("Holding at %1%").replace("%1",battery.threshold)
    return tr("Connected to power")
  }
  spacing: 0

  Rectangle {
    width:root.width
    height:top.implicitHeight
    color:root.heroColor
    Column {
      id:top
      width:parent.width
      padding:Style.space(20)
      spacing:Style.space(18)
      RowLayout {
        width:parent.width-top.padding*2
        spacing:Style.space(8)
        BatteryIcon { percentage:root.present&&root.battery.percentage!==null?root.battery.percentage:0;state:root.batteryState;color:root.secondary;Layout.preferredWidth:Style.space(16);Layout.preferredHeight:Style.space(16) }
        Label { text:root.tr("Power");font.pixelSize:Style.space(14);Layout.fillWidth:true }
        PowerAction { id:settingsButton;iconName:"settings";Layout.preferredWidth:Style.space(30);Layout.preferredHeight:Style.space(30);foreground:root.secondary;tooltipText:root.tr("Settings");onClicked:root.settingsRequested() }
      }
      RowLayout {
        width:parent.width-top.padding*2
        spacing:Style.space(24)
        Item {
          visible:root.present
          Layout.preferredWidth:Style.space(root.width<Style.space(350)?108:126)
          Layout.preferredHeight:width
          Canvas {
            id:ring
            anchors.fill:parent
            property real fraction:root.present&&root.battery.percentage!==null?root.battery.percentage/100:0
            property color accent:Color.accent
            property color track:Qt.alpha(Color.popups.text,0.13)
            onFractionChanged:requestPaint()
            onAccentChanged:requestPaint()
            onTrackChanged:requestPaint()
            onWidthChanged:requestPaint()
            onHeightChanged:requestPaint()
            onPaint: {
              var ctx=getContext("2d"), line=Style.space(6), radius=(Math.min(width,height)-line)/2
              ctx.reset();ctx.lineWidth=line;ctx.lineCap="round"
              ctx.strokeStyle=track;ctx.beginPath();ctx.arc(width/2,height/2,radius,0,Math.PI*2);ctx.stroke()
              if(fraction>0){ctx.strokeStyle=accent;ctx.beginPath();ctx.arc(width/2,height/2,radius,-Math.PI/2,-Math.PI/2+Math.PI*2*Math.min(1,fraction));ctx.stroke()}
            }
            Accessible.role:Accessible.ProgressBar
            Accessible.name:root.tr("Power")
            Accessible.description:root.present?Model.measurement(root.battery.percentage,"%"):""
          }
          Row {
            anchors.centerIn:parent
            spacing:Style.space(1)
            Label { text:root.present&&root.battery.percentage!==null?Math.round(root.battery.percentage):"—";font.pixelSize:Style.space(40);font.letterSpacing:-1.5 }
            Label { visible:root.present&&root.battery.percentage!==null;text:"%";font.pixelSize:Style.space(18);anchors.bottom:parent.bottom;anchors.bottomMargin:Style.space(6) }
          }
        }
        Column {
          Layout.fillWidth:true
          spacing:Style.space(5)
          RowLayout {
            width:parent.width
            spacing:Style.space(8)
            Item {
              visible:root.present
              Layout.preferredWidth:Style.space(18);Layout.preferredHeight:Style.space(18)
              BatteryIcon { anchors.fill:parent;visible:root.batteryState==="discharging";percentage:root.present&&root.battery.percentage!==null?root.battery.percentage:0;state:root.batteryState;color:root.secondary }
              PowerIcon { anchors.fill:parent;visible:root.batteryState!=="discharging";name:"plug";color:root.secondary }
            }
            Label { text:root.statusText;font.pixelSize:Style.space(17);Layout.fillWidth:true;wrapMode:Text.WordWrap }
          }
          Label { visible:root.present;width:parent.width;text:root.timeSummary;color:root.secondary;font.pixelSize:Style.space(13);wrapMode:Text.WordWrap }
          Label { visible:root.present&&["charging","discharging"].indexOf(root.batteryState)>=0;text:root.present?Model.measurement(root.battery.rate,"W"):"";color:root.secondary }
        }
      }
    }
  }
  Column {
    width:parent.width
    padding:Style.space(20)
    spacing:Style.space(24)
    Column {
      width:parent.width-parent.padding*2
      spacing:Style.space(12)
      SectionTitle { text:root.tr("Power profile") }
      RowLayout {
        width:parent.width
        spacing:Style.space(7)
        Repeater {
          model:root.profiles
          Controls.Button {
            id:profileButton
            required property string modelData
            Layout.fillWidth:true
            Layout.preferredWidth:1
            implicitHeight:Style.space(root.width<Style.space(350)?62:40)
            enabled:!root.busy
            opacity:enabled?1:0.55
            activeFocusOnTab:true
            text:root.tr(Model.profileLabel(modelData))
            Accessible.name:text
            Accessible.role:Accessible.RadioButton
            Accessible.checked:root.activeProfile===modelData
            onClicked:root.profileRequested(modelData)
            background:Rectangle { radius:Style.space(8);color:root.activeProfile===profileButton.modelData||profileButton.hovered?Qt.alpha(Color.accent,0.12):"transparent";border.width:1;border.color:profileButton.activeFocus||root.activeProfile===profileButton.modelData?Color.accent:Qt.alpha(Color.popups.text,0.18) }
            contentItem:Item {
              RowLayout {
                anchors.centerIn:parent
                spacing:Style.space(5)
                PowerIcon { name:profileButton.modelData==="power-saver"?"leaf":profileButton.modelData==="balanced"?"scale":"gauge";color:Color.popups.text;Layout.preferredWidth:Style.space(15);Layout.preferredHeight:Style.space(15) }
                Label { text:profileButton.text;font.pixelSize:Style.space(11);horizontalAlignment:Text.AlignHCenter;wrapMode:Text.WordWrap;Layout.maximumWidth:Math.max(0,parent.parent.width-Style.space(20)) }
              }
            }
          }
        }
      }
      Label { visible:root.profiles.length===0;text:root.tr("Unavailable");color:root.secondary }
    }
    Column {
      visible:root.present
      width:parent.width-parent.padding*2
      spacing:Style.space(14)
      SectionTitle { text:root.tr("Battery details") }
      GridLayout {
        width:parent.width
        columns:2
        columnSpacing:Style.space(24)
        rowSpacing:Style.space(20)
        Fact { label:root.tr("Full capacity");value:root.present?Model.measurement(root.battery.capacity,"Wh"):"—" }
        Fact { label:root.tr("Charge cycles");value:root.present?Model.measurement(root.battery.cycles,""):"—" }
        Fact { label:root.tr(root.batteryState==="charging"?"Charging at":root.batteryState==="discharging"?"Discharging at":"Battery state");value:root.present?["charging","discharging"].indexOf(root.batteryState)>=0?Model.measurement(root.battery.rate,"W"):root.tr(root.batteryState==="holding"?"Holding":Model.statusLabel(root.batteryState)):"—" }
        Fact { label:root.tr(root.batteryState==="holding"?"Charge limit":root.batteryState==="discharging"?"Time left":"Time to full");value:root.batteryState==="holding"?Model.measurement(root.battery.threshold,"%"):['charging','discharging'].indexOf(root.batteryState)>=0?root.timeText:"—" }
      }
      Label { visible:root.present&&root.battery.count>1;width:parent.width;text:root.tr("Cycle counts are per battery; no combined value is available.");color:root.secondary;font.pixelSize:Style.space(11);wrapMode:Text.WordWrap }
    }
    Column {
      visible:root.error!==""
      width:parent.width-parent.padding*2
      spacing:Style.space(8)
      Label { width:parent.width;text:root.error;color:Color.urgent;wrapMode:Text.WordWrap;Accessible.role:Accessible.AlertMessage }
      PowerAction { label:root.tr("Retry");iconName:"refresh-cw";foreground:root.secondary;enabled:!root.busy&&!root.loading;onClicked:root.retryRequested() }
    }
  }
  component Label:Text { textFormat:Text.PlainText;color:Color.popups.text;font.family:"sans-serif";font.pixelSize:Style.space(13) }
  component SectionTitle:Label { font.pixelSize:Style.space(11);font.letterSpacing:1.2;font.capitalization:Font.AllUppercase;color:root.secondary }
  component Fact:Column {
    property string label:""
    property string value:""
    Layout.fillWidth:true
    Layout.preferredWidth:1
    spacing:Style.space(5)
    Label { width:parent.width;text:parent.label;color:root.secondary;font.pixelSize:Style.space(12);wrapMode:Text.WordWrap }
    Label { width:parent.width;text:parent.value;font.pixelSize:Style.space(16);wrapMode:Text.WordWrap }
  }
}
