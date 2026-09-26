"""Exercise the real helper and Omarchy battery service using isolated power fixtures."""

import json
import os
from pathlib import Path
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
       "QT_QPA_PLATFORM": "offscreen", "QT_QPA_PLATFORMTHEME": "basic", "QT_STYLE_OVERRIDE": "Fusion"}
env.pop("WAYLAND_DISPLAY", None)

stub = '''#!/usr/bin/python3
import json,os,pathlib,sys
path=pathlib.Path(os.environ['POWER_FIXTURE']);data=json.loads(path.read_text());args=sys.argv[1:]
if pathlib.Path(sys.argv[0]).name=='powerprofilesctl':
    if data['fail']: sys.exit(1)
    if args[0]=='list':
        for p in ['power-saver','balanced','performance']: print(('* ' if p==data['active'] else '  ')+p+':')
    elif args[0]=='set':
        data['active']=args[1];path.write_text(json.dumps(data))
elif 'EnumerateDevices' in args:
    print(json.dumps({'type':'ao','data':[['/org/freedesktop/UPower/devices/battery_BAT0']]}))
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

service_source = omarchy / "shell/plugins/services/battery"
service = (service_source / "Service.qml").read_text()
service = service.replace("import Quickshell.Services.UPower", 'import "mocks" as Mock')
service = service.replace("UPower.", "Mock.State.").replace("UPowerDeviceState.Discharging", "2")
service = service.replace("target: UPower", "target: Mock.State")
(app / "Service.qml").write_text(service)
shutil.copy(service_source / "BatteryModel.js", app)
mocks = app / "mocks"
mocks.mkdir()
(mocks / "qmldir").write_text("module Mock\nsingleton State 1.0 State.qml\n")
(mocks / "State.qml").write_text('pragma Singleton\nimport QtQuick\nQtObject { property bool onBattery:false; property var displayDevice:({isPresent:true,percentage:0.68,state:2}) }\n')
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


def cli(*args, success=True):
    response = subprocess.run(["python3", str(plugin / "power_status.py"), *args], env=env, text=True, capture_output=True, timeout=10)
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
        reading = cli("status")
        assert reading["battery"]["percentage"] == 68 and reading["battery"]["cycles"] == 186
        cli("default", "ac", "performance")
        wait_active("performance")
        cli("default", "battery", "power-saver")
        wait_active("performance")
        cli("set", "balanced")
        wait_active("balanced")
        assert (state / "ac").read_text().strip() == "performance"
        transition("battery")
        wait_active("power-saver")
        assert cli("status")["battery"]["state"] == "discharging"
        transition("ac")
        wait_active("performance")
        update(fail=True)
        failure = cli("set", "balanced", success=False)
        assert failure["error"]["code"] == "COMMAND_FAILED"
        reading = cli("status")
        assert reading["battery"]["present"] and reading["errors"] and not reading["profiles"]
        print("PASS: helper commands, shared defaults, temporary override, stock battery service unplug/replug, and unavailable profile service")
    finally:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
print("Isolated runtime evidence:", base)
