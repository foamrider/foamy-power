#!/usr/bin/env python3
"""UPower readings and Omarchy-compatible power-profile preferences."""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

PROFILES = ("power-saver", "balanced", "performance")
UPOWER = "org.freedesktop.UPower"
ROOT = "/org/freedesktop/UPower"
DEVICE = UPOWER + ".Device"


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


def number(value, minimum: float = 0, maximum: float = float("inf")):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if math.isfinite(value) and minimum <= value <= maximum else None


def sysfs_number(native: str, filename: str):
    # UPower native paths must name one local supply, never traverse the filesystem.
    if not native or Path(native).name != native or native in (".", ".."):
        return None
    try:
        return number(float((Path("/sys/class/power_supply") / native / filename).read_text()))
    except (OSError, ValueError):
        return None


def battery_state(device: dict, source: str, threshold):
    state = device.get("State")
    percentage = number(device.get("Percentage"), maximum=100)
    rate = number(device.get("EnergyRate"))
    full_time = number(device.get("TimeToFull"))
    if source == "battery" or state == 2:
        return "discharging"
    if threshold is not None and 0 < threshold < 100:
        if state == 5:
            return "holding"
        if state == 4 and percentage is not None and percentage >= threshold - 3:
            return "holding"
        if (state == 1 and percentage is not None and percentage >= threshold - 1
                and ((rate is not None and rate <= 0.2)
                     or (full_time is not None and full_time >= 28800))):
            return "holding"
    return {1: "charging", 4: "charged", 5: "connected", 6: "connected"}.get(state, "connected")


def normalize_battery(display: dict, batteries: list[dict], source: str) -> dict:
    present = display.get("IsPresent") is True and display.get("Type") == 2
    if not present:
        return {"present": False}
    thresholds = []
    cycles = None
    for battery in batteries:
        native = battery.get("NativePath", "")
        threshold = number(battery.get("ChargeEndThreshold"), maximum=100)
        if not threshold:
            threshold = sysfs_number(native, "charge_control_end_threshold")
        thresholds.append(threshold if threshold and threshold <= 100 else None)
        if len(batteries) == 1:
            cycles = number(battery.get("ChargeCycles"))
            if cycles is None:
                cycles = sysfs_number(native, "cycle_count")
    # An aggregate battery must not inherit the first pack's limit or cycle count.
    threshold = thresholds[0] if thresholds and all(v == thresholds[0] for v in thresholds) else None
    state = battery_state(display, source, threshold)
    seconds = display.get("TimeToEmpty") if state == "discharging" else display.get("TimeToFull")
    return {
        "present": True, "percentage": number(display.get("Percentage"), maximum=100),
        "state": state, "capacity": number(display.get("EnergyFull")),
        "rate": number(display.get("EnergyRate")), "seconds": number(seconds),
        "cycles": cycles, "threshold": threshold, "count": len(batteries),
    }


def read_battery(source: str) -> dict:
    display = properties(ROOT + "/devices/DisplayDevice", DEVICE)
    if display.get("IsPresent") is not True or display.get("Type") != 2:
        return {"present": False}
    paths = bus_call(ROOT, UPOWER, "EnumerateDevices")
    if not isinstance(paths, list) or len(paths) > 128:
        raise PowerError("INVALID_RESPONSE", "Invalid device list from UPower.")
    batteries = []
    for path in paths:
        if not isinstance(path, str) or not path.startswith(ROOT + "/devices/"):
            raise PowerError("INVALID_RESPONSE", "Invalid device path from UPower.")
        device = properties(path, DEVICE)
        if device.get("Type") == 2 and device.get("PowerSupply") is True and device.get("IsPresent") is True:
            batteries.append(device)
    return normalize_battery(display, batteries, source)


def profile_status() -> tuple[list[str], str]:
    output = run(["powerprofilesctl", "list"])
    available = []
    active = ""
    for line in output.splitlines():
        match = re.fullmatch(r"\s*(\*?)\s*(power-saver|balanced|performance):\s*", line)
        if match:
            profile = match[2]
            if profile not in available:
                available.append(profile)
            if match[1]:
                active = profile
    if not available or active not in available:
        raise PowerError("PROFILES_UNAVAILABLE", "Power profiles are unavailable. Check power-profiles-daemon.")
    return [profile for profile in PROFILES if profile in available], active


def state_directory() -> Path:
    override = os.environ.get("OMARCHY_POWERPROFILES_STATE_DIR")
    return Path(override) if override else Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / "omarchy/powerprofiles"


def read_default(source: str, available: list[str]) -> str:
    path = state_directory() / source
    try:
        value = path.read_text().strip()
    except FileNotFoundError:
        value = ""
    except OSError as exc:
        raise PowerError("READ_DEFAULT_FAILED", "Cannot read the saved power-profile defaults.") from exc
    # Match omarchy-powerprofiles-set's effective fallback without creating state on install.
    if value in available:
        return value
    return "performance" if source == "ac" and "performance" in available else "balanced"


def snapshot() -> dict:
    result = {"battery": None, "source": None, "profiles": [], "active": "", "defaults": {}, "errors": []}
    try:
        result["source"] = power_source()
        result["battery"] = read_battery(result["source"])
    except PowerError as exc:
        result["errors"].append(exc.payload())
    try:
        result["profiles"], result["active"] = profile_status()
        result["defaults"] = {source: read_default(source, result["profiles"]) for source in ("ac", "battery")}
    except PowerError as exc:
        result["errors"].append(exc.payload())
    return result


@contextlib.contextmanager
def action_lock():
    directory = state_directory()
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / ".foamy-power.lock").open("a") as lock:
        # Fail promptly when another widget instance is applying a change; do not queue stale intent.
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise PowerError("BUSY", "Another power-profile change is running. Try again.") from exc
        yield


def atomic_default(source: str, profile: str):
    directory = state_directory()
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
            run(["powerprofilesctl", "set", profile])
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
    commands.add_parser("status")
    current = commands.add_parser("set")
    current.add_argument("profile", choices=PROFILES)
    default = commands.add_parser("default")
    default.add_argument("source", choices=("ac", "battery"))
    default.add_argument("profile", choices=PROFILES)
    args = parser.parse_args()
    try:
        result = snapshot() if args.command == "status" else change_profile(args.profile, getattr(args, "source", None))
        print(json.dumps(result, allow_nan=False))
        return 0
    except PowerError as exc:
        print(json.dumps({"ok": False, "error": exc.payload()}))
    except OSError:
        print(json.dumps({"ok": False, "error": {"code": "STATE_WRITE_FAILED", "message": "Cannot save power-profile state. Check directory permissions."}}))
    return 1


if __name__ == "__main__":
    sys.exit(main())
