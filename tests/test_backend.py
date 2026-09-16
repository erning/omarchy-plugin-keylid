import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("keylid_backend", ROOT / "backend.py")
backend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend)

FAKE_HYPRCTL = r'''#!/usr/bin/env python3
import json, os, pathlib, sys, time
root = pathlib.Path(os.environ["KEYLID_TEST_STATE"])
if sys.argv[1] == "devices":
    print((root / "devices.json").read_text())
elif sys.argv[1] == "eval":
    enabled = "enabled = true" in sys.argv[2]
    with (root / "commands.jsonl").open("a") as f:
        f.write(json.dumps({"enabled": enabled, "lua": sys.argv[2]}) + "\n")
    if not enabled and (root / "delay").exists():
        time.sleep(float((root / "delay").read_text()))
    (root / "enabled").write_text(str(enabled))
    if not enabled and (root / "fail").exists():
        (root / "fail").unlink()
        print("Lua error: test failure")
    else:
        print("ok")
else:
    print("{}")
'''


class BackendCommandTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="keylid-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        fake = self.root / "hyprctl"
        fake.write_text(FAKE_HYPRCTL)
        fake.chmod(0o755)
        self.devices([
            backend.DEVICE, "keychron-k8-keychron-k8", "apple-inc.-touch-bar-display"
        ])
        self.env = {
            **os.environ,
            "PATH": str(self.root) + os.pathsep + os.environ["PATH"],
            "KEYLID_TEST_STATE": str(self.root),
        }

    def devices(self, names):
        (self.root / "devices.json").write_text(json.dumps({
            "keyboards": [{"name": name} for name in names],
            "mice": [{"name": backend.DEVICE}],
        }))

    def run_action(self, action, exit_code=0):
        result = subprocess.run(
            [sys.executable, "-B", str(ROOT / "backend.py"), action],
            env=self.env, stdin=subprocess.DEVNULL, capture_output=True,
            text=True, timeout=5,
        )
        self.assertEqual(result.returncode, exit_code, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def commands(self):
        path = self.root / "commands.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def test_commands_exit_and_change_only_the_internal_keyboard(self):
        self.assertEqual(self.run_action("enable"), {
            "available": True, "disabled": False, "error": ""
        })
        self.assertTrue(self.run_action("disable")["disabled"])
        # Disabling does not require a helper to remain alive.
        self.assertEqual((self.root / "enabled").read_text(), "False")
        self.assertFalse(self.run_action("enable")["disabled"])
        self.assertEqual((self.root / "enabled").read_text(), "True")
        self.assertEqual([c["enabled"] for c in self.commands()], [True, False, True])
        self.assertTrue(all(f'name = "{backend.DEVICE}"' in c["lua"] for c in self.commands()))

    def test_lua_error_with_zero_exit_status_is_not_success(self):
        (self.root / "fail").touch()
        state = self.run_action("disable", exit_code=1)
        self.assertIsNone(state["disabled"])
        self.assertIn("Lua error", state["error"])
        self.assertFalse(self.run_action("enable")["disabled"])
        self.assertEqual((self.root / "enabled").read_text(), "True")

    def test_missing_keyboard_never_disables_a_mouse_or_external_device(self):
        self.devices(["keychron-k8-keychron-k8", backend.DEVICE + "-1"])
        state = self.run_action("disable", exit_code=1)
        self.assertFalse(state["available"])
        self.assertIn("not found", state["error"])
        self.assertEqual(self.commands(), [])
        # Enabling still clears a stale rule if the keyboard has disappeared.
        self.assertFalse(self.run_action("enable")["disabled"])

    def test_malformed_device_list_never_disables(self):
        (self.root / "devices.json").write_text("not json")
        self.assertIn("Invalid keyboard list", self.run_action("disable", 1)["error"])
        self.assertEqual(self.commands(), [])

    def test_recovery_still_enables_when_device_list_is_malformed(self):
        (self.root / "devices.json").write_text("not json")
        state = self.run_action("enable", 1)
        self.assertFalse(state["disabled"])
        self.assertIn("Invalid keyboard list", state["error"])
        self.assertEqual((self.root / "enabled").read_text(), "True")

    def test_timeout_is_reported_without_assuming_a_disabled_state(self):
        (self.root / "delay").write_text("4")
        state = self.run_action("disable", 1)
        self.assertIsNone(state["disabled"])
        self.assertIn("timed out", state["error"])
        self.assertFalse((self.root / "enabled").exists())


class CommandFailureTests(unittest.TestCase):
    def test_missing_hyprctl_is_an_error(self):
        with patch.object(backend.subprocess, "run", side_effect=FileNotFoundError("hyprctl")):
            with self.assertRaises(backend.ControlError):
                backend.set_enabled(False)

    def test_nonzero_exit_status_is_an_error(self):
        result = subprocess.CompletedProcess(["hyprctl"], 1, "", "connection failed")
        with patch.object(backend.subprocess, "run", return_value=result):
            with self.assertRaisesRegex(backend.ControlError, "connection failed"):
                backend.set_enabled(False)


if __name__ == "__main__":
    unittest.main()
