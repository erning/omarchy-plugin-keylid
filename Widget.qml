import QtQuick
import qs.Ui

BarWidget {
  id: root
  moduleName: "erning.keylid"

  readonly property var service: bar?.shell?.serviceFor("erning.keylid") ?? null
  readonly property bool locked: service?.disabled === true
  readonly property bool busy: !service || service.busy
  readonly property bool failed: !!service && service.error !== ""
  property bool indicatorHovered: false
  readonly property bool revealInactiveIndicators: indicatorHovered
    || (bar?.centerSectionRevealHeld === true && bar?.centerHoverRevealSuppressed !== true)
  readonly property bool shown: locked || failed || revealInactiveIndicators

  visible: shown
  implicitWidth: vertical ? button.implicitWidth : (shown ? button.implicitWidth : 0)
  implicitHeight: vertical ? (shown ? button.implicitHeight : 0) : barSize

  function setIndicatorItemHovered(hovered) {
    if (hovered) {
      hideTimer.stop()
      indicatorHovered = true
    } else {
      hideTimer.restart()
    }
  }

  Timer {
    id: hideTimer
    interval: 120
    onTriggered: root.indicatorHovered = false
  }

  BarIndicator {
    id: button
    bar: root.bar
    indicatorHost: root
    maintainIndicatorReveal: true
    // Nerd Font: keyboard / keyboard-off.
    activeText: root.locked ? "󰌐" : "󰌌"
    inactiveText: "󰌌"
    active: root.locked || root.failed
    useActiveColor: true
    pressable: !root.busy
    activeTooltipText: {
      if (!root.service) return "Keylid is starting…"
      if (root.service.busy) return "Updating internal keyboard…"
      if (root.failed) return "Keylid: " + root.service.error + "\nClick to retry enabling the keyboard"
      if (!root.service.available) return "Internal keyboard not found — click to check again"
      return root.locked
        ? "Internal keyboard disabled — click to enable"
        : "Internal keyboard enabled — click to disable"
    }
    inactiveTooltipText: activeTooltipText
    onPressed: function(mouseButton) {
      if (!root.service || root.busy) return
      if (mouseButton === Qt.RightButton || root.failed) root.service.enable()
      else if (mouseButton === Qt.LeftButton) root.service.toggle()
    }
  }
}
