#!/usr/bin/env python3
"""Apply one keyboard change and exit. No daemon or persistent disable rule."""

import argparse
import json
import subprocess
import sys


DEVICES = (
    "apple-inc.-apple-internal-keyboard-/-trackpad",
    "apple-spi-keyboard",
)
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


def set_enabled(devices, enabled):
    value = "true" if enabled else "false"
    command = "; ".join(
        f'hl.device({{ name = "{name}", enabled = {value} }})' for name in devices
    )
    reply = hyprctl("eval", command)
    # hyprctl can report a Lua error in stdout, even with exit status zero.
    if reply != "ok":
        raise ControlError(reply or "Hyprland did not acknowledge the change")


def keyboard_devices():
    try:
        keyboards = json.loads(hyprctl("devices", "-j"))["keyboards"]
        if not isinstance(keyboards, list):
            raise ValueError("keyboards is not a list")
        names = {k.get("name") for k in keyboards}
        return tuple(name for name in DEVICES if name in names)
    except (ValueError, KeyError, AttributeError, TypeError) as exc:
        raise ControlError("Invalid keyboard list from Hyprland") from exc


def apply(action):
    state = {"available": False, "disabled": None, "error": ""}
    try:
        if action == "enable":
            # Recovery must not depend on a successful device-list query.
            set_enabled(DEVICES, True)
            state["disabled"] = False
        devices = keyboard_devices()
        state["available"] = bool(devices)
        if action == "disable":
            if not state["available"]:
                raise ControlError("Internal keyboard not found")
            set_enabled(devices, False)
            state["disabled"] = True
    except ControlError as exc:
        state["error"] = str(exc)
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("enable", "disable"))
    state = apply(parser.parse_args().action)
    print(json.dumps(state))
    return 1 if state["error"] else 0


if __name__ == "__main__":
    sys.exit(main())
