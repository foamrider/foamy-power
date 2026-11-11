"""Black-box tests of the power action helper: it runs as a process, with fake
`busctl` and `omarchy-powerprofiles-set` executables on a PATH that holds
nothing else, and temporary HOME/XDG/state directories. Nothing here can reach
the real power-profiles daemon, UPower or Omarchy's state files.

FOAMY_HELPER is the helper's argv prefix as a JSON list (default: this
machine's bin/<arch>/foamy-power-helper), e.g. the aarch64 build through
qemu binfmt:
  FOAMY_HELPER='["bin/aarch64/foamy-power-helper"]' python3 -m unittest discover -s tests -p 'test_*.py'
"""

import fcntl
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest

PLUGIN = Path(__file__).resolve().parents[1]
PPD = ["net.hadess.PowerProfiles", "/net/hadess/PowerProfiles", "net.hadess.PowerProfiles"]
GET_PROFILES = ["busctl", "--system", "--json=short", "get-property", *PPD, "ActiveProfile", "Profiles"]
GET_SOURCE = ["busctl", "--system", "--json=short", "call", "org.freedesktop.UPower", "/org/freedesktop/UPower",
              "org.freedesktop.DBus.Properties", "GetAll", "s", "org.freedesktop.UPower"]


def set_profile(profile):
    return ["busctl", "--system", "set-property", *PPD, "ActiveProfile", "s", profile]


def helper_prefix():
    prefix = json.loads(os.environ["FOAMY_HELPER"]) if os.environ.get("FOAMY_HELPER") else [str(PLUGIN / "bin" / platform.machine() / "foamy-power-helper")]
    # Resolve the program now: the helper itself runs with a PATH of fakes only.
    program = prefix[0] if "/" in prefix[0] else shutil.which(prefix[0])
    if not program:
        raise RuntimeError(f"helper program not found: {prefix[0]}")
    return [str(Path(program).resolve()), *prefix[1:]]


HELPER = helper_prefix()

# One script serves every fake: it logs its argv (and LC_ALL) to calls.jsonl
# and answers from fixture.json, which tests edit.
FAKE = textwrap.dedent('''\
    #!{python}
    import json, os, sys, time
    from pathlib import Path
    here = Path(__file__).resolve().parent
    name, args = os.path.basename(sys.argv[0]), sys.argv[1:]
    with open(here / "calls.jsonl", "a") as log:
        log.write(json.dumps({{"argv": [name, *args], "lc_all": os.environ.get("LC_ALL")}}) + "\\n")
    fixture = here / "fixture.json"
    data = json.loads(fixture.read_text())
    if name == "busctl":
        key = "get-property" if "get-property" in args else "set-property" if "set-property" in args else "GetAll"
    else:
        key = name
    time.sleep(data["sleep"].get(key, 0))
    if key in data["fail"]:
        print("diagnostics with a machine id 0123456789abcdef", file=sys.stderr)
        sys.exit(1)
    if key == "get-property":
        if "profiles_reply" in data:
            sys.stdout.write(data["profiles_reply"])
        else:
            print(json.dumps({{"type": "s", "data": data["active"]}}))
            print(json.dumps({{"type": "aa{{sv}}", "data": [{{"Profile": {{"type": "s", "data": p}}, "Driver": {{"type": "s", "data": "placeholder"}}}} for p in data["profiles"]]}}))
    elif key == "set-property":
        data["active"] = args[-1]
    elif key == "GetAll":
        if "upower_reply" in data:
            sys.stdout.write(data["upower_reply"])
        else:
            sources = data["sources"]
            battery = (sources.pop(0) if len(sources) > 1 else sources[0]) == "battery"
            print(json.dumps({{"type": "a{{sv}}", "data": [{{"OnBattery": {{"type": "b", "data": battery}}, "DaemonVersion": {{"type": "s", "data": "1.90"}}}}]}}))
    elif key == "omarchy-powerprofiles-set":
        data["applied"].append(args)
    fixture.write_text(json.dumps(data))
''')


