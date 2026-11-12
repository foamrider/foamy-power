"""Load the real Panel.qml twice (two monitors) in an isolated offscreen shell
on a chosen Omarchy host and check: one leader owns IPC, PowerService reads
power profiles once (stub `busctl`) and the AC/battery defaults in process,
the popup body builds lazily, the width does not change when Settings opens,
quick successive saves are queued on both the inline and CLI paths, the
default-profile dropdowns keep following the saved defaults after a selection
(whose action reaches the native helper and its JSON reply),
and re-read sysfs facts are published once their reload completes. A second
run, with only `qs` and the harness's omarchy stubs on PATH, checks that a profile read or an action
whose command can't start ends with an error instead of empty data.

  python3 tests/runtime.py

Runs on Omarchy 4.5: the installed /usr/share/omarchy/shell, or the tree in
FOAMY_HOST_45.

Uses foamy-kit's preview harness (FOAMY_KIT, default ~/GitHub/Personal/foamy-kit):
temp HOME/XDG dirs, no Wayland/Hyprland variables, no host scripts run. The
`omarchy` CLI is a stub that only logs its arguments; a run that tried any other
host command fails.
"""

import os
import shutil
import sys
from pathlib import Path

plugin = Path(__file__).resolve().parents[1]
kit = Path(os.environ.get("FOAMY_KIT", Path.home() / "GitHub/Personal/foamy-kit"))
# The installed shell is 4.5; set before the harness reads it.
os.environ.setdefault("FOAMY_HOST_45", "/usr/share/omarchy/shell")
sys.path.insert(0, str(kit / "preview"))
import harness  # noqa: E402

