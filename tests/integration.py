"""Exercise the real action helper and Omarchy 4.5's battery service with isolated power fixtures.

The battery service, Commons and omarchy scripts come from the installed Omarchy
(OMARCHY_PATH, default /usr/share/omarchy). Its QML is loaded with UPower and
power-profiles-daemon mocked; `busctl`, `powerprofilesctl` and `omarchy-shell`
are stubs, and HOME, the XDG directories and the session bus are temporary.
"""

import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile
import time

plugin = Path(__file__).resolve().parents[1]
omarchy = Path(os.environ.get("OMARCHY_PATH", "/usr/share/omarchy"))
base = Path(tempfile.mkdtemp(prefix="foamy-power-integration-"))
app = base / "app"
app.mkdir()
bin_dir = base / "bin"
bin_dir.mkdir()
runtime = base / "runtime"
runtime.mkdir(mode=0o700)
state = base / "powerprofiles"
state.mkdir()
fixture = base / "fixture.json"
fixture.write_text(json.dumps({"source": "ac", "active": "balanced", "fail": False}))
env = {**os.environ, "HOME": str(base), "XDG_RUNTIME_DIR": str(runtime),
       "OMARCHY_POWERPROFILES_STATE_DIR": str(state), "POWER_FIXTURE": str(fixture),
       "PATH": str(bin_dir) + ":" + str(omarchy / "bin") + ":" + os.environ["PATH"],
       "QT_QPA_PLATFORM": "offscreen", "QT_QPA_PLATFORMTHEME": "basic", "QT_STYLE_OVERRIDE": "Fusion",
       "OMARCHY_PATH": str(omarchy), "FOAMY_TEST_APP": str(app),
       # No session bus: nothing here may reach the desktop's.
       "DBUS_SESSION_BUS_ADDRESS": f"unix:path={base}/no-session-bus"}
# Temporary XDG directories: 4.5's Commons reads the language from the config home.
for name in ("XDG_CONFIG_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME"):
    env[name] = str(base / name.lower())
for name in ("WAYLAND_DISPLAY", "DISPLAY", "HYPRLAND_INSTANCE_SIGNATURE"):
    env.pop(name, None)

stub = '''#!/usr/bin/python3
import json,os,pathlib,sys
path=pathlib.Path(os.environ['POWER_FIXTURE']);data=json.loads(path.read_text());args=sys.argv[1:]
if pathlib.Path(sys.argv[0]).name=='powerprofilesctl':
    if data['fail']: sys.exit(1)
    if args[0]=='list':
        for p in ['power-saver','balanced','performance']: print(('* ' if p==data['active'] else '  ')+p+':')
    elif args[0]=='set':
        data['active']=args[1];path.write_text(json.dumps(data))
elif 'net.hadess.PowerProfiles' in args:
    if data['fail']: sys.exit(1)
    if 'set-property' in args:
        data['active']=args[-1];path.write_text(json.dumps(data))
    else:
        print(json.dumps({'type':'s','data':data['active']}))
        print(json.dumps({'type':'aa{sv}','data':[{'Profile':{'type':'s','data':p}} for p in ['power-saver','balanced','performance']]}))
else:
    is_root='/org/freedesktop/UPower' in args
    values={'OnBattery':data['source']=='battery'} if is_root else {
        'NativePath':'BAT0','Type':2,'PowerSupply':True,'IsPresent':True,'Percentage':68,
        'State':2 if data['source']=='battery' else 1,'EnergyFull':57,'EnergyRate':24.6,
        'TimeToFull':2520,'TimeToEmpty':11520,'ChargeCycles':186,'ChargeEndThreshold':100}
    print(json.dumps({'type':'a{sv}','data':[{k:{'type':'v','data':v} for k,v in values.items()}]}))
'''
for name in ("busctl", "powerprofilesctl"):
    path = bin_dir / name
    path.write_text(stub)
    path.chmod(0o755)
# omarchy-powerprofiles-set asks the shell to re-read the profile; answer from
# this test's shell, never the desktop's.
shell_stub = bin_dir / "omarchy-shell"
shell_stub.write_text('#!/bin/sh\n[ "$1" = -q ] && shift\n'
                      'qs ipc -p "$FOAMY_TEST_APP" call "$@" >/dev/null 2>&1\nexit 0\n')
shell_stub.chmod(0o755)

