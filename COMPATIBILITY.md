# Compatibility Across Linux Distros

## What Works Everywhere (any distro with X11)

### Per-app scaling mechanisms
These are toolkit-level, not distro-specific. They work on any Linux distribution:
- `GDK_DPI_SCALE` — GTK apps
- `QT_SCALE_FACTOR` — Qt apps
- `--force-device-scale-factor` — Electron/Chromium apps
- Wine `LogPixels` registry DPI — Wine apps

### PATH wrappers
`~/.local/bin/scaled/` wrappers work on any distro. The `~/.local/bin` convention is part of the freedesktop.org XDG Base Directory spec and is respected everywhere.

### .desktop file patching
`~/.local/share/applications/` overriding system `.desktop` files is a freedesktop.org standard. All major desktop environments (GNOME, KDE, XFCE, Cinnamon, MATE, etc.) follow it.

### xrandr
Available on all X11-based systems for resolution detection.

### udev
Monitor hotplug detection via udev rules in `/etc/udev/rules.d/` works on all systemd-based distros (which is virtually all modern distros).

## GNOME-Specific Parts

### `app-scaling global` command
This uses `xrandr --scale` to change the display scaling, which works on X11 regardless of desktop environment. However, the *reason* we need it — GNOME's fractional scaling rendering at a higher virtual resolution then downscaling — is GNOME-specific.

Other desktop environments handle fractional scaling differently:
- **KDE Plasma**: Uses its own scaling system via `kscreen` and `~/.config/kdeglobals`. Would need `kscreen-doctor` instead of `xrandr --scale`.
- **XFCE**: Limited fractional scaling support. Uses `xfconf-query` for display settings.
- **Cinnamon**: Has its own fractional scaling via `gsettings` (similar to GNOME but different schema).

### GNOME scaling percentage to xrandr mapping
GNOME maps its UI percentages to specific xrandr scale values (e.g., "150%" in GNOME settings = 1.333x xrandr scale). This mapping is GNOME-internal. The `global-scale` state file stores the user-facing percentage.

## Distro-Specific Assumptions

### Snap app directory
The script searches `/var/lib/snapd/desktop/applications/` for snap-installed apps. This only exists on:
- Ubuntu (default)
- Any distro with snapd installed (Fedora, Arch, etc. can install it)

**For Flatpak-based distros** (Fedora, etc.), you'd need to also search:
- `/var/lib/flatpak/exports/share/applications/`
- `~/.local/share/flatpak/exports/share/applications/`

### Shell config for PATH
The installer appends the PATH export to `~/.bashrc`. This assumes bash as the default shell. Adjustments needed for:
- **Zsh** (default on some distros like macOS, popular on Arch): use `~/.zshrc`
- **Fish**: use `~/.config/fish/config.fish` with `set -gx PATH ~/.local/bin/scaled $PATH`
- **Generic**: `~/.profile` or `~/.bash_profile` (read by login shells on most distros)

### udev rule path
`/etc/udev/rules.d/` is standard on all systemd-based distros. Non-systemd distros (Void Linux with runit, Artix, Devuan) may not have udev — they use `eudev` or `mdev` which are compatible but may behave slightly differently.

## Wayland Caveat

The system currently assumes X11. On Wayland:

### What breaks
- **`xrandr`** does not work on Wayland. Resolution detection and `app-scaling global` would fail.
- **Replacements needed**:
  - `wlr-randr` — for wlroots-based compositors (Sway, Hyprland)
  - `gnome-randr` or `gsettings` — for GNOME on Wayland
  - `kscreen-doctor` — for KDE Plasma on Wayland

### What still works
- `--force-device-scale-factor` — Electron apps work on Wayland (Electron uses Ozone platform layer)
- `GDK_DPI_SCALE` — GTK env vars work on Wayland
- `QT_SCALE_FACTOR` — Qt env vars work on Wayland
- Wine `LogPixels` — Wine manages its own rendering regardless of display server
- PATH wrappers — shell-level, independent of display server
- `.desktop` file patching — freedesktop.org standard, works everywhere

### Summary table

| Component | X11 | Wayland |
|-----------|-----|---------|
| Per-app scaling (GTK, Qt, Electron, Wine) | Works | Works |
| PATH wrappers | Works | Works |
| .desktop patching | Works | Works |
| Resolution detection (`xrandr`) | Works | Needs replacement |
| `app-scaling global` (`xrandr --scale`) | Works | Needs replacement |
| Monitor hotplug (udev) | Works | Works |
| udev handler (calls xrandr) | Works | Needs replacement |

## Porting Checklist

To adapt this system for a different distro/environment:

1. **Non-GNOME desktop**: Replace `xrandr --scale` in `app-scaling global` with the DE's native scaling command
2. **Flatpak instead of Snap**: Add flatpak desktop file directories to `patch-desktop-scaling`
3. **Non-bash shell**: Update `install.sh` to detect the user's shell and append PATH to the right config file
4. **Wayland**: Replace all `xrandr` calls with the appropriate Wayland tool (`wlr-randr`, `gnome-randr`, `kscreen-doctor`)
5. **Non-systemd**: Verify udev/eudev compatibility for the monitor handler, or switch to polling
