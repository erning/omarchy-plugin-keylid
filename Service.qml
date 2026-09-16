import QtQuick
import Quickshell
import Quickshell.Hyprland
import Quickshell.Io

Item {
  id: root

  property var shell: null
  property bool available: false
  property bool disabled: false
  property bool busy: true
  property string error: ""
  property bool ready: false
  property bool refreshPending: false
  property bool stopping: false

  readonly property string backendPath: decodeURIComponent(Qt.resolvedUrl("backend.py").toString().replace(/^file:\/\//, ""))

  function request(action) {
    if (root.stopping) return
    if (!controller.running) {
      // Restart always starts by enabling the keyboard.
      root.busy = true
      root.ready = false
      root.error = ""
      controller.stdinEnabled = true
      controller.running = true
      startupTimer.restart()
      return
    }
    if (!root.ready || root.busy) {
      if (action === "reapply") root.refreshPending = true
      return
    }
    root.busy = true
    controller.write(JSON.stringify({ action: action }) + "\n")
  }

  function toggle() { request(root.error || !root.available ? "enable" : "toggle") }
  function enable() { request("enable") }

  function acceptState(data) {
    let state
    try { state = JSON.parse(data) } catch (e) {
      root.error = "Invalid response from keyboard controller"
      root.busy = false
      return
    }
    startupTimer.stop()
    root.ready = true
    root.available = state.available === true
    root.disabled = state.disabled === true
    root.error = String(state.error || "")
    root.busy = false
    if (root.refreshPending) {
      root.refreshPending = false
      root.request("reapply")
    }
  }

  Process {
    id: controller
    command: ["python3", "-B", root.backendPath, "serve"]
    stdinEnabled: true
    running: true
    stdout: SplitParser { onRead: data => root.acceptState(data) }
    stderr: SplitParser { onRead: data => console.warn("Keylid:", data) }
    onExited: function(exitCode) {
      root.ready = false
      root.busy = false
      if (!root.stopping) root.error = "Keyboard controller stopped; click to reconnect"
    }
  }

  Timer {
    id: startupTimer
    interval: 12000
    running: true
    onTriggered: {
      if (!root.ready) {
        root.error = "Keyboard controller did not start"
        root.busy = false
        controller.running = false
      }
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

  Component.onDestruction: {
    root.stopping = true
    // EOF asks the independent worker to restore the keyboard and exit.
    controller.stdinEnabled = false
  }
}
