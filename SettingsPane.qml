import QtQuick
import qs.Commons
import "kit"
import "Model.js" as Model
import "Preferences.js" as Preferences

// Power settings on the foamy settings skeleton: bar percentage options and
// Omarchy's AC/battery default profiles.
FoamySettingsPage {
  id: root

  required property var settings
  property var profiles: []
  property var defaults: ({})

  signal save(string key, var value)
  signal saveDefault(string source, string profile)

  // FoamyDropdown (kit 0.1.0) assigns `value` on select, which would cut the
  // binding to the saved default; restore it so the dropdown keeps showing
  // what is persisted (a failed save, or a change made elsewhere, shows up).
  function rebind(dropdown, source) {
    dropdown.value = Qt.binding(function() { return root.defaults[source] || "" })
  }

  readonly property var profileOptions: profiles.map(function(p) { return { value: p, label: FoamyI18n.t(Model.profileLabel(p)) } })

  FoamySettingsSection {
    width: parent.width
    title: FoamyI18n.t("Bar")
    FoamyToggle {
      id: showPercentageToggle
      width: parent.width
      enabled: !root.saving
      label: FoamyI18n.t("Show percentage in the bar")
      checked: Preferences.value(root.settings, "showPercentage")
      onClicked: root.save("showPercentage", !checked)
    }
    FoamyToggle {
      visible: showPercentageToggle.checked
      width: parent.width
      enabled: !root.saving
      label: FoamyI18n.t("Show only when battery is low")
      description: FoamyI18n.t("10% or less while on battery")
      checked: Preferences.value(root.settings, "showPercentageWhenLow")
      onClicked: root.save("showPercentageWhenLow", !checked)
    }
  }

  FoamySettingsSection {
    width: parent.width
    title: FoamyI18n.t("Default power profiles")
    description: FoamyI18n.t("A profile selected from the main view lasts until the power source changes.")
    FoamyDropdown {
      id: acDropdown
      objectName: "acDefault"
      width: parent.width
      label: FoamyI18n.t("Plugged in (AC)")
      value: root.defaults.ac || ""
      options: root.profileOptions
      enabled: !root.saving && root.profiles.length > 0
      onChanged: function(value) { root.rebind(acDropdown, "ac"); root.saveDefault("ac", value) }
    }
    FoamyDropdown {
      id: batteryDropdown
      objectName: "batteryDefault"
      width: parent.width
      label: FoamyI18n.t("On battery (DC)")
      value: root.defaults.battery || ""
      options: root.profileOptions
      enabled: !root.saving && root.profiles.length > 0
      onChanged: function(value) { root.rebind(batteryDropdown, "battery"); root.saveDefault("battery", value) }
    }
  }
}
