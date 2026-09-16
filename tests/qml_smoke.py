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

  Window {
    id: testWindow
    visible: true
    width: 120
    height: 40
  }

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
    property bool centerSectionRevealHeld: false
    property bool centerHoverRevealSuppressed: false
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
    // Keep the offscreen platform's default pointer away from the test widget;
    // hover is driven explicitly through the bar properties below.
    scene.widget = widgetComponent.createObject(testWindow.contentItem, { bar: fakeBar, x: 60 })
    check(!!scene.widget, "Widget creation failed")
  }

  Timer {
    interval: 50
    running: true
    repeat: true
    onTriggered: {
      if (!scene.service || !scene.service.ready || scene.service.busy) return
      if (scene.phase !== 6) check(scene.service.error === "", scene.service.error)
      check(scene.service.available, "Keyboard not found")
      if (scene.phase === 0) {
        check(!scene.widget.locked, "Widget starts locked")
        check(!scene.widget.visible && scene.widget.implicitWidth === 0,
          "Enabled keyboard should collapse without leaving a horizontal gap")
        fakeBar.centerSectionRevealHeld = true
        scene.phase = 1
      } else if (scene.phase === 1) {
        check(scene.widget.visible && scene.widget.implicitWidth > 0,
          "Hovering the center of the bar should reveal the widget")
        fakeBar.centerHoverRevealSuppressed = true
        scene.phase = 2
      } else if (scene.phase === 2) {
        check(!scene.widget.visible, "Widget should respect suppressed center hover")
        fakeBar.centerHoverRevealSuppressed = false
        fakeBar.centerSectionRevealHeld = false
        scene.phase = 3
      } else if (scene.phase === 3) {
        check(!scene.widget.visible, "Leaving the bar should collapse the widget")
        scene.phase = 4
        scene.service.toggle()
      } else if (scene.phase === 4) {
        check(scene.widget.locked, "Widget did not follow the service")
        check(scene.widget.visible, "Disabled keyboard must remain visible without hover")
        scene.phase = 5
        scene.service.enable()
      } else if (scene.phase === 5) {
        check(!scene.widget.locked, "Widget did not show enabled state")
        check(!scene.widget.visible, "Re-enabling should collapse the widget without hover")
        scene.service.error = "Test error"
        scene.phase = 6
      } else if (scene.phase === 6) {
        check(scene.widget.visible, "An error must keep the widget visible")
        scene.service.error = ""
        fakeBar.vertical = true
        scene.phase = 7
      } else if (scene.phase === 7) {
        check(!scene.widget.visible && scene.widget.implicitHeight === 0,
          "Enabled keyboard should collapse without leaving a vertical gap")
        fakeBar.centerSectionRevealHeld = true
        scene.phase = 8
      } else if (scene.phase === 8) {
        check(scene.widget.visible && scene.widget.implicitHeight > 0,
          "Center hover should also reveal the widget in a vertical bar")
        fakeBar.centerSectionRevealHeld = false
        fakeBar.vertical = false
        scene.phase = 9
        scene.service.toggle()
      } else if (scene.phase === 9) {
        check(scene.widget.locked, "Second disable failed")
        scene.phase = 10
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
            "QT_QUICK_BACKEND": "software",
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
