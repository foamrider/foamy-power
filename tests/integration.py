"""Exercise the real action helper and Omarchy 4.5's battery service with isolated power fixtures.

The battery service, Commons and the two power-profile scripts
(omarchy-powerprofiles-set and -list) come from the installed Omarchy
(OMARCHY_PATH, default /usr/share/omarchy). Its QML is loaded with UPower and
power-profiles-daemon mocked; `busctl` and `powerprofilesctl` are fakes, every
other Omarchy script is a foamy-kit hostenv stub that only logs (and
`omarchy-shell` reaches this test's shell alone), and HOME, the XDG
directories, the session bus and a dead system bus are temporary.
Needs foamy-kit (FOAMY_KIT, default ~/GitHub/Personal/foamy-kit).
"""

import json
import os
from pathlib import Path
import platform
import shutil
import signal
import subprocess
import sys
import tempfile

plugin = Path(__file__).resolve().parents[1]
kit = Path(os.environ.get("FOAMY_KIT", Path.home() / "GitHub/Personal/foamy-kit"))
sys.path.insert(0, str(kit / "preview"))
import harness  # noqa: E402
import hostenv  # noqa: E402

omarchy = Path(os.environ.get("OMARCHY_PATH", "/usr/share/omarchy"))
# A short name: qs's IPC socket (<runtime>/quickshell/by-id/<id>/ipc.sock)
# must fit a unix socket path (107 bytes), and TMPDIR may be long.
base = Path(tempfile.mkdtemp(prefix="fp-int-"))
app = base / "app"
app.mkdir()
bin_dir = base / "bin"
bin_dir.mkdir()
runtime = base / "runtime"
runtime.mkdir(mode=0o700)
assert len(str(runtime)) + len("/quickshell/by-id/xxxxxxxxxxx/ipc.sock") <= 107, (
    f"TMPDIR too long for qs ipc: {runtime}"
)
state = base / "powerprofiles"
state.mkdir()
fixture = base / "fixture.json"
fixture.write_text(json.dumps({"source": "ac", "active": "balanced", "fail": False}))
env = {
    **os.environ,
    "HOME": str(base),
    "XDG_RUNTIME_DIR": str(runtime),
    "OMARCHY_POWERPROFILES_STATE_DIR": str(state),
    "POWER_FIXTURE": str(fixture),
    "QT_QPA_PLATFORM": "offscreen",
    "QT_QPA_PLATFORMTHEME": "basic",
    "QT_STYLE_OVERRIDE": "Fusion",
    # No session bus: nothing here may reach the desktop's.
    "DBUS_SESSION_BUS_ADDRESS": f"unix:path={base}/no-session-bus",
}
# No Omarchy bin dir, AppImage library or system bus (hostenv.isolate). Only
# the scripts under test run for real; every other Omarchy script (a later
# version of these may call more) is a stub that logs the call, checked below.
hostenv.isolate(env, base)
real = {
    name: f'#!/bin/sh\nexec "{omarchy / "bin" / name}" "$@"\n'
    for name in ("omarchy-powerprofiles-set", "omarchy-powerprofiles-list")
}
env.update(hostenv.make(base, app, env, stubs=real))
env["PATH"] = f"{bin_dir}:{env['PATH']}"
# Temporary XDG directories: 4.5's Commons reads the language from the config home.
for name in ("XDG_CONFIG_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME"):
    env[name] = str(base / name.lower())
for name in ("WAYLAND_DISPLAY", "DISPLAY", "HYPRLAND_INSTANCE_SIGNATURE"):
    env.pop(name, None)

stub = """#!/usr/bin/python3
import json,os,pathlib,sys
path=pathlib.Path(os.environ['POWER_FIXTURE']);data=json.loads(path.read_text());args=sys.argv[1:]
def save(data):
    temp=path.with_name(f'{path.name}.{os.getpid()}');temp.write_text(json.dumps(data));os.replace(temp,path)
if pathlib.Path(sys.argv[0]).name=='powerprofilesctl':
    if data['fail']: sys.exit(1)
    if args[0]=='list':
        for p in ['power-saver','balanced','performance']: print(('* ' if p==data['active'] else '  ')+p+':')
    elif args[0]=='set':
        data['active']=args[1];save(data)
elif 'net.hadess.PowerProfiles' in args:
    if data['fail']: sys.exit(1)
    if 'set-property' in args:
        data['active']=args[-1];save(data)
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
"""
for name in ("busctl", "powerprofilesctl"):
    path = bin_dir / name
    path.write_text(stub)
    path.chmod(0o755)