SHELL = r"""import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui
import "harness"
import "plugin" as Plugin
import "plugin/kit" as Kit

ShellRoot {
  id: shell
  property int step: 0
  property var calls: []
  property bool inline: true
  function fail(message) { console.log("FOAMY FAIL " + message); Qt.quit() }
  function check(condition, message) { if (!condition) fail(message); return condition }

  FloatingWindow {
    implicitWidth: 1920; implicitHeight: 1080
    ScreenSim { id: sim }
    Plugin.Panel { id: one; x: 1400; y: 4; width: 30; height: 26 }
    Plugin.Panel { id: two; x: 1440; y: 4; width: 30; height: 26 }
  }

  MockBar {
    id: bar
    shell: QtObject {
      function updateEntryInline(id, settings) {
        shell.calls = shell.calls.concat([{ id: id, settings: JSON.parse(JSON.stringify(settings)) }])
        return shell.inline
      }
    }
  }

  Component.onCompleted: {
    for (var p of [one, two]) { p.bar = bar; p.moduleName = "foamy.power"; p.settings = { showPercentage: false } }
    step0()
  }

  function ipcEnabled(panel) {
    for (var i = 0; i < panel.data.length; i++) {
      var o = panel.data[i]
      if (o && String(o).indexOf("FoamyIpc") === 0) return o.enabled
    }
    return null
  }

  FoamyWait { id: wait }

  // Each step waits for the state it checks; wait.after() only where the
  // check is that nothing changes (the width while Settings opens).
  function step0() {
    wait.waitFor(function() {
      return ipcEnabled(one) !== null && Plugin.PowerService.profiles.length === 3 && Plugin.PowerService.defaults.ac !== undefined
    }, 10000, function() {
      if (!check(ipcEnabled(one) !== ipcEnabled(two) && ipcEnabled(one) !== null, "exactly one IPC leader " + ipcEnabled(one) + " " + ipcEnabled(two))) return
      if (!check(JSON.stringify(Plugin.PowerService.profiles) === '["power-saver","balanced","performance"]' && Plugin.PowerService.active === "balanced", "profiles from busctl: " + JSON.stringify(Plugin.PowerService.profiles) + " " + Plugin.PowerService.active)) return
      if (!check(Plugin.PowerService.defaults.ac === "power-saver" && Plugin.PowerService.defaults.battery === "balanced", "defaults from state files: " + JSON.stringify(Plugin.PowerService.defaults))) return
      if (!check(one.popup && one.popup.bodyItem === null, "body not built before first open " + one.popup + " " + one.data.concat(one.children).map(String).join(","))) return
      if (!check(Plugin.PowerService.demanded === false, "no demand while closed")) return
      one.open()
      wait.waitFor(function() { return one.popup.bodyItem !== null }, 10000, step1, "body built on open")
    })
  }
  function step1(ok) {
    if (!ok) return
    shell.width0 = one.popup.contentWidth
    one.openSettings()
    wait.waitFor(function() { return one.editingSettings && Plugin.PowerService.demanded }, 10000, function(ok) {
      if (!check(ok, "Settings open, with demand: editing " + one.editingSettings + ", demanded " + Plugin.PowerService.demanded)) return
      wait.after(300, step2)
    })
  }
  function step2() {
    if (!check(one.popup.contentWidth === shell.width0, "width stays " + shell.width0 + " in Settings, got " + one.popup.contentWidth)) return
    if (!check(one.showPercentage === false && one.percentageVisible === false, "bar reads the setting through the schema")) return
    // Inline path: the shell entry does not update yet; the second save must carry the first.
    one.savePreference("showPercentage", true)
    one.savePreference("showPercentageWhenLow", true)
    if (!check(shell.calls.length === 2, "two inline saves, got " + shell.calls.length)) return
    if (!check(shell.calls[1].settings.showPercentage === true && shell.calls[1].settings.showPercentageWhenLow === true, "second inline save keeps the first: " + JSON.stringify(shell.calls[1].settings))) return
    if (!check(one.showPercentage === true, "a pending save reads at once")) return
    // CLI path: both saves run, one after another.
    shell.inline = false
    two.savePreference("showPercentage", true)
    two.savePreference("showPercentageWhenLow", true)
    if (!check(two.saving, "second CLI save queued while the first runs")) return
    wait.waitFor(function() { return !two.saving }, 15000, step3, "the CLI save queue drains")
  }
  function step3(ok) {
    if (!ok) return
    logView.path = Quickshell.env("FOAMY_CLI_LOG")
    logView.reload()
    var lines = logView.text().trim().split("\n")
    if (!check(lines.length === 2, "two CLI saves, got " + JSON.stringify(lines))) return
    if (!check(lines[0] === "bar set foamy.power showPercentage true --json" && lines[1] === "bar set foamy.power showPercentageWhenLow true --json", "CLI order: " + JSON.stringify(lines))) return
    if (!check(two.prefs.error === "", "queue drained without error: " + two.prefs.error)) return
    // Default-profile dropdown: selecting must not cut its binding to the saved default.
    var dd = shell.find(one.popup.bodyItem, "acDefault")
    if (!check(dd && dd.value === "power-saver", "AC dropdown shows the saved default: " + (dd ? dd.value : "missing"))) return
    dd.changed("balanced")         // a pick: the kit emits, the saved default stays the source
    if (!check(dd.value === "power-saver", "dropdown rebound to the saved default after select, got " + dd.value)) return
    // The pick runs the helper through FoamyNative; the stub busctl refuses everything but reads.
    wait.waitFor(function() { return !Plugin.PowerService.busy && Plugin.PowerService.actionError !== "" }, 20000, step4, "the helper replies")
  }
  function step4(ok) {
    if (!ok) return
    if (!check(Plugin.PowerService.actionError === "busctl failed. Check the power service and permissions.", "helper replied through QML: " + Plugin.PowerService.actionError)) return
    if (!check(facts.threshold === 80 && facts.cycles === 186, "sysfs facts loaded: " + facts.threshold + "/" + facts.cycles)) return
    shell.saves = 0
    thresholdWriter.setText("60\n")
    cyclesWriter.setText("190\n")
    acWriter.setText("performance\n")   // a default changed elsewhere
    wait.waitFor(function() { return shell.saves === 3 }, 10000, step5, "the fixture files are written")
  }
  function step5(ok) {
    if (!ok) return
    shell.factUpdates = 0
    facts.reload()
    wait.waitFor(function() {
      var dd = shell.find(one.popup.bodyItem, "acDefault")
      return facts.threshold === 60 && facts.cycles === 190 && shell.factUpdates >= 2 && dd && dd.value === "performance"
    }, 10000, function(ok) {
      var dd = shell.find(one.popup.bodyItem, "acDefault")
      if (!check(ok, "reloaded sysfs facts published after load: " + facts.threshold + "/" + facts.cycles + " updates " + shell.factUpdates
                 + "; dropdown follows a default changed elsewhere: " + (dd ? dd.value : "missing"))) return
      one.closeSettings(); one.close()
      console.log("FOAMY DONE")
      Qt.quit()
    })
  }
  property real width0: 0
  property int factUpdates: 0
  property int saves: 0
  function find(item, name) {
    if (!item) return null
    if (item.objectName === name) return item
    var kids = item.children || []
    for (var i = 0; i < kids.length; i++) { var hit = find(kids[i], name); if (hit) return hit }
    return null
  }
  FileView { id: logView; blockLoading: true; printErrors: false }
  Plugin.BatteryFacts { id: facts; base: Quickshell.env("FOAMY_SYSFS"); supply: "BAT0"; onUpdated: shell.factUpdates++ }
  FileView { id: thresholdWriter; onSaved: shell.saves++; path: Quickshell.env("FOAMY_SYSFS") + "/BAT0/charge_control_end_threshold"; printErrors: false }
  FileView { id: cyclesWriter; onSaved: shell.saves++; path: Quickshell.env("FOAMY_SYSFS") + "/BAT0/cycle_count"; printErrors: false }
  FileView { id: acWriter; onSaved: shell.saves++; path: Quickshell.env("HOME") + "/.local/state/omarchy/powerprofiles/ac"; printErrors: false }
}
"""

