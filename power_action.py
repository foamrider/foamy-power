#!/usr/bin/env python3
"""Change the power profile or Omarchy's AC/battery default profiles.

Readings (battery, active profile, defaults) come from Quickshell's UPower and
PowerProfiles services in the widget itself; this helper only runs for a user
action: `set <profile>` or `default <ac|battery> <profile>`. Defaults are
written atomically to Omarchy's state files; the action lock lives in the
user's runtime directory, never in Omarchy's state directory."""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

PROFILES = ("power-saver", "balanced", "performance")
UPOWER = "org.freedesktop.UPower"
ROOT = "/org/freedesktop/UPower"
PPD = "net.hadess.PowerProfiles"
PPD_PATH = "/net/hadess/PowerProfiles"


class PowerError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code

    def payload(self) -> dict:
        return {"code": self.code, "message": str(self)}


def run(command: list[str]) -> str:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=5,
                                env={**os.environ, "LC_ALL": "C"})
    except FileNotFoundError as exc:
        raise PowerError("MISSING_COMMAND", f"Required command is missing: {command[0]}.") from exc
    except subprocess.TimeoutExpired as exc:
        raise PowerError("TIMEOUT", "Power service timed out. Try again.") from exc
    if result.returncode:
        # Service diagnostics can contain machine identifiers; expose a stable recovery message.
        raise PowerError("COMMAND_FAILED", f"{command[0]} failed. Check the power service and permissions.")
    return result.stdout


def bus_call(path: str, interface: str, method: str, *arguments: str):
    try:
        response = json.loads(run(["busctl", "--system", "--json=short", "call",
                                   UPOWER, path, interface, method, *arguments]))
        return response["data"][0]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise PowerError("INVALID_RESPONSE", "Invalid response from UPower.") from exc


def properties(path: str, interface: str) -> dict:
    values = bus_call(path, "org.freedesktop.DBus.Properties", "GetAll", "s", interface)
    if not isinstance(values, dict):
        raise PowerError("INVALID_RESPONSE", "Invalid response from UPower.")
    try:
        return {name: value["data"] for name, value in values.items()}
    except (KeyError, TypeError) as exc:
        raise PowerError("INVALID_RESPONSE", "Invalid response from UPower.") from exc


def power_source() -> str:
    on_battery = properties(ROOT, UPOWER).get("OnBattery")
    if not isinstance(on_battery, bool):
        raise PowerError("UNKNOWN_SOURCE", "Cannot determine the power source.")
    return "battery" if on_battery else "ac"


def profile_status() -> tuple[list[str], str]:
    # Straight from the daemon: powerprofilesctl is a PyGObject script that can
    # crash on interpreter shutdown under CPython 3.14 (python/cpython#124619).
    output = run(["busctl", "--system", "--json=short", "get-property", PPD, PPD_PATH, PPD,
                  "ActiveProfile", "Profiles"])
    try:
        lines = [json.loads(line) for line in output.splitlines() if line.strip()]
        active = lines[0]["data"]
        listed = [entry["Profile"]["data"] for entry in lines[1]["data"]]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise PowerError("PROFILES_UNAVAILABLE", "Power profiles are unavailable. Check power-profiles-daemon.") from exc
    available = [profile for profile in PROFILES if profile in listed]
    if not available or active not in available:
        raise PowerError("PROFILES_UNAVAILABLE", "Power profiles are unavailable. Check power-profiles-daemon.")
    return available, active


def apply_profile(profile: str):
    run(["busctl", "--system", "set-property", PPD, PPD_PATH, PPD, "ActiveProfile", "s", profile])


def state_directory() -> Path:
    override = os.environ.get("OMARCHY_POWERPROFILES_STATE_DIR")
    return Path(override) if override else Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / "omarchy/powerprofiles"


def lock_path() -> Path:
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime and Path(runtime).is_dir():
        return Path(runtime) / "foamy-power.lock"
    cache = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))) / "foamy-power"
    cache.mkdir(mode=0o700, parents=True, exist_ok=True)
    return cache / "action.lock"


@contextlib.contextmanager
def action_lock():
    with lock_path().open("a") as lock:
        # Fail promptly when another widget instance is applying a change; do not queue stale intent.
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise PowerError("BUSY", "Another power-profile change is running. Try again.") from exc
        yield


def atomic_default(source: str, profile: str):
    directory = state_directory()
    directory.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".foamy-power-", dir=directory)
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(profile + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, directory / source)
    finally:
        Path(name).unlink(missing_ok=True)


def restore_if_source_changed(previous: str):
    # A cable transition during a manual operation must win over the old source's request.
    for _ in range(3):
        current = power_source()
        if current == previous:
            return
        run(["omarchy-powerprofiles-set", current])
        previous = current
    raise PowerError("SOURCE_UNSTABLE", "Power source keeps changing. Try again when it is stable.")


def change_profile(profile: str, source: str | None = None) -> dict:
    if profile not in PROFILES or source not in (None, "ac", "battery"):
        raise PowerError("INVALID_ARGUMENT", "Invalid power profile or source.")
    with action_lock():
        available, _ = profile_status()
        if profile not in available:
            raise PowerError("PROFILE_UNAVAILABLE", "This power profile is not available on this machine.")
        current = power_source()
        if source is None:
            apply_profile(profile)
            restore_if_source_changed(current)
        else:
            atomic_default(source, profile)
            # Persist the inactive source without briefly applying its profile to the current source.
            try:
                current = power_source()
                if current == source:
                    run(["omarchy-powerprofiles-set", current])
                restore_if_source_changed(current)
            except PowerError as exc:
                raise PowerError("DEFAULT_SAVED_APPLY_FAILED", "Default saved, but the active profile could not be applied. Try again.") from exc
    return {"ok": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    current = commands.add_parser("set")
    current.add_argument("profile", choices=PROFILES)
    default = commands.add_parser("default")
    default.add_argument("source", choices=("ac", "battery"))
    default.add_argument("profile", choices=PROFILES)
    args = parser.parse_args()
    try:
        result = change_profile(args.profile, getattr(args, "source", None))
        print(json.dumps(result, allow_nan=False))
        return 0
    except PowerError as exc:
        print(json.dumps({"ok": False, "error": exc.payload()}))
    except OSError:
        print(json.dumps({"ok": False, "error": {"code": "STATE_WRITE_FAILED", "message": "Cannot save power-profile state. Check directory permissions."}}))
    return 1


if __name__ == "__main__":
    sys.exit(main())
