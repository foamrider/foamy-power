import QtQuick
import qs.Commons
import "kit"
import "Model.js" as Model

// Power settings on the foamy settings skeleton: bar percentage options and
// Omarchy's AC/battery default profiles.
FoamySettingsPage {
  id: root

  required property var settings
  property var profiles: []
  property var defaults: ({})

  signal save(string key, var value)
  signal saveDefault(string source, string profile)

  readonly property var profileOptions: profiles.map(function(p) { return { value: p, label: FoamyI18n.t(Model.profileLabel(p)) } })

  FoamySettingsSection {
    width: parent.width
    title: FoamyI18n.t("Bar")
    FoamyToggle {
      id: showPercentageToggle
      width: parent.width
      enabled: !root.saving
      label: FoamyI18n.t("Show percentage in the bar")
      checked: root.settings.showPercentage === true
      onClicked: root.save("showPercentage", !checked)
    }
    FoamyToggle {
      visible: showPercentageToggle.checked
      width: parent.width
      enabled: !root.saving
      label: FoamyI18n.t("Show only when battery is low")
      description: FoamyI18n.t("10% or less while on battery")
      checked: root.settings.showPercentageWhenLow === true
      onClicked: root.save("showPercentageWhenLow", !checked)
    }
  }

  FoamySettingsSection {
    width: parent.width
    title: FoamyI18n.t("Default power profiles")
    description: FoamyI18n.t("A profile selected from the main view lasts until the power source changes.")
    FoamyDropdown {
      objectName: "acDefault"
      width: parent.width
      compact: true
      label: FoamyI18n.t("Plugged in (AC)")
      value: root.defaults.ac || ""
      options: root.profileOptions
      enabled: !root.saving && root.profiles.length > 0
      onChanged: function(value) { root.saveDefault("ac", value) }
    }
    FoamyDropdown {
      objectName: "batteryDefault"
      width: parent.width
      compact: true
      label: FoamyI18n.t("On battery (DC)")
      value: root.defaults.battery || ""
      options: root.profileOptions
      enabled: !root.saving && root.profiles.length > 0
      onChanged: function(value) { root.saveDefault("battery", value) }
    }
  }
}
