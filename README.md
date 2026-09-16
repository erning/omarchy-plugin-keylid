# Keylid

A small Omarchy bar plugin that toggles the MacBook internal keyboard.

Click the keyboard icon to disable or enable it. The disabled state uses a
keyboard-off icon and the theme's attention color. Right-click always enables
the keyboard. All monitors share one controller.

Version 0.1 targets Omarchy 4.0, Quickshell 0.3.1 and Hyprland's Lua configuration
API (0.56). It uses Python 3's standard library and `hyprctl`; no root access is
needed. The target is the keyboard named
`apple-inc.-apple-internal-keyboard-/-trackpad`, as reported by `hyprctl devices -j`.
The trackpad, Touch Bar and external keyboards remain available.

## Local installation

Run from the project directory. The destination must not already exist.

```bash
omarchy plugin validate "$PWD"
mkdir -p ~/.config/omarchy/plugins
ln -sT "$PWD" ~/.config/omarchy/plugins/erning.keylid
omarchy-shell shell rescanPlugins
omarchy plugin enable erning.keylid --after omarchy.indicators
```

Reload after editing:

```bash
omarchy-shell shell rescanPlugins
```

A published Git repository with `manifest.json` at its root can also be installed
with `omarchy plugin add <git-url> --enable`, and updated with
`omarchy plugin update erning.keylid`.

## Disable or uninstall

```bash
omarchy plugin disable erning.keylid
omarchy plugin enable erning.keylid
omarchy plugin remove erning.keylid
```

Disabling or removing the plugin closes its controller connection. The worker
restores the keyboard before exiting. Removing a symlink installation only
removes the link; the project directory stays intact.

## State and recovery

The keyboard starts enabled. No disabled state is saved across plugin restarts
or login sessions. Hyprland config reloads reapply the current choice. This only
controls input inside Hyprland, not the Linux console or another login session.

Hyprland 0.56.2 does not expose the keyboard's enabled state in its device list.
The icon shows the last acknowledged Keylid command, not an independently read
hardware state. Avoid changing this same device through another tool while
Keylid is active.

The worker survives destruction of Quickshell's managed process and restores
on connection loss, including plugin unload. A session lock serializes workers
during reloads. Restoration requires a responsive Hyprland instance; killing the
worker itself with SIGKILL cannot run cleanup.

To request recovery through the running plugin:

```bash
omarchy-shell keylid enable
omarchy-shell keylid status
```

If the plugin is unavailable, run from the project directory:

```bash
python3 backend.py enable
```

Equivalent direct recovery command:

```bash
hyprctl eval 'hl.device({ name = "apple-inc.-apple-internal-keyboard-/-trackpad", enabled = true })'
```

## Development checks

```bash
omarchy plugin validate .
python3 -B -m unittest discover -s tests -v
python3 -B tests/qml_smoke.py
```

The tests substitute a fake `hyprctl`; they do not disable real input devices.
