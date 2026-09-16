# Keylid

A small Omarchy bar plugin that toggles the MacBook internal keyboard.

Hover over the center of the bar, near the clock, to reveal the keyboard icon.
Click it to disable or enable the internal keyboard. While the keyboard is
enabled, the icon collapses when you leave the bar, like Omarchy's indicators.
When disabled or an error occurs, the icon stays visible in the theme's attention
color. Right-click always enables the keyboard. All monitors share one QML service.

The widget uses Omarchy's indicator font size and spacing. Keep it in the center
section so it shares the indicators' hover-to-reveal behavior.

Version 0.1 targets Omarchy 4.0, Quickshell 0.3.1 and Hyprland's Lua configuration
API (0.56). It uses Python 3's standard library and `hyprctl`; no root access is
needed. It only targets exact matches in the `keyboards` list from
`hyprctl devices -j` for these names:

- `apple-inc.-apple-internal-keyboard-/-trackpad`
- `apple-spi-keyboard`

The trackpad, Touch Bar and external keyboards remain available. Other keyboard
names are not supported; the tooltip reports when no supported keyboard is found.

There is no persistent helper process. The service keeps state inside Omarchy's
existing shell and runs a short-lived Python command on startup, on each click,
and when Hyprland reloads its configuration.

## Local installation

Run from the project directory. The destination must not already exist.

```bash
omarchy plugin validate "$PWD"
mkdir -p ~/.config/omarchy/plugins
ln -sT "$PWD" ~/.config/omarchy/plugins/erning.keylid
omarchy shell shell rescanPlugins
omarchy plugin enable erning.keylid --after omarchy.indicators
```

Reload after editing:

```bash
omarchy shell shell rescanPlugins
```

To install from Git and place Keylid immediately after the indicators, to the
left of the clock:

```bash
omarchy plugin add https://github.com/erning/omarchy-plugin-keylid.git
omarchy plugin enable erning.keylid --after omarchy.indicators
```

The `add` command may offer to enable the plugin and choose a bar section; the
following `enable` command sets its exact position. `add --enable` alone uses
Omarchy's default position within the center section, which may be to the right
of the clock. To reposition an existing installation, use the same `enable`
command with `--after omarchy.indicators`.

Update a Git installation with `omarchy plugin update erning.keylid`.

## Disable or uninstall

```bash
omarchy plugin disable erning.keylid
omarchy plugin enable erning.keylid
omarchy plugin remove erning.keylid
```

Disabling or removing the plugin makes one best-effort attempt to enable the
keyboard. Removing a symlink installation only removes the link; the project
directory stays intact.

## State and recovery

The keyboard starts enabled. No disabled state is saved across plugin restarts
or login sessions. Hyprland config reloads reapply the current choice. This only
controls input inside Hyprland, not the Linux console or another login session.

Hyprland 0.56.2 does not expose the keyboard's enabled state in its device list.
The icon shows the last acknowledged Keylid command, not an independently read
hardware state. Avoid changing this same device through another tool while
Keylid is active.

Normal unload sends a detached `hyprctl` enable command. There is no watchdog,
session lock or cleanup retry. Recovery is not guaranteed if the shell crashes,
Hyprland is unresponsive, or unload overlaps a running command. If needed, use
one of the recovery commands below.

To request recovery through the running plugin:

```bash
omarchy shell erning.keylid enable
omarchy shell erning.keylid status
```

If the plugin is unavailable, run from the project directory:

```bash
python3 backend.py enable
```

Equivalent direct recovery command:

```bash
hyprctl eval 'hl.device({ name = "apple-inc.-apple-internal-keyboard-/-trackpad", enabled = true }); hl.device({ name = "apple-spi-keyboard", enabled = true })'
```

## Development checks

```bash
omarchy plugin validate .
python3 -B -m unittest discover -s tests -v
python3 -B tests/qml_smoke.py
```

The tests substitute a fake `hyprctl`; they do not disable real input devices.
