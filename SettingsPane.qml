import QtQuick
import QtQuick.Controls as Controls
import QtQuick.Layouts
import qs.Commons
import qs.Ui
import "Model.js" as Model
import "Preferences.js" as Preferences

Column {
  id:root
  required property var settings
  required property var profiles
  required property var defaults
  property string language:"en"
  property bool saving:false
  property string error:""
  property alias backTarget:backButton
  signal back()
  signal save(string key,var value)
  signal saveDefault(string source,string profile)
  signal retry()
  function tr(label){return Preferences.text(label,language)}
  function focusBack(){backButton.forceActiveFocus()}
  readonly property color secondary:Qt.tint(Color.popups.background,Qt.alpha(Color.popups.text,0.7))
  readonly property var profileOptions:profiles.map(function(p){return {value:p,label:root.tr(Model.profileLabel(p))}})
  padding:Style.space(20)
  spacing:Style.space(20)
  RowLayout {
    width:parent.width-root.padding*2
    PowerAction { id:backButton;iconName:"arrow-left";foreground:root.secondary;tooltipText:root.tr("Back");onClicked:root.back() }
    Label { text:root.tr("Settings");Layout.fillWidth:true }
    Label { visible:root.saving;text:root.tr("Saving…");font.pixelSize:Style.space(11);color:root.secondary }
  }
  Column {
    width:parent.width-root.padding*2
    spacing:Style.space(8)
    Label { text:root.tr("General");font.pixelSize:Style.space(11);font.letterSpacing:1.2;font.capitalization:Font.AllUppercase;color:root.secondary }
    Controls.Switch {
      width:parent.width
      implicitHeight:Style.space(36)
      text:root.tr("Show bar percentage")
      activeFocusOnTab:true
      indicator:Rectangle {
        x:parent.width-width
        anchors.verticalCenter:parent.verticalCenter
        width:Style.space(32);height:Style.space(19);radius:height/2
        color:parent.checked?Color.accent:Qt.alpha(Color.popups.text,0.16)
        border.width:parent.activeFocus?1:0
        border.color:Color.accent
        Rectangle { x:parent.parent.checked?parent.width-width-Style.space(3):Style.space(3);y:Style.space(3);width:Style.space(13);height:width;radius:width/2;color:parent.parent.checked?Color.popups.background:Color.popups.text }
      }
      contentItem:Label { text:parent.text;verticalAlignment:Text.AlignVCenter;rightPadding:Style.space(45);wrapMode:Text.WordWrap }
      checked:Preferences.value(root.settings,"showPercentage")
      enabled:!root.saving
      onClicked:root.save("showPercentage",checked)
    }
    PowerDropdown {
      width:parent.width
      label:root.tr("Language")
      fontFamily:"sans-serif"
      value:Preferences.value(root.settings,"language")
      options:[{value:"system",label:root.tr("System")},{value:"en",label:"English"},{value:"nb",label:"Norsk bokmål"}]
      enabled:!root.saving
      onChanged:function(value){root.save("language",value)}
    }
  }
  Column {
    width:parent.width-root.padding*2
    spacing:Style.space(18)
    topPadding:Style.space(8)
    Label { text:root.tr("Default power profiles");font.pixelSize:Style.space(11);font.letterSpacing:1.2;font.capitalization:Font.AllUppercase;color:root.secondary }
    PowerDropdown { width:parent.width;label:root.tr("Plugged in (AC)");fontFamily:"sans-serif";value:root.defaults.ac||"";options:root.profileOptions;enabled:!root.saving&&root.profiles.length>0;onChanged:function(value){root.saveDefault("ac",value)} }
    PowerDropdown { width:parent.width;label:root.tr("On battery (DC)");fontFamily:"sans-serif";value:root.defaults.battery||"";options:root.profileOptions;enabled:!root.saving&&root.profiles.length>0;onChanged:function(value){root.saveDefault("battery",value)} }
    Label { width:parent.width;text:root.tr("A profile selected from the main view lasts until the power source changes.");font.pixelSize:Style.space(12);color:root.secondary;wrapMode:Text.WordWrap }
  }
  Column {
    visible:root.error!==""
    width:parent.width-root.padding*2
    spacing:Style.space(8)
    Label { width:parent.width;text:root.error;color:Color.urgent;wrapMode:Text.WordWrap;Accessible.role:Accessible.AlertMessage }
    PowerAction { label:root.tr("Retry");iconName:"refresh-cw";foreground:root.secondary;enabled:!root.saving;onClicked:root.retry() }
  }
  component Label:Text { textFormat:Text.PlainText;color:Color.popups.text;font.family:"sans-serif";font.pixelSize:Style.space(13) }
}
