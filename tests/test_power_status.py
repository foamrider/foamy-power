import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("power_status", Path(__file__).parents[1] / "power_status.py")
power = importlib.util.module_from_spec(spec)
spec.loader.exec_module(power)


class BatteryTests(unittest.TestCase):
    def device(self, **values):
        return {"IsPresent": True, "Type": 2, "Percentage": 68, "State": 1,
                "EnergyRate": 24.6, "EnergyFull": 57, "TimeToFull": 2520,
                "TimeToEmpty": 11520, **values}

    def test_full_tolerance_does_not_invent_limit(self):
        for charge in (97, 98, 99, 100):
            self.assertEqual(power.battery_state(self.device(State=4, Percentage=charge), "ac", 100), "charged")
            self.assertEqual(power.battery_state(self.device(State=4, Percentage=charge), "ac", None), "charged")

    def test_actual_limit_and_unknown_telemetry(self):
        self.assertEqual(power.battery_state(self.device(State=4, Percentage=80), "ac", 80), "holding")
        self.assertEqual(power.battery_state(self.device(State=5), "ac", None), "connected")
        self.assertEqual(power.battery_state(self.device(Percentage=80, EnergyRate=None, TimeToFull=None), "ac", 80), "charging")
        self.assertEqual(power.battery_state(self.device(Percentage=80, EnergyRate=0.1), "ac", 80), "holding")
        self.assertEqual(power.battery_state(self.device(State=4, Percentage=80), "battery", 80), "discharging")

    @patch.object(power, "sysfs_number", return_value=None)
    def test_multiple_packs_do_not_use_first_pack_metadata(self, _read):
        packs = [{"NativePath": "BAT0", "ChargeEndThreshold": 80, "ChargeCycles": 186},
                 {"NativePath": "BAT1", "ChargeEndThreshold": 100, "ChargeCycles": 45}]
        value = power.normalize_battery(self.device(State=4, Percentage=97), packs, "ac")
        self.assertIsNone(value["threshold"])
        self.assertIsNone(value["cycles"])
        self.assertEqual(value["state"], "charged")
        self.assertEqual(value["capacity"], 57)

    def test_no_battery_or_ups_does_not_become_system_battery(self):
        self.assertEqual(power.normalize_battery({}, [], "ac"), {"present": False})
        self.assertEqual(power.normalize_battery(self.device(Type=3), [], "ac"), {"present": False})

    def test_invalid_readings_remain_unknown(self):
        for value in (True, "42", float("nan"), float("inf"), -1):
            self.assertIsNone(power.number(value))
        self.assertIsNone(power.sysfs_number("../../etc", "cycle_count"))


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = patch.dict(os.environ, {"OMARCHY_POWERPROFILES_STATE_DIR": self.tmp.name})
        env.start(); self.addCleanup(env.stop)
        status = patch.object(power, "profile_status", return_value=(list(power.PROFILES), "balanced"))
        status.start(); self.addCleanup(status.stop)

    def test_current_selection_preserves_defaults(self):
        power.atomic_default("ac", "performance")
        with patch.object(power, "power_source", return_value="ac"), patch.object(power, "run") as run:
            power.change_profile("balanced")
        run.assert_called_once_with(["powerprofilesctl", "set", "balanced"])
        self.assertEqual(power.read_default("ac", list(power.PROFILES)), "performance")

    def test_inactive_default_never_applies(self):
        with patch.object(power, "power_source", return_value="ac"), patch.object(power, "run") as run:
            power.change_profile("power-saver", "battery")
        run.assert_not_called()
        self.assertEqual((Path(self.tmp.name) / "battery").read_text(), "power-saver\n")

    def test_active_default_applies(self):
        with patch.object(power, "power_source", return_value="ac"), patch.object(power, "run") as run:
            power.change_profile("performance", "ac")
        run.assert_called_once_with(["omarchy-powerprofiles-set", "ac"])

    def test_source_transition_wins_over_manual_request(self):
        with patch.object(power, "power_source", side_effect=["ac", "battery", "battery"]), patch.object(power, "run") as run:
            power.change_profile("performance")
        self.assertEqual([call.args[0] for call in run.call_args_list],
                         [["powerprofilesctl", "set", "performance"], ["omarchy-powerprofiles-set", "battery"]])

    def test_unknown_source_does_not_write_default(self):
        with patch.object(power, "power_source", side_effect=power.PowerError("UNKNOWN_SOURCE", "Unknown")):
            with self.assertRaises(power.PowerError):
                power.change_profile("balanced", "ac")
        self.assertFalse((Path(self.tmp.name) / "ac").exists())

    def test_failed_apply_reports_saved_default(self):
        with patch.object(power, "power_source", return_value="ac"), patch.object(power, "run", side_effect=power.PowerError("COMMAND_FAILED", "Failed")):
            with self.assertRaises(power.PowerError) as error:
                power.change_profile("balanced", "ac")
        self.assertEqual(error.exception.code, "DEFAULT_SAVED_APPLY_FAILED")
        self.assertEqual((Path(self.tmp.name) / "ac").read_text(), "balanced\n")

    def test_unavailable_profile_cannot_be_saved(self):
        with patch.object(power, "profile_status", return_value=(["balanced"], "balanced")):
            with self.assertRaises(power.PowerError):
                power.change_profile("performance", "ac")
        self.assertFalse((Path(self.tmp.name) / "ac").exists())

    def test_duplicate_operation_is_rejected(self):
        with power.action_lock():
            with self.assertRaises(power.PowerError) as error:
                power.change_profile("balanced")
        self.assertEqual(error.exception.code, "BUSY")

    def test_defaults_match_omarchy_and_are_read_only(self):
        self.assertEqual(power.read_default("ac", list(power.PROFILES)), "performance")
        self.assertEqual(power.read_default("battery", list(power.PROFILES)), "balanced")
        self.assertEqual(power.read_default("ac", ["power-saver", "balanced"]), "balanced")
        self.assertEqual(list(Path(self.tmp.name).iterdir()), [])


class BoundaryTests(unittest.TestCase):
    def test_service_failure_keeps_battery_independent(self):
        with patch.object(power, "power_source", return_value="ac"), patch.object(power, "read_battery", return_value={"present": False}), patch.object(power, "profile_status", side_effect=power.PowerError("PROFILES_UNAVAILABLE", "Profiles unavailable")):
            value = power.snapshot()
        self.assertEqual(value["battery"], {"present": False})
        self.assertEqual(value["profiles"], [])
        self.assertEqual(value["errors"][0]["code"], "PROFILES_UNAVAILABLE")

    def test_real_busctl_response_format(self):
        with patch.object(power, "run", return_value='{"type":"a{sv}","data":[{"OnBattery":{"type":"b","data":true}}]}'):
            self.assertEqual(power.power_source(), "battery")

    def test_real_profiles_format(self):
        with patch.object(power, "run", return_value="* performance:\n    CpuDriver: intel_pstate\n  balanced:\n  power-saver:\n"):
            self.assertEqual(power.profile_status(), (list(power.PROFILES), "performance"))


if __name__ == "__main__":
    unittest.main()