service_source = omarchy / "shell/plugins/services/battery"
service = (service_source / "Service.qml").read_text()
# UPower and PowerProfiles become Mock.State; the enum values are Quickshell's.
for old, new in [("import Quickshell.Services.UPower", 'import "mocks" as Mock'),
                 ("UPowerDeviceState.Discharging", "2"),
                 ("PowerProfile.PowerSaver", "0"), ("PowerProfile.Performance", "2"),
                 ("target: PowerProfiles", "target: Mock.State"), ("PowerProfiles.profile", "Mock.State.profile"),
                 ("target: UPower", "target: Mock.State"), ("UPower.", "Mock.State.")]:
    assert old in service, f"{service_source}/Service.qml changed shape: no {old!r}"
    service = service.replace(old, new)
(app / "Service.qml").write_text(service)
shutil.copy(service_source / "BatteryModel.js", app)
(app / "Commons").symlink_to(omarchy / "shell/Commons", target_is_directory=True)
mocks = app / "mocks"
mocks.mkdir()
(mocks / "qmldir").write_text("module Mock\nsingleton State 1.0 State.qml\n")
(mocks / "State.qml").write_text('pragma Singleton\nimport QtQuick\nQtObject { property bool onBattery:false; property int profile:1; property var displayDevice:({isPresent:true,percentage:0.68,state:2}) }\n')
(app / "shell.qml").write_text('''import QtQuick
import Quickshell
import Quickshell.Io
import "mocks" as Mock
ShellRoot {
  Service {}
  IpcHandler {
    target:"fixture"
    function source(battery:bool):string { Mock.State.onBattery=battery;return "ok" }
  }
}
''')


# FOAMY_HELPER: the helper's argv prefix as a JSON list (see test_power_action.py).
helper = json.loads(os.environ["FOAMY_HELPER"]) if os.environ.get("FOAMY_HELPER") else [str(plugin / "bin" / platform.machine() / "foamy-power-helper")]


def cli(*args, success=True):
    response = subprocess.run([*helper, *args], env=env, text=True, capture_output=True, timeout=10)
    assert (response.returncode == 0) == success, response.stdout + response.stderr
    return json.loads(response.stdout)


def update(**values):
    data = json.loads(fixture.read_text())
    fixture.write_text(json.dumps({**data, **values}))


def wait_active(profile):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if json.loads(fixture.read_text())["active"] == profile:
            return
        time.sleep(0.05)
    raise AssertionError("Automatic switch did not apply " + profile)


log_path = base / "runtime.log"
with log_path.open("w") as log:
    process = subprocess.Popen(["qs", "-p", str(app), "--no-color"], env=env, stdout=log, stderr=log)
    try:
        def transition(source):
            update(source=source)
            response = subprocess.run(["qs", "ipc", "-p", str(app), "call", "fixture", "source", str(source == "battery").lower()], env=env, text=True, capture_output=True, timeout=3)
            assert response.returncode == 0 and response.stdout.strip() == "ok", response.stdout + response.stderr

        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            response = subprocess.run(["qs", "ipc", "-p", str(app), "call", "fixture", "source", "false"], env=env, text=True, capture_output=True, timeout=3)
            if response.returncode == 0 and response.stdout.strip() == "ok":
                break
            time.sleep(0.05)
        else:
            raise AssertionError(log_path.read_text())
        cli("default", "ac", "performance")
        wait_active("performance")
        cli("default", "battery", "power-saver")
        wait_active("performance")
        cli("set", "balanced")
        wait_active("balanced")
        assert (state / "ac").read_text().strip() == "performance"
        transition("battery")
        wait_active("power-saver")
        transition("ac")
        wait_active("performance")
        update(fail=True)
        failure = cli("set", "balanced", success=False)
        assert failure["error"]["code"] in ("COMMAND_FAILED", "PROFILES_UNAVAILABLE"), failure
        assert sorted(p.name for p in state.iterdir()) == ["ac", "battery"], list(state.iterdir())
        assert (runtime / "foamy-power.lock").exists()
        print("PASS: helper commands over busctl, atomic shared defaults, temporary override, stock battery service unplug/replug, unavailable profile service, lock outside Omarchy state")
    finally:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
shell_log = log_path.read_text()
assert not any(marker in shell_log for marker in ("ReferenceError", "TypeError", "Failed to load", "Unable to assign")), shell_log
print("Isolated runtime evidence:", base)
