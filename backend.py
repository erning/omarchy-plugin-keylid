#!/usr/bin/env python3
"""Session-only keyboard control. No root access or persistent disable rule."""

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


DEVICE = "apple-inc.-apple-internal-keyboard-/-trackpad"
COMMAND_TIMEOUT = 3


class ControlError(Exception):
    pass


def hyprctl(*args):
    try:
        result = subprocess.run(
            ["hyprctl", *args], stdin=subprocess.DEVNULL, capture_output=True, text=True,
            timeout=COMMAND_TIMEOUT, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ControlError(str(exc)) from exc
    if result.returncode:
        raise ControlError((result.stderr or result.stdout).strip() or "hyprctl failed")
    return result.stdout.strip()


def set_enabled(enabled):
    # The device name is a fixed, verified Hyprland name, never shell input.
    value = "true" if enabled else "false"
    reply = hyprctl("eval", f'hl.device({{ name = "{DEVICE}", enabled = {value} }})')
    # hyprctl can report a Lua error in stdout, even with exit status zero.
    if reply != "ok":
        raise ControlError(reply or "Hyprland did not acknowledge the change")


class Controller:
    def __init__(self):
        self.available = False
        self.disabled = None
        self.desired_disabled = False
        self.touched = False
        self.error = ""

    def probe(self):
        try:
            data = json.loads(hyprctl("devices", "-j"))
            keyboards = data["keyboards"]
            if not isinstance(keyboards, list):
                raise ValueError("keyboards is not a list")
            self.available = any(k.get("name") == DEVICE for k in keyboards)
        except (ValueError, KeyError, AttributeError, TypeError) as exc:
            raise ControlError("Invalid keyboard list from Hyprland") from exc

    def apply(self, disabled):
        # Mark this before issuing the request: a timeout may still have changed
        # Hyprland, so cleanup must attempt to restore even after an error.
        self.touched = True
        self.disabled = None
        set_enabled(not disabled)
        self.disabled = disabled
        self.desired_disabled = disabled

    def handle(self, action):
        self.error = ""
        try:
            if action not in ("enable", "toggle", "reapply", "status"):
                raise ControlError("Unknown keyboard action")
            self.probe()
            if action == "enable":
                # Also clear a stale device rule when the keyboard disappears.
                self.apply(False)
            elif action == "toggle":
                if not self.available:
                    raise ControlError("Internal keyboard not found")
                self.apply(not self.disabled if self.disabled is not None else False)
            elif action == "reapply" and self.available:
                self.apply(self.desired_disabled)
        except ControlError as exc:
            self.error = str(exc)
        return self.status()

    def status(self):
        return {"available": self.available, "disabled": self.disabled, "error": self.error}

    def restore(self):
        if not self.touched:
            return
        for attempt in range(3):
            try:
                set_enabled(True)
                return
            except ControlError as exc:
                if attempt == 2:
                    print(f"Keylid could not restore the keyboard: {exc}", file=sys.stderr)
                else:
                    time.sleep(0.2)


def session_lock():
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    signature = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
    if not runtime or not signature:
        raise ControlError("Keylid requires a running Hyprland session")
    key = hashlib.sha256(signature.encode()).hexdigest()[:16]
    path = Path(runtime) / f"keylid-{key}.lock"
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
    lock = os.fdopen(fd, "w")
    # A hot reload waits until the old worker has restored the keyboard. Never
    # unlink this file: doing so could give two workers different lock inodes.
    deadline = time.monotonic() + 10
    while True:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return lock
        except BlockingIOError:
            if time.monotonic() >= deadline:
                lock.close()
                raise ControlError("Another Keylid controller is still running")
            time.sleep(0.05)


def emit(state):
    print(json.dumps(state), flush=True)


def serve():
    controller = Controller()
    # Quickshell 0.3.1 SIGKILLs Process children when their QML object is
    # destroyed. The wrapper is that child; this worker survives to see EOF on
    # stdin and finish cleanup. The wrapper waits so Process still tracks it.
    worker = os.fork()
    if worker:
        _, status = os.waitpid(worker, 0)
        return os.waitstatus_to_exitcode(status)
    os.setsid()

    def terminate(_signum, _frame):
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGINT, terminate)
    try:
        with session_lock():
            try:
                emit(controller.handle("enable"))
                for line in sys.stdin:
                    try:
                        request = json.loads(line)
                        action = request["action"]
                    except (ValueError, KeyError, TypeError):
                        emit({**controller.status(), "error": "Invalid keyboard request"})
                        continue
                    emit(controller.handle(action))
            finally:
                controller.restore()
    except BrokenPipeError:
        # The UI may already have gone away. Restoration has still run.
        pass
    except (ControlError, OSError) as exc:
        try:
            emit({"available": False, "disabled": None, "error": str(exc)})
        except BrokenPipeError:
            pass
        return 1
    finally:
        # Avoid a second flush of stdout after the reader has disconnected.
        try:
            sys.stdout.flush()
        except BrokenPipeError:
            os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("serve", "enable"))
    args = parser.parse_args()
    if args.action == "serve":
        return serve()
    # Standalone recovery remains usable even if the plugin is unavailable.
    try:
        set_enabled(True)
    except ControlError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