# Neither `busctl` nor `timeout` can start: Quickshell then emits no exited(),
# only running -> false. Both must still end, with an error.
FAILED_START = r"""import QtQuick
import Quickshell
import qs.Ui
import "harness"
import "plugin" as Plugin

ShellRoot {
  id: shell
  function fail(message) { console.log("FOAMY FAIL " + message); Qt.quit() }
  FloatingWindow {
    implicitWidth: 1920; implicitHeight: 1080
    ScreenSim { }
    Plugin.Panel { id: one; x: 1400; y: 4; width: 30; height: 26 }
  }
  MockBar { id: bar; shell: QtObject { function updateEntryInline(id, settings) { return true } } }
  Component.onCompleted: { one.bar = bar; one.moduleName = "foamy.power"; one.settings = {}; noProbe() }
  FoamyWait { id: wait }
  readonly property var service: Plugin.PowerService
  function state() { return "profiles " + JSON.stringify(service.profilesError) + ", action " + JSON.stringify(service.actionError) + ", busy " + service.busy }
  // Each failure has 10 s to arrive on a loaded machine.
  function noProbe() {
    wait.waitFor(function() { return service.profilesError !== "" }, 10000, function(ok) {
      if (!ok) return shell.fail("the profile read that couldn't start never ended: " + state())
      if (service.profilesKnown || service.probe.running) return shell.fail("probe that couldn't start still pending")
      service.setProfile("balanced")
      noAction()
    })
  }
  function noAction() {
    wait.waitFor(function() { return service.actionError !== "" }, 10000, function(ok) {
      if (!ok) return shell.fail("the action that couldn't start never ended: " + state())
      if (service.busy || service.actionError !== "Power action failed. Try again.") return shell.fail("action that couldn't start: " + state())
      // The next request runs again: nothing stayed in flight.
      service.refresh()
      wait.waitFor(function() { return service.profilesError !== "" && service.actionError === "" }, 10000, function(ok) {
        if (!ok) return shell.fail("a refresh after the failures: " + state())
        console.log("FOAMY DONE")
        Qt.quit()
      })
    })
  }
}
"""


def run_failed_start(host):
    r = harness.Run(host, FAILED_START, plugin=plugin, prefix=f"foamy-power-nostart-{host}-")
    stub = r.base / "bin"
    stub.mkdir()
    (stub / "qs").symlink_to(shutil.which("qs"))
    # Neither busctl nor timeout is on PATH; the harness's omarchy stubs stay first.
    r.env["PATH"] = f"{r.base / 'host-bin'}:{stub}"
    return finish(r.run(timeout=40), "foamy-power runtime (commands that can't start)")


BUSCTL = """#!/bin/sh
[ "$2" = get-property ] || exit 1
echo '{"type":"s","data":"balanced"}'
echo '{"type":"aa{sv}","data":[{"Profile":{"type":"s","data":"power-saver"}},{"Profile":{"type":"s","data":"balanced"}},{"Profile":{"type":"s","data":"performance"}}]}'
"""


def run(host):
    r = harness.Run(
        host,
        SHELL,
        plugin=plugin,
        prefix=f"foamy-power-runtime-{host}-",
        fakebin={"omarchy": '#!/bin/sh\nsleep 0.2\necho "$*" >> "$FOAMY_CLI_LOG"\n', "busctl": BUSCTL},
    )
    profiles = r.base / "home/.local/state/omarchy/powerprofiles"
    profiles.mkdir(parents=True)
    (profiles / "ac").write_text("power-saver\n")
    sysfs = r.base / "sysfs/BAT0"
    sysfs.mkdir(parents=True)
    (sysfs / "charge_control_end_threshold").write_text("80\n")
    (sysfs / "cycle_count").write_text("186\n")
    r.env["FOAMY_SYSFS"] = str(sysfs.parent)
    r.env["FOAMY_CLI_LOG"] = str(r.base / "cli.log")
    r.run(timeout=60)
    for line in r.log.splitlines():
        if ("WARN" in line or "rror" in line) and "wl_display" not in line and "window masks" not in line:
            print("  log:", line.strip())
    return finish(r, "foamy-power runtime")


def finish(r, name):
    """Pass only when the scene finished and no real host command was tried."""
    commands = r.host_commands()
    ok = r.ok and not commands
    if not ok:
        print(r.log)
        for line in commands:
            print("  host command:", line)
    print(f"{name}: {'pass' if ok else 'FAIL'}")
    r.cleanup()
    return ok


sys.exit(0 if all([run("4.5"), run_failed_start("4.5")]) else 1)
