import QtQuick
import QtQuick.Controls as Controls
import Quickshell
import Quickshell.Io
import Quickshell.Services.UPower
import qs.Commons
import qs.Ui
import "Model.js" as Model
import "Preferences.js" as Preferences

Panel {
  id:root
  moduleName:"foamy.power"
  ipcTarget:"foamy.power"
  manageIpc:false
  readonly property bool vertical:bar&&(bar.position==="left"||bar.position==="right")
  readonly property string helperPath:decodeURIComponent(Qt.resolvedUrl("power_status.py").toString().replace(/^file:\/\//,""))
  readonly property string language:Preferences.language(Preferences.value(settings,"language"),Qt.locale().name)
  readonly property bool showPercentage:Preferences.value(settings,"showPercentage")
  readonly property bool batteryPresent:!!(UPower.displayDevice&&UPower.displayDevice.isPresent&&UPower.displayDevice.type===UPowerDeviceType.Battery)
  readonly property real fraction:batteryPresent?Math.max(0,Math.min(1,UPower.displayDevice.percentage)):0
  readonly property string barIcon: {
    if(!batteryPresent)return "battery-medium"
    var state=UPower.displayDevice.state
    if(UPower.onBattery||state===UPowerDeviceState.Discharging)
      return fraction<0.15?"battery-low":fraction>=0.9?"battery-full":"battery-medium"
    return state===UPowerDeviceState.Charging&&!(payload.battery&&payload.battery.state==="holding")?"battery-charging":"battery-full"
  }
  readonly property color foreground:bar?bar.barForeground:Color.foreground
  property var payload:({battery:null,source:null,profiles:[],active:"",defaults:{},errors:[]})
  property bool editingSettings:false
  property string queryError:""
  property string actionError:""
  property string settingsError:""
  property bool refreshPending:false
  property var pendingPreferences:({})
  readonly property string errors:([queryError,actionError].concat(payload.errors.map(function(e){return root.tr(e.message)})).filter(function(e){return e!==""}).join("\n"))
  function tr(label){return Preferences.text(label,language)}
  function refresh(){
    // Coalesce source transitions and post-action reads; never overlap snapshots or publish an old one after a write.
    if(statusProcess.running||actionProcess.running){refreshPending=true;return}
    refreshPending=false
    statusProcess.running=true
  }
  function runAction(args){
    if(actionProcess.running||statusProcess.running)return
    actionError=""
    actionProcess.command=["timeout","--kill-after=1s","30s","python3",helperPath].concat(args)
    actionProcess.running=true
  }
  function savePreference(key,value){
    if(!Preferences.valid(key,value))return
    settingsError=""
    pendingPreferences[key]=value
    flushPreferences()
  }
  function flushPreferences(){
    if(preferencesSave.running)return
    var keys=Object.keys(pendingPreferences)
    if(!keys.length)return
    var key=keys[0],value=pendingPreferences[key]
    delete pendingPreferences[key]
    preferencesSave.command=["omarchy-shell","shell","setBarWidget",moduleName,key," "+JSON.stringify(value),"{}"]
    preferencesSave.running=true
  }
  function openSettings(){editingSettings=true;open();scroll.contentY=0;Qt.callLater(function(){settingsPane.focusBack()})}
  function closeSettings(){editingSettings=false;scroll.contentY=0;Qt.callLater(function(){overview.settingsTarget.forceActiveFocus()})}
  function retry(){queryError="";actionError="";settingsError="";refresh()}
  visible:batteryPresent||opened
  implicitWidth:visible?button.implicitWidth:0
  implicitHeight:visible?button.implicitHeight:0
  Component.onCompleted:refresh()
  onOpenedChanged:{scroll.contentY=0;if(opened){refresh();Qt.callLater(function(){if(!root.editingSettings)scroll.forceActiveFocus()})}else editingSettings=false}
  Connections { target:UPower;function onOnBatteryChanged(){transitionRefresh.restart()} }
  Connections { target:UPower.displayDevice;function onStateChanged(){transitionRefresh.restart()}function onIsPresentChanged(){root.refresh()} }
  // Let Omarchy's existing battery service finish restoring the source default before reading its result.
  Timer { id:transitionRefresh;interval:650;onTriggered:root.refresh() }
  Timer { interval:5000;running:root.opened;repeat:true;onTriggered:root.refresh() }
  Process {
    id:statusProcess
    command:["timeout","--kill-after=1s","25s","python3",root.helperPath,"status"]
    stdout:StdioCollector { id:statusOutput;waitForEnd:true }
    onExited:function(code){
      if(code!==0)root.queryError=root.tr(root.payload.battery?"Battery readings are stale. Try again.":"Power query failed. Try again.")
      else {
        try{root.payload=Model.parsePayload(statusOutput.text);root.queryError=""}
        catch(error){root.queryError=root.tr("Invalid power status.");console.warn("foamy.power: invalid status response")}
      }
      if(root.refreshPending)Qt.callLater(root.refresh)
    }
  }
  Process {
    id:actionProcess
    stdout:StdioCollector { id:actionOutput;waitForEnd:true }
    onExited:function(code){
      try{
        var response=JSON.parse(actionOutput.text)
        if(code!==0||response.ok!==true)root.actionError=response.error&&typeof response.error.message==="string"?root.tr(response.error.message):root.tr("Power action failed. Try again.")
      }catch(error){root.actionError=root.tr("Power action failed. Try again.")}
      Qt.callLater(root.refresh)
    }
  }
  Process {
    id:preferencesSave
    stdout:StdioCollector { id:saveOutput;waitForEnd:true }
    onExited:function(code){if(code!==0||saveOutput.text.trim()!=="ok")root.settingsError=root.tr("Could not save settings.");Qt.callLater(root.flushPreferences)}
  }
  IpcHandler {
    target:"foamy.power"
    function open():void{root.open()}
    function close():void{root.close()}
    function toggle():void{root.toggle()}
    function settings():void{root.openSettings()}
    function refresh():void{root.refresh()}
    function togglePercentage():void{root.savePreference("showPercentage",!root.showPercentage)}
  }
  WidgetButton {
    id:button
    anchors.fill:parent
    bar:root.bar
    text:""
    labelVisible:false
    hasVisualContent:true
    fixedWidth:root.vertical?-1:Math.max(Style.bar.iconSlot,barContent.implicitWidth+Style.bar.iconSlot-Style.bar.iconCanvas)
    tooltipText:""
    Row {
      id:barContent
      anchors.centerIn:parent
      spacing:Style.space(4)
      PowerIcon { name:root.barIcon;width:Style.bar.iconCanvas;height:width;color:root.foreground;anchors.verticalCenter:parent.verticalCenter }
      Text { visible:root.showPercentage&&!root.vertical;text:Math.round(root.fraction*100)+"%";textFormat:Text.PlainText;color:root.foreground;font.family:button.fontFamily;font.pixelSize:button.fontSize;anchors.verticalCenter:parent.verticalCenter }
    }
    onPressed:function(b){if(b===Qt.RightButton)root.savePreference("showPercentage",!root.showPercentage);else root.toggle()}
  }
  PowerPopup {
    id:panel
    anchorItem:button
    owner:root
    bar:root.bar
    open:root.opened
    focusTarget:root.editingSettings?settingsPane.backTarget:scroll
    padding:0
    borderSpec:Border.flat(Qt.alpha(Color.popups.text,0.15),1)
    contentWidth:panel.fittedContentWidth(Style.space(420))
    contentHeight:panel.fittedContentHeight(Math.min(Style.space(700),root.editingSettings?settingsPane.implicitHeight:overview.implicitHeight))
    Flickable {
      id:scroll
      anchors.fill:parent
      clip:true
      contentWidth:width
      contentHeight:root.editingSettings?settingsPane.implicitHeight:overview.implicitHeight
      boundsBehavior:Flickable.StopAtBounds
      flickableDirection:Flickable.VerticalFlick
      onContentHeightChanged:contentY=Math.max(0,Math.min(contentY,contentHeight-height))
      onHeightChanged:contentY=Math.max(0,Math.min(contentY,contentHeight-height))
      Keys.onEscapePressed:root.editingSettings?root.closeSettings():root.close()
      Connections {
        target:scroll.Window.window
        function onActiveFocusItemChanged(){
          var item=target.activeFocusItem
          if(!item)return
          var point=item.mapToItem(scroll.contentItem,0,0)
          if(point.y<scroll.contentY)scroll.contentY=Math.max(0,point.y-Style.space(8))
          else if(point.y+item.height>scroll.contentY+scroll.height)scroll.contentY=Math.max(0,Math.min(scroll.contentHeight-scroll.height,point.y+item.height-scroll.height+Style.space(8)))
        }
      }
      Controls.ScrollBar.vertical:Controls.ScrollBar { policy:Controls.ScrollBar.AsNeeded }
      PowerView {
        id:overview
        visible:!root.editingSettings
        width:scroll.width
        battery:root.payload.battery
        profiles:root.payload.profiles
        activeProfile:root.payload.active
        language:root.language
        error:root.errors
        loading:statusProcess.running
        busy:actionProcess.running||statusProcess.running
        onSettingsRequested:root.openSettings()
        onProfileRequested:function(profile){root.runAction(["set",profile])}
        onRetryRequested:root.retry()
      }
      SettingsPane {
        id:settingsPane
        visible:root.editingSettings
        width:scroll.width
        settings:root.settings
        profiles:root.payload.profiles
        defaults:root.payload.defaults
        language:root.language
        saving:preferencesSave.running||actionProcess.running||statusProcess.running
        error:([root.settingsError,root.errors].filter(function(e){return e!==""}).join("\n"))
        onBack:root.closeSettings()
        onSave:function(key,value){root.savePreference(key,value)}
        onSaveDefault:function(source,profile){root.runAction(["default",source,profile])}
        onRetry:root.retry()
      }
    }
  }
}