class Helper(unittest.TestCase):
    def setUp(self):
        base = tempfile.TemporaryDirectory(prefix="foamy-power-test-")
        self.addCleanup(base.cleanup)
        self.base = Path(base.name)
        self.bin = self.base / "bin"
        self.bin.mkdir()
        self.runtime = self.base / "runtime"
        self.runtime.mkdir(mode=0o700)
        self.state = self.base / "powerprofiles"
        self.state.mkdir()
        (self.base / "home").mkdir()
        script = FAKE.format(python=sys.executable)
        # powerprofilesctl and omarchy-shell must never run: the call log would show them.
        for name in ("busctl", "omarchy-powerprofiles-set", "powerprofilesctl", "omarchy-shell"):
            (self.bin / name).write_text(script)
            (self.bin / name).chmod(0o755)
        self.fixture = {"sources": ["ac"], "active": "balanced", "profiles": ["power-saver", "balanced", "performance"],
                        "fail": [], "sleep": {}, "applied": []}
        self.write_fixture()
        self.env = {"PATH": str(self.bin), "HOME": str(self.base / "home"), "XDG_RUNTIME_DIR": str(self.runtime),
                    "XDG_STATE_HOME": str(self.base / "state"), "XDG_CACHE_HOME": str(self.base / "cache"),
                    "OMARCHY_POWERPROFILES_STATE_DIR": str(self.state)}
        # Defence in depth: the helper must only ever find the fakes.
        self.assertEqual(shutil.which("busctl", path=self.env["PATH"]), str(self.bin / "busctl"))

    def write_fixture(self, **values):
        self.fixture.update(values)
        (self.bin / "fixture.json").write_text(json.dumps(self.fixture))

    def read_fixture(self):
        return json.loads((self.bin / "fixture.json").read_text())

    def calls(self):
        log = self.bin / "calls.jsonl"
        return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []

    def argvs(self):
        return [call["argv"] for call in self.calls()]

    def helper(self, *args, code=0, env=None):
        result = subprocess.run([*HELPER, *args], env=env or self.env, cwd=self.base, stdin=subprocess.DEVNULL,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        if code == 2:
            return result
        self.assertEqual(result.stderr, "")
        self.assertEqual(len(result.stdout.splitlines()), 1, result.stdout)
        reply = json.loads(result.stdout)
        if code == 0:
            self.assertEqual(reply, {"ok": True})
        else:
            self.assertIs(reply["ok"], False)
            self.assertEqual(sorted(reply["error"]), ["code", "message"])
        return reply

    def error(self, *args, env=None):
        return self.helper(*args, code=1, env=env)["error"]

    def state_files(self):
        return sorted(p.name for p in self.state.iterdir())


class ProfileTests(Helper):
    def test_current_selection_preserves_defaults(self):
        (self.state / "ac").write_text("performance\n")
        self.helper("set", "balanced")
        self.assertEqual(self.argvs(), [GET_PROFILES, GET_SOURCE, set_profile("balanced"), GET_SOURCE])
        self.assertEqual((self.state / "ac").read_text(), "performance\n")
        self.assertEqual(self.read_fixture()["active"], "balanced")

    def test_inactive_default_never_applies(self):
        self.helper("default", "battery", "power-saver")
        self.assertEqual(self.argvs(), [GET_PROFILES, GET_SOURCE, GET_SOURCE, GET_SOURCE])
        self.assertEqual((self.state / "battery").read_text(), "power-saver\n")
        self.assertEqual(self.read_fixture()["active"], "balanced")

    def test_active_default_applies(self):
        self.helper("default", "ac", "performance")
        self.assertEqual(self.argvs(), [GET_PROFILES, GET_SOURCE, GET_SOURCE, ["omarchy-powerprofiles-set", "ac"], GET_SOURCE])
        self.assertEqual((self.state / "ac").read_text(), "performance\n")

    def test_default_file_is_private_and_replaced_whole(self):
        (self.state / "ac").write_text("balanced\n")
        os.chmod(self.state / "ac", 0o644)
        self.helper("default", "ac", "power-saver")
        self.assertEqual((self.state / "ac").read_text(), "power-saver\n")
        self.assertEqual((self.state / "ac").stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.state_files(), ["ac"])

    def test_source_transition_wins_over_manual_request(self):
        self.write_fixture(sources=["ac", "battery", "battery"])
        self.helper("set", "performance")
        self.assertEqual(self.argvs(), [GET_PROFILES, GET_SOURCE, set_profile("performance"), GET_SOURCE,
                                        ["omarchy-powerprofiles-set", "battery"], GET_SOURCE])

    def test_source_that_keeps_changing_gives_up(self):
        self.write_fixture(sources=["ac", "battery", "ac", "battery", "ac"])
        self.assertEqual(self.error("set", "balanced"),
                         {"code": "SOURCE_UNSTABLE", "message": "Power source keeps changing. Try again when it is stable."})
        self.assertEqual(self.read_fixture()["applied"], [["battery"], ["ac"], ["battery"]])

    def test_unknown_source_does_not_write_default(self):
        self.write_fixture(upower_reply='{"type":"a{sv}","data":[{"OnBattery":{"type":"s","data":"maybe"}}]}\n')
        self.assertEqual(self.error("default", "ac", "balanced"),
                         {"code": "UNKNOWN_SOURCE", "message": "Cannot determine the power source."})
        self.assertEqual(self.state_files(), [])

    def test_failed_apply_reports_saved_default(self):
        self.write_fixture(fail=["omarchy-powerprofiles-set"])
        self.assertEqual(self.error("default", "ac", "balanced"),
                         {"code": "DEFAULT_SAVED_APPLY_FAILED", "message": "Default saved, but the active profile could not be applied. Try again."})
        self.assertEqual((self.state / "ac").read_text(), "balanced\n")

    def test_unavailable_profile_cannot_be_saved(self):
        self.write_fixture(profiles=["balanced"])
        self.assertEqual(self.error("default", "ac", "performance"),
                         {"code": "PROFILE_UNAVAILABLE", "message": "This power profile is not available on this machine."})
        self.assertEqual(self.state_files(), [])
        self.assertEqual(self.argvs(), [GET_PROFILES])

    def test_duplicate_operation_is_rejected(self):
        with open(self.runtime / "foamy-power.lock", "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertEqual(self.error("set", "balanced"),
                             {"code": "BUSY", "message": "Another power-profile change is running. Try again."})
        self.assertEqual(self.argvs(), [])

    def test_lock_stays_out_of_omarchy_state(self):
        self.helper("default", "battery", "power-saver")
        self.assertEqual(self.state_files(), ["battery"])
        self.assertTrue((self.runtime / "foamy-power.lock").is_file())

    def test_lock_falls_back_to_the_cache_without_a_runtime_dir(self):
        env = {**self.env}
        del env["XDG_RUNTIME_DIR"]
        self.helper("set", "balanced", env=env)
        cache = self.base / "cache/foamy-power"
        self.assertEqual(cache.stat().st_mode & 0o777, 0o700)
        self.assertTrue((cache / "action.lock").is_file())
        self.assertFalse((self.runtime / "foamy-power.lock").exists())

    def test_default_creates_missing_state_directory(self):
        nested = self.state / "fresh"
        self.helper("default", "ac", "balanced", env={**self.env, "OMARCHY_POWERPROFILES_STATE_DIR": str(nested)})
        self.assertEqual((nested / "ac").read_text(), "balanced\n")

    def test_state_directory_follows_xdg_state_home(self):
        env = {**self.env}
        del env["OMARCHY_POWERPROFILES_STATE_DIR"]
        self.helper("default", "battery", "balanced", env=env)
        self.assertEqual((self.base / "state/omarchy/powerprofiles/battery").read_text(), "balanced\n")
        self.assertEqual(self.state_files(), [])

    def test_unwritable_state_reports_write_failure(self):
        blocker = self.base / "blocker"
        blocker.write_text("")
        env = {**self.env, "OMARCHY_POWERPROFILES_STATE_DIR": str(blocker / "sub")}
        self.assertEqual(self.error("default", "ac", "balanced", env=env),
                         {"code": "STATE_WRITE_FAILED", "message": "Cannot save power-profile state. Check directory permissions."})
        self.assertEqual(self.read_fixture()["applied"], [])


class BoundaryTests(Helper):
    def test_real_busctl_response_format(self):
        self.write_fixture(upower_reply='{"type":"a{sv}","data":[{"OnBattery":{"type":"b","data":true}}]}')
        self.helper("default", "battery", "balanced")
        self.assertEqual(self.read_fixture()["applied"], [["battery"]])

    def test_real_profiles_format(self):
        self.write_fixture(profiles_reply='{"type":"s","data":"performance"}\n'
                           '{"type":"aa{sv}","data":[{"Profile":{"type":"s","data":"power-saver"}},'
                           '{"Profile":{"type":"s","data":"balanced"}},{"Profile":{"type":"s","data":"performance"}}]}\n')
        self.helper("set", "power-saver")
        self.assertEqual(self.argvs()[0], GET_PROFILES)
        self.assertNotIn("powerprofilesctl", [argv[0] for argv in self.argvs()])
        self.assertEqual(self.read_fixture()["active"], "power-saver")

    def test_unusable_profiles_reply(self):
        for reply in ("", "{}", "not json\n", '{"type":"s","data":"turbo"}\n{"type":"aa{sv}","data":[]}',
                      '{"type":"s","data":"balanced"}\n{"type":"aa{sv}","data":[{"Driver":{"type":"s","data":"x"}}]}',
                      '{"type":"s","data":"balanced"}\n'):
            with self.subTest(reply=reply):
                self.write_fixture(profiles_reply=reply)
                self.assertEqual(self.error("set", "balanced"),
                                 {"code": "PROFILES_UNAVAILABLE", "message": "Power profiles are unavailable. Check power-profiles-daemon."})
        self.assertNotIn(set_profile("balanced"), self.argvs())

    def test_unusable_upower_reply(self):
        for reply in ("", "nope", '{"type":"a{sv}","data":[]}', '{"type":"a{sv}","data":["x"]}',
                      '{"type":"a{sv}","data":[{"OnBattery":true}]}'):
            with self.subTest(reply=reply):
                self.write_fixture(upower_reply=reply)
                self.assertEqual(self.error("set", "balanced"),
                                 {"code": "INVALID_RESPONSE", "message": "Invalid response from UPower."})
        self.assertNotIn(set_profile("balanced"), self.argvs())

    def test_failing_service_hides_its_diagnostics(self):
        self.write_fixture(fail=["set-property"])
        self.assertEqual(self.error("set", "balanced"),
                         {"code": "COMMAND_FAILED", "message": "busctl failed. Check the power service and permissions."})

    def test_missing_busctl(self):
        (self.bin / "busctl").unlink()
        self.assertEqual(self.error("set", "balanced"),
                         {"code": "MISSING_COMMAND", "message": "Required command is missing: busctl."})

    def test_hung_service_times_out(self):
        self.write_fixture(sleep={"get-property": 20})
        started = time.monotonic()
        self.assertEqual(self.error("set", "balanced"),
                         {"code": "TIMEOUT", "message": "Power service timed out. Try again."})
        self.assertLess(time.monotonic() - started, 10)

    def test_slow_service_answers_within_the_widget_deadline(self):
        # Every call answers inside its 5 s deadline and the source keeps
        # changing: the nine calls of `set` would take 31.5 s. The widget's
        # wrapper (as in PowerService.qml) kills only the helper at 30 s, so
        # the helper must reply before that itself.
        self.write_fixture(sources=["ac", "battery"] * 10,
                           sleep={"get-property": 3.5, "GetAll": 3.5, "set-property": 3.5, "omarchy-powerprofiles-set": 3.5})
        started = time.monotonic()
        result = subprocess.run([shutil.which("timeout"), "--kill-after=1s", "30s", *HELPER, "set", "balanced"], env=self.env, cwd=self.base,
                                stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=40)
        elapsed = time.monotonic() - started
        self.assertEqual(result.returncode, 1, f"{result.stdout}{result.stderr} after {elapsed:.1f} s")
        self.assertEqual(json.loads(result.stdout)["error"]["code"], "TIMEOUT")
        self.assertLess(elapsed, 27)
        # Nothing the helper started outlives its reply (each fake saves the
        # fixture when it finishes).
        fixture = (self.bin / "fixture.json").read_text()
        time.sleep(4)
        self.assertEqual((self.bin / "fixture.json").read_text(), fixture)

    def test_commands_run_in_the_c_locale(self):
        self.helper("default", "ac", "balanced", env={**self.env, "LC_ALL": "nb_NO.UTF-8"})
        self.assertEqual({call["lc_all"] for call in self.calls()}, {"C"})

    def test_no_status_command(self):
        for args in (["status"], [], ["set"], ["set", "turbo"], ["set", "balanced", "extra"],
                     ["default", "mains", "balanced"], ["default", "ac"]):
            with self.subTest(args=args):
                result = self.helper(*args, code=2)
                if result.stdout.strip():
                    self.assertEqual(json.loads(result.stdout)["error"]["code"], "INVALID_ARGUMENT")
        self.assertEqual(self.argvs(), [])
        self.assertEqual(self.state_files(), [])


if __name__ == "__main__":
    unittest.main()
