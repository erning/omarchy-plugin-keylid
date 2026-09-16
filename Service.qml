import QtQuick
import Quickshell
import Quickshell.Hyprland
import Quickshell.Io

Item {
  id: root

  property var shell: null
  property bool available: false
  property bool disabled: false
  property bool busy: false
  property string error: ""
  property bool ready: false
  property bool refreshPending: false
  property bool stopping: false

  readonly property string backendPath: decodeURIComponent(Qt.resolvedUrl("backend.py").toString().replace(/^file:\/\//, ""))

  function request(action) {
    if (root.stopping) return
    if (root.busy) {
      if (action === "reapply") root.refreshPending = true
      return
    }
    if (action === "reapply") action = root.disabled && !root.error ? "disable" : "enable"
    root.busy = true
    root.error = ""
    controller.command = ["python3", "-B", root.backendPath, action]
    commandTimer.restart()
    controller.running = true
  }

  function toggle() { request(root.error || !root.available || root.disabled ? "enable" : "disable") }
  function enable() { request("enable") }

  function finish(exitCode, output) {
    if (root.stopping || !root.busy) return
    commandTimer.stop()
    try {
      let state = JSON.parse(output)
      root.available = state.available === true
      root.disabled = state.disabled === true
      root.error = String(state.error || "")
      if (exitCode !== 0 && !root.error) root.error = "Keyboard command failed"
    } catch (e) {
      root.error = "Invalid response from keyboard command"
    }
    root.ready = true
    root.busy = false
    if (root.refreshPending) {
      root.refreshPending = false
      Qt.callLater(function() { root.request("reapply") })
    }
  }

  Process {
    id: controller
    stdout: StdioCollector { id: commandOutput }
    stderr: SplitParser { onRead: data => console.warn("Keylid:", data) }
    onExited: function(exitCode) { root.finish(exitCode, commandOutput.text) }
  }

  Timer {
    id: commandTimer
    interval: 8000
    onTriggered: {
      // Also handles a command that could not be started at all.
      root.error = "Keyboard command timed out or could not start"
      root.ready = true
      root.busy = false
      root.refreshPending = false
      controller.running = false
    }
  }

  Connections {
    target: Hyprland
    function onRawEvent(event) {
      if (event && event.name === "configreloaded") root.request("reapply")
    }
  }

  IpcHandler {
    target: "erning.keylid"
    function status(): string {
      return JSON.stringify({ available: root.available, disabled: root.disabled, busy: root.busy, error: root.error })
    }
    function enable(): void { root.enable() }
    function toggle(): void { root.toggle() }
  }

  Component.onCompleted: root.enable()
  Component.onDestruction: {
    root.stopping = true
    // Best effort only. Call hyprctl directly so removing the plugin directory
    // cannot remove the helper before it starts. Keep the names in sync with backend.py.
    Quickshell.execDetached([
      "hyprctl", "eval",
      'hl.device({ name = "apple-inc.-apple-internal-keyboard-/-trackpad", enabled = true }); '
        + 'hl.device({ name = "apple-spi-keyboard", enabled = true })'
    ])
  }
}
