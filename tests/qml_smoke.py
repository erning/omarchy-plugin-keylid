"""Load the real Omarchy QML components against a fake keyboard controller."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

from test_backend import FAKE_HYPRCTL, ROOT, backend


QML = r'''
import QtQuick
import Quickshell

ShellRoot {
  id: scene
  property var service: null
  property var widget: null
  property int phase: 0

  QtObject {
    id: fakeBar
    property var shell: QtObject {
      function serviceFor(id) { return scene.service }
    }
    property bool vertical: false
    property int barSize: 32
    property color barForeground: "#eeeeee"
    property color urgent: "#ff5555"
    property string fontFamily: "monospace"
    property bool foregroundAnimationEnabled: false
    function registerClickTarget(item) {}
    function unregisterClickTarget(item) {}
    function showTooltip(item, text) {}
    function hideTooltip(item) {}
  }

  function check(value, message) {
    if (!value) {
      console.error("KEYLID_SMOKE_FAILED: " + message)
      Qt.quit()
    }
  }

  Component.onCompleted: {
    let serviceComponent = Qt.createComponent("@ROOT@/Service.qml")
    check(serviceComponent.status === Component.Ready, serviceComponent.errorString())
    scene.service = serviceComponent.createObject(scene)
    check(!!scene.service, "Service creation failed")
    let widgetComponent = Qt.createComponent("@ROOT@/Widget.qml")
    check(widgetComponent.status === Component.Ready, widgetComponent.errorString())
    scene.widget = widgetComponent.createObject(scene, { bar: fakeBar })
    check(!!scene.widget, "Widget creation failed")
  }

  Timer {
    interval: 50
    running: true
    repeat: true
    onTriggered: {
      if (!scene.service || !scene.service.ready || scene.service.busy) return
      check(scene.service.error === "", scene.service.error)
      check(scene.service.available, "Keyboard not found")
      if (scene.phase === 0) {
        check(!scene.widget.locked, "Widget starts locked")
        scene.phase = 1
        scene.service.toggle()
      } else if (scene.phase === 1) {
        check(scene.widget.locked, "Widget did not follow the service")
        scene.phase = 2
        scene.service.enable()
      } else if (scene.phase === 2) {
        check(!scene.widget.locked, "Widget did not show enabled state")
        scene.phase = 3
        scene.service.toggle()
      } else if (scene.phase === 3) {
        check(scene.widget.locked, "Second disable failed")
        scene.phase = 4
        scene.widget.destroy()
        scene.service.destroy()
        scene.widget = null
        scene.service = null
        finish.start()
      }
    }
  }

  Timer {
    id: finish
    interval: 750
    onTriggered: {
      console.log("KEYLID_SMOKE_OK")
      Qt.quit()
    }
  }
  Timer {
    interval: 15000
    running: true
    onTriggered: {
      console.error("KEYLID_SMOKE_FAILED: timed out")
      Qt.quit()
    }
  }
}
'''


def main():
    with tempfile.TemporaryDirectory(prefix="keylid-qml-") as temporary:
        root = Path(temporary)
        for name in ("Ui", "Commons"):
            (root / name).symlink_to(Path("/usr/share/omarchy/shell") / name)
        (root / "shell.qml").write_text(QML.replace("@ROOT@", ROOT.as_uri()))
        fake = root / "hyprctl"
        fake.write_text(FAKE_HYPRCTL)
        fake.chmod(0o755)
        (root / "devices.json").write_text(json.dumps({"keyboards": [{"name": backend.DEVICE}]}))
        env = {
            **os.environ,
            "QT_QPA_PLATFORM": "offscreen",
            "QT_QPA_PLATFORMTHEME": "",
            "PATH": str(root) + os.pathsep + os.environ["PATH"],
            "XDG_RUNTIME_DIR": str(root),
            "XDG_CACHE_HOME": str(root / "cache"),
            "HYPRLAND_INSTANCE_SIGNATURE": "keylid-qml-test",
            "KEYLID_TEST_STATE": str(root),
        }
        result = subprocess.run(
            ["quickshell", "--no-color", "-p", str(root)],
            env=env, capture_output=True, text=True, timeout=20,
        )
        output = result.stdout + result.stderr
        print(output)
        assert result.returncode == 0, result.returncode
        assert "KEYLID_SMOKE_OK" in output
        assert "KEYLID_SMOKE_FAILED" not in output
        # The actual Quickshell destructor must leave the fake keyboard enabled.
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if (root / "enabled").exists() and (root / "enabled").read_text() == "True":
                print("Keyboard restored after QML service destruction.")
                return
            time.sleep(0.05)
        raise AssertionError("Keyboard was not restored after unloading the QML service")


if __name__ == "__main__":
    main()
