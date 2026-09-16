import QtQuick
import qs.Ui

BarWidget {
  id: root
  moduleName: "erning.keylid"

  readonly property var service: bar?.shell?.serviceFor("erning.keylid") ?? null
  readonly property bool locked: service?.disabled === true
  readonly property bool busy: !service || service.busy
  readonly property bool failed: !!service && service.error !== ""

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  BarIconButton {
    id: button
    bar: root.bar
    // Nerd Font: keyboard / keyboard-off.
    text: root.locked ? "󰌐" : "󰌌"
    active: root.locked || root.failed
    dimmed: root.busy || (!root.locked && !root.failed)
    pressable: !root.busy
    tooltipText: {
      if (!root.service) return "Keylid is starting…"
      if (root.service.busy) return "Updating internal keyboard…"
      if (root.failed) return "Keylid: " + root.service.error + "\nClick to retry enabling the keyboard"
      if (!root.service.available) return "Internal keyboard not found — click to check again"
      return root.locked
        ? "Internal keyboard disabled — click to enable"
        : "Internal keyboard enabled — click to disable"
    }
    onPressed: function(mouseButton) {
      if (!root.service || root.busy) return
      if (mouseButton === Qt.RightButton || root.failed) root.service.enable()
      else if (mouseButton === Qt.LeftButton) root.service.toggle()
    }
  }
}
