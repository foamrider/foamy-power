import importlib.util
import os
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("power_action", Path(__file__).parents[1] / "power_action.py")
power = importlib.util.module_from_spec(spec)
spec.loader.exec_module(power)


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.runtime = tempfile.TemporaryDirectory()
        self.addCleanup(self.runtime.cleanup)
        env = patch.dict(os.environ, {"OMARCHY_POWERPROFILES_STATE_DIR": self.tmp.name, "XDG_RUNTIME_DIR": self.runtime.name})
        env.start(); self.addCleanup(env.stop)
        status = patch.object(power, "profile_status", return_value=(list(power.PROFILES), "balanced"))
        status.start(); self.addCleanup(status.stop)

    def test_current_selection_preserves_defaults(self):
        power.atomic_default("ac", "performance")
        with patch.object(power, "power_source", return_value="ac"), patch.object(power, "run") as run:
            power.change_profile("balanced")
        run.assert_called_once_with(["busctl", "--system", "set-property", "net.hadess.PowerProfiles", "/net/hadess/PowerProfiles", "net.hadess.PowerProfiles", "ActiveProfile", "s", "balanced"])
        self.assertEqual((Path(self.tmp.name) / "ac").read_text(), "performance\n")

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
                         [["busctl", "--system", "set-property", "net.hadess.PowerProfiles", "/net/hadess/PowerProfiles", "net.hadess.PowerProfiles", "ActiveProfile", "s", "performance"], ["omarchy-powerprofiles-set", "battery"]])

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

    def test_lock_stays_out_of_omarchy_state(self):
        with patch.object(power, "power_source", return_value="ac"), patch.object(power, "run"):
            power.change_profile("power-saver", "battery")
        self.assertEqual(sorted(p.name for p in Path(self.tmp.name).iterdir()), ["battery"])
        self.assertTrue((Path(self.runtime.name) / "foamy-power.lock").exists())

    def test_default_creates_missing_state_directory(self):
        nested = Path(self.tmp.name) / "fresh"
        with patch.dict(os.environ, {"OMARCHY_POWERPROFILES_STATE_DIR": str(nested)}):
            power.atomic_default("ac", "balanced")
        self.assertEqual((nested / "ac").read_text(), "balanced\n")


class BoundaryTests(unittest.TestCase):
    def test_real_busctl_response_format(self):
        with patch.object(power, "run", return_value='{"type":"a{sv}","data":[{"OnBattery":{"type":"b","data":true}}]}'):
            self.assertEqual(power.power_source(), "battery")

    def test_real_profiles_format(self):
        reply = ('{"type":"s","data":"performance"}\n'
                 '{"type":"aa{sv}","data":[{"Profile":{"type":"s","data":"power-saver"}},'
                 '{"Profile":{"type":"s","data":"balanced"}},{"Profile":{"type":"s","data":"performance"}}]}\n')
        with patch.object(power, "run", return_value=reply) as run:
            self.assertEqual(power.profile_status(), (list(power.PROFILES), "performance"))
        self.assertNotIn("powerprofilesctl", run.call_args.args[0])

    def test_unusable_profiles_reply(self):
        for reply in ("", "{}", '{"type":"s","data":"turbo"}\n{"type":"aa{sv}","data":[]}'):
            with patch.object(power, "run", return_value=reply):
                with self.assertRaises(power.PowerError):
                    power.profile_status()

    def test_no_status_command(self):
        with patch.object(sys, "argv", ["power_action.py", "status"]), self.assertRaises(SystemExit):
            power.main()


if __name__ == "__main__":
    unittest.main()
