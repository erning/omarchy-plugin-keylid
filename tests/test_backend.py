import importlib.util
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import time
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


class BackendLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="keylid-test-")
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
            "XDG_RUNTIME_DIR": str(self.root),
            "HYPRLAND_INSTANCE_SIGNATURE": "keylid-test-session",
            "KEYLID_TEST_STATE": str(self.root),
        }
        self.processes = []

    def tearDown(self):
        for process in self.processes:
            if process.stdin and not process.stdin.closed:
                process.stdin.close()
            try:
                process.wait(timeout=12)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            for stream in (process.stdout, process.stderr):
                if stream and not stream.closed:
                    stream.close()
        self.temp.cleanup()

    def devices(self, names):
        (self.root / "devices.json").write_text(json.dumps({
            "keyboards": [{"name": name} for name in names],
            "mice": [{"name": backend.DEVICE + "-1"}],
        }))

    def start(self):
        process = subprocess.Popen(
            [sys.executable, "-B", str(ROOT / "backend.py"), "serve"],
            env=self.env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True,
        )
        self.processes.append(process)
        return process

    def receive(self, process):
        self.assertTrue(select.select([process.stdout], [], [], 5)[0], "No controller response")
        line = process.stdout.readline()
        self.assertTrue(line, "Controller exited without a response")
        return json.loads(line)

    def send(self, process, action):
        process.stdin.write(json.dumps({"action": action}) + "\n")
        process.stdin.flush()
        return self.receive(process)

    def commands(self):
        path = self.root / "commands.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def until(self, condition):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if condition():
                return
            time.sleep(0.02)
        self.fail("Timed out waiting for keyboard restoration")

    def test_toggle_and_unload_restore_only_the_internal_keyboard(self):
        process = self.start()
        self.assertEqual(self.receive(process), {"available": True, "disabled": False, "error": ""})
        self.assertTrue(self.send(process, "toggle")["disabled"])
        self.assertFalse(self.send(process, "toggle")["disabled"])
        self.assertTrue(self.send(process, "toggle")["disabled"])
        process.stdin.close()
        self.assertEqual(process.wait(timeout=5), 0)
        self.assertEqual((self.root / "enabled").read_text(), "True")
        self.assertTrue(all(f'name = "{backend.DEVICE}"' in c["lua"] for c in self.commands()))

    def test_quickshell_killing_its_managed_process_still_restores(self):
        process = self.start()
        self.receive(process)
        self.send(process, "toggle")
        process.kill()
        process.wait(timeout=5)
        process.stdin.close()
        process.stdout.close()
        self.until(lambda: (self.root / "enabled").read_text() == "True")

    def test_unload_during_disable_waits_then_restores(self):
        process = self.start()
        self.receive(process)
        (self.root / "delay").write_text("0.3")
        process.stdin.write('{"action":"toggle"}\n')
        process.stdin.flush()
        self.until(lambda: any(not c["enabled"] for c in self.commands()))
        process.kill()
        process.wait(timeout=5)
        process.stdin.close()
        process.stdout.close()
        self.until(lambda: len(self.commands()) >= 3 and self.commands()[-1]["enabled"])
        self.until(lambda: (self.root / "enabled").read_text() == "True")

    def test_lua_error_with_zero_exit_status_is_not_success(self):
        process = self.start()
        self.receive(process)
        (self.root / "fail").touch()
        state = self.send(process, "toggle")
        self.assertIsNone(state["disabled"])
        self.assertIn("Lua error", state["error"])
        # An uncertain state always recovers instead of blindly toggling off.
        state = self.send(process, "toggle")
        self.assertFalse(state["disabled"])
        self.assertEqual(state["error"], "")

    def test_missing_keyboard_never_disables_an_external_device(self):
        self.devices(["keychron-k8-keychron-k8", backend.DEVICE + "-1"])
        process = self.start()
        self.assertFalse(self.receive(process)["available"])
        self.assertIn("not found", self.send(process, "toggle")["error"])
        self.assertTrue(all(c["enabled"] for c in self.commands()))

    def test_config_reload_reapplies_current_choice(self):
        process = self.start()
        self.receive(process)
        self.send(process, "toggle")
        (self.root / "enabled").write_text("True")
        self.assertTrue(self.send(process, "reapply")["disabled"])
        self.assertEqual((self.root / "enabled").read_text(), "False")

    def test_new_worker_waits_for_old_worker_cleanup(self):
        first = self.start()
        self.receive(first)
        self.send(first, "toggle")
        second = self.start()
        self.assertFalse(select.select([second.stdout], [], [], 0.2)[0])
        first.stdin.close()
        first.wait(timeout=5)
        self.assertFalse(self.receive(second)["disabled"])
        self.assertTrue(self.send(second, "toggle")["disabled"])
        self.assertEqual((self.root / "enabled").read_text(), "False")

    def test_malformed_device_list_is_reported_without_disabling(self):
        (self.root / "devices.json").write_text("not json")
        process = self.start()
        self.assertIn("Invalid keyboard list", self.receive(process)["error"])
        self.assertEqual(self.commands(), [])

    def test_failed_disable_is_still_restored_on_unload(self):
        process = self.start()
        self.receive(process)
        (self.root / "fail").touch()
        self.send(process, "toggle")
        process.stdin.close()
        process.wait(timeout=5)
        self.assertEqual((self.root / "enabled").read_text(), "True")


class CommandTests(unittest.TestCase):
    def test_hyprctl_timeout_is_an_error(self):
        with patch.object(backend.subprocess, "run", side_effect=subprocess.TimeoutExpired("hyprctl", 3)):
            with self.assertRaises(backend.ControlError):
                backend.set_enabled(False)

    def test_failed_restore_is_retried(self):
        controller = backend.Controller()
        controller.touched = True
        with patch.object(backend, "set_enabled", side_effect=[backend.ControlError("busy"), None]) as apply:
            controller.restore()
        self.assertEqual(apply.call_count, 2)
        apply.assert_called_with(True)


if __name__ == "__main__":
    unittest.main()