service_source = omarchy / "shell/plugins/services/battery"
service = (service_source / "Service.qml").read_text()
# UPower and PowerProfiles become Mock.State; the enum values are Quickshell's.
for old, new in [
    ("import Quickshell.Services.UPower", 'import "mocks" as Mock'),
    ("UPowerDeviceState.Discharging", "2"),
    ("PowerProfile.PowerSaver", "0"),
    ("PowerProfile.Performance", "2"),
    ("target: PowerProfiles", "target: Mock.State"),
    ("PowerProfiles.profile", "Mock.State.profile"),
    ("target: UPower", "target: Mock.State"),
    ("UPower.", "Mock.State."),
]:
    assert old in service, f"{service_source}/Service.qml changed shape: no {old!r}"
    service = service.replace(old, new)
(app / "Service.qml").write_text(service)
shutil.copy(service_source / "BatteryModel.js", app)
(app / "Commons").symlink_to(omarchy / "shell/Commons", target_is_directory=True)
mocks = app / "mocks"
mocks.mkdir()
(mocks / "qmldir").write_text("module Mock\nsingleton State 1.0 State.qml\n")
(mocks / "State.qml").write_text(
    "pragma Singleton\nimport QtQuick\nQtObject { property bool onBattery:false; property int profile:1; property var displayDevice:({isPresent:true,percentage:0.68,state:2}) }\n"
)
(app / "shell.qml").write_text("""import QtQuick
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
""")


# FOAMY_HELPER: the helper's argv prefix as a JSON list (see test_power_action.py).
helper = (
    json.loads(os.environ["FOAMY_HELPER"])
    if os.environ.get("FOAMY_HELPER")
    else [str(plugin / "bin" / platform.machine() / "foamy-power-helper")]
)


def cli(*args, success=True):
    response = subprocess.run([*helper, *args], env=env, text=True, capture_output=True, timeout=40)
    assert (response.returncode == 0) == success, response.stdout + response.stderr
    return json.loads(response.stdout)


def update(**values):
    # Replaced, never rewritten in place: the fakes read it concurrently.
    data = json.loads(fixture.read_text())
    temp = fixture.with_name(fixture.name + ".test")
    temp.write_text(json.dumps({**data, **values}))
    os.replace(temp, fixture)


def wait_active(profile):
    if not harness.wait_for(lambda: json.loads(fixture.read_text())["active"] == profile, 20):
        raise AssertionError("Automatic switch did not apply " + profile)


log_path = base / "runtime.log"
with log_path.open("w") as log:
    # Its own process group: the stock service's omarchy-powerprofiles-set (and
    # the `qs ipc` it starts) end with the shell below.
    process = subprocess.Popen(
        ["qs", "-p", str(app), "--no-color"], env=env, stdout=log, stderr=log, start_new_session=True
    )
    try:

        def transition(source):
            update(source=source)
            response = subprocess.run(
                ["qs", "ipc", "-p", str(app), "call", "fixture", "source", str(source == "battery").lower()],
                env=env,
                text=True,
                capture_output=True,
                timeout=15,
            )
            assert response.returncode == 0 and response.stdout.strip() == "ok", response.stdout + response.stderr

        def ready():
            try:
                response = subprocess.run(
                    ["qs", "ipc", "-p", str(app), "call", "fixture", "source", "false"],
                    env=env,
                    text=True,
                    capture_output=True,
                    timeout=15,
                )
            except subprocess.TimeoutExpired:
                return False
            return response.returncode == 0 and response.stdout.strip() == "ok"

        if not harness.wait_for(ready, 30, stop=lambda: process.poll() is not None):
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
        print(
            "PASS: helper commands over busctl, atomic shared defaults, temporary override, stock battery service unplug/replug, unavailable profile service, lock outside Omarchy state"
        )
    finally:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            pass
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
shell_log = log_path.read_text()
assert not any(
    marker in shell_log for marker in ("ReferenceError", "TypeError", "Failed to load", "Unable to assign")
), shell_log
# omarchy-powerprofiles-set asks this test's shell to re-read the profile; no
# other Omarchy script ran.
hostenv.check(env, shell_log)
others = [line for line in hostenv.calls(base) if Path(line.split()[0]).name != "omarchy-shell"]
assert not others, others
# Passed: nothing to inspect. A failure above keeps the directory for its log.
# A script the last transition started can still be finishing (it outlives
# the shell's group only if it left it); it would recreate runtime/ after
# the removal, so wait for everything that names this directory first.
assert harness.wait_for(lambda: not harness.processes_under(base), 10), harness.processes_under(base)
shutil.rmtree(base)
