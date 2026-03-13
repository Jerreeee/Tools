# Linux Per-App Scaling System

## The Problem

On a 4K monitor (3840x2160) with GNOME's 150% fractional scaling enabled, GTK/GNOME-native apps scale correctly, but many third-party apps (Electron, Qt, Wine) render at native resolution and appear tiny/unreadable. GNOME's built-in scaling only affects GTK apps. Each toolkit has its own independent scaling mechanism, so there's no single setting to fix everything.

### System Info
- Ubuntu 24.04.3 LTS, GNOME 46.0 on X11
- 3840x2160 (4K) monitor
- Fractional scaling enabled (`x11-randr-fractional-scaling`)
- Display scale: 150% (renders at 5120x2880, downscales to 3840x2160)
- `text-scaling-factor`: 1.25

## The Goal

A per-app scaling system that:
1. Lets you set a custom scale factor for each app individually
2. Auto-detects the current resolution and picks the right scale (e.g., no scaling on 1080p, 1.4x on 4K)
3. Works both from the terminal AND from the GNOME app launcher ("Show Apps" / Activities)
4. Supports all major Linux UI toolkits: GTK, Qt, Electron, and Wine
5. Can change GNOME's global fractional scaling and automatically adjust per-app factors to compensate
6. Auto-detects monitor changes and adjusts scaling automatically
7. Can be fully reverted with a single command

## How Scaling Works Per Toolkit

Each Linux UI toolkit has its own way of controlling scale. The `scaled-launch` script detects which toolkit an app uses and applies the correct mechanism:

### Electron / Chromium (`electron`)
- **Mechanism**: Command-line flag `--force-device-scale-factor=X`
- **How it works**: Chromium's rendering engine accepts a flag that overrides its DPI detection and renders everything at the given multiplier
- **Stacks with GNOME scaling**: Yes. GNOME 150% + our 1.4x = effective ~210%
- **Apps**: VS Code, Google Chrome, Slack, Discord, Spotify
- **Example**: `code --force-device-scale-factor=1.4`

### Qt (`qt`)
- **Mechanism**: Environment variable `QT_SCALE_FACTOR=X`
- **How it works**: Qt reads this env var at startup and applies it as a global scale multiplier to all widgets, text, and layouts. Supports fractional values.
- **Stacks with GNOME scaling**: Yes
- **Apps**: VLC, OBS, VirtualBox, KDE apps
- **Example**: `QT_SCALE_FACTOR=1.5 vlc`

### GTK (`gtk`)
- **Mechanism**: Environment variable `GDK_DPI_SCALE=X`
- **How it works**: GDK (GTK's drawing layer) uses this to adjust DPI-based rendering. `GDK_SCALE` also exists but only supports integers. We use `GDK_DPI_SCALE` because it supports fractional values like 1.25.
- **Stacks with GNOME scaling**: Yes
- **Apps**: GIMP, Files, most GNOME-native apps (though these usually scale fine already)
- **Example**: `GDK_DPI_SCALE=1.5 gimp`

### Wine (`wine`)
- **Mechanism**: Wine registry `LogPixels` DPI value
- **How it works**: Wine apps (Windows apps running under Wine/snap) don't read Linux env vars. Instead, Wine has its own DPI setting stored in the Windows registry files (`user.reg` and `system.reg`). The base DPI is 96. To scale by 3.0x, we set DPI to 288 (96 * 3.0). The script writes this as a hex dword to the `LogPixels` registry key before launching the app.
- **DOES NOT stack with GNOME scaling**: Wine ignores GNOME's compositor scaling entirely. Wine DPI is absolute. This is why Wine apps are excluded from the `--relative` adjustment when changing GNOME scaling.
- **Wine prefix locations**:
  - Snap apps: `~/snap/<app-name>/common/.wine/`
  - Regular Wine apps: `~/.wine/`
- **Registry files modified**: `user.reg` and `system.reg` (the `LogPixels` dword value)
- **Apps**: Notepad++ (snap), any other Wine-based app
- **Example**: Sets `"LogPixels"=dword:00000120` (288 DPI) for 3.0x scale

### How GNOME Fractional Scaling Works (important context)
GNOME's 150% fractional scaling on X11 works via xrandr: it renders the desktop at a higher virtual resolution (5120x2880 for 150% on 4K) then downscales to the native resolution (3840x2160). This is controlled by `xrandr --output DP-0 --scale 1.5x1.5`. Our per-app scale factors are applied ON TOP of this base scaling for all toolkits except Wine.

### Other global scaling mechanisms (NOT used by this system, listed for reference)
| Method | What it does | Scope |
|--------|-------------|-------|
| `gsettings ... text-scaling-factor` | Scales text in GTK/GNOME apps | Global |
| `GDK_SCALE=2` | Integer-only scaling for GTK apps | Per-launch |
| `QT_AUTO_SCREEN_SCALE_FACTOR=1` | Qt auto-detects DPI | Per-launch |
| `Xft.dpi` in `~/.Xresources` | X11-level DPI (affects many apps) | Global |
| `xrandr --dpi 192` | Sets X11 DPI globally | Global |

## Architecture: How It All Fits Together

There are two ways an app can launch on Linux: from the terminal (typing a command) and from the GUI (clicking an icon in "Show Apps"). This system intercepts both:

```
Terminal launch:              GUI launch (Show Apps):
    |                              |
    v                              v
~/.local/bin/scaled/code      ~/.local/share/applications/code.desktop
(wrapper script)              (patched Exec= line)
    |                              |
    v                              v
    +------> scaled-launch <-------+
                  |
                  v
      reads ~/.config/app-scaling/scales.conf
      (checks [defaults] for empty scales)
      (checks scales.override if it exists)
                  |
                  v
      detects resolution via xrandr
                  |
                  v
      applies toolkit-specific scaling
                  |
                  v
      exec's the real binary
```

Additionally, a udev rule triggers `app-scaling-monitor-handler` on monitor hotplug:
```
Monitor plugged/unplugged
    |
    v
udev rule (99-app-scaling-monitor.rules)
    |
    v
app-scaling-monitor-handler
    |
    v
reads [monitors] section from scales.conf
    |
    v
calls: app-scaling global <target%> --relative
    |
    v
adjusts GNOME scaling + per-app factors
    |
    v
sends desktop notification
```

### Interception Method 1: PATH Wrappers (terminal launches)

**What we did**: Created small wrapper scripts in `~/.local/bin/scaled/` that shadow the real binaries. For example, `~/.local/bin/scaled/code` is a 2-line script that calls `scaled-launch code "$@"`.

**How the hijack works**: We added `~/.local/bin/scaled` to the FRONT of `$PATH` in `~/.bashrc`. When you type `code` in a terminal, bash searches PATH left-to-right, finds our wrapper in `~/.local/bin/scaled/code` before the real `/usr/bin/code`, and runs our wrapper instead. The wrapper delegates to `scaled-launch`, which resolves the real binary by scanning PATH while skipping the wrappers directory.

**Files involved**:
- `~/.local/bin/scaled/<app-name>` — one wrapper per configured app
- `~/.bashrc`: `export PATH="$HOME/.local/bin/scaled:$PATH"`

### Interception Method 2: Patched .desktop Files (GUI launches)

**What we did**: Copied each app's `.desktop` file from the system directory to `~/.local/share/applications/` and rewrote the `Exec=` lines to go through `scaled-launch`.

**How the hijack works**: The freedesktop.org spec says that `.desktop` files in `~/.local/share/applications/` take priority over those in `/usr/share/applications/` and `/var/lib/snapd/desktop/applications/`. So when GNOME's "Show Apps" reads the desktop database, it finds our patched version first. The `Exec=` line now says `Exec=scaled-launch code %F` instead of `Exec=/usr/bin/code %F`.

**Files involved**:
- `~/.local/share/applications/code.desktop` (patched, original in `/usr/share/applications/`)
- `~/.local/share/applications/google-chrome.desktop` (patched, original in `/usr/share/applications/`)
- `~/.local/share/applications/notepad-plus-plus_notepad-plus-plus.desktop` (patched, original in `/var/lib/snapd/desktop/applications/`)

**Source directories searched for originals**:
- `/usr/share/applications/` — standard system apps
- `/var/lib/snapd/desktop/applications/` — snap-installed apps

## All Files in This Project

### Scripts (source in `scripts/`, installed to `~/.local/bin/`)

| Script | Purpose |
|--------|---------|
| `scaled-launch` | Core launcher. Reads config (with `[defaults]` support), detects resolution, applies toolkit-specific scaling, then exec's the real binary. Also checks for `scales.override` (created by `--no-save`). |
| `patch-desktop-scaling` | Copies and patches `.desktop` files to route through `scaled-launch`. Supports `--dry-run` and `--restore`. Searches both system and snap app directories. |
| `generate-wrappers` | Creates PATH wrapper scripts in `~/.local/bin/scaled/`. Supports `--clean` to remove them. |
| `app-scaling` | Management CLI. Subcommands: `setup`, `teardown`, `status`, `test <app>`, `global <pct>`, `migrate`. |
| `app-scaling-monitor-handler` | Triggered by udev on monitor hotplug. Reads `[monitors]` section, calls `app-scaling global` to auto-adjust. |

### Config

| File | Purpose |
|------|---------|
| `config/scales.conf` | Per-app scaling config with `[monitors]`, `[defaults]`, and `[apps]` sections |
| `config/99-app-scaling-monitor.rules` | udev rule template for monitor auto-detection |

### Installer

| File | Purpose |
|------|---------|
| `install.sh` | Copies scripts to `~/.local/bin/`, installs config, adds PATH entry to `~/.bashrc`, auto-migrates old config, optionally installs udev rule (with sudo). |

## Config Format Reference

```ini
[monitors]
# resolution_height = gnome_scaling_percentage
# Used by auto-switch daemon when monitors are plugged/unplugged
2160 = 150
1440 = 125
1080 = 100

[defaults]
# Per-toolkit default scale factors
# Apps with an empty scale value inherit from here
wine = 3.0
# qt = 1.0
# gtk = 1.0
# electron = 1.0

[apps]
# Format: app-name = scale_1080p / scale_4k : toolkit
# Or:     app-name = scale : toolkit               (single factor for all resolutions)
# Or:     app-name = : toolkit                      (use toolkit default from [defaults])
#
# Supported toolkits: gtk | qt | electron | wine
# Comment out with # to disable an app

code          = 1.0 / 1.4 : electron
google-chrome = 1.0 / 1.2 : electron
notepad-plus-plus = : wine              # uses wine default (3.0)
```

**Resolution detection**: uses `xrandr` to find the active resolution height. If >= 2160px, uses the 4K scale factor; otherwise uses the 1080p factor.

**Override file**: If `~/.config/app-scaling/scales.override` exists, `scaled-launch` uses it instead of `scales.conf`. Created by `app-scaling global --no-save`.

## The `app-scaling global` Command

Changes GNOME's fractional scaling and optionally adjusts per-app factors to compensate.

### Usage
```bash
app-scaling global <percentage> [--relative] [--no-save]
```

### Examples
```bash
# Just change GNOME scaling, leave per-app factors alone:
app-scaling global 100

# Change to 100% and multiply all per-app factors by 1.5 to compensate (150/100):
app-scaling global 100 --relative

# Same but don't save the adjusted factors to disk:
app-scaling global 100 --relative --no-save

# Go back to 150% and adjust factors back down:
app-scaling global 150 --relative
```

### How `--relative` works
1. Reads the current GNOME percentage from `~/.config/app-scaling/global-scale`
2. Calculates ratio: `old_percentage / new_percentage` (e.g., 150/100 = 1.5)
3. Multiplies every non-Wine app's scale factor(s) by this ratio
4. **Wine apps are excluded** — Wine DPI is absolute and independent of GNOME scaling
5. Both the 1080p and 4K columns are multiplied
6. Example: VS Code `1.0 / 1.4` with ratio 1.5 becomes `1.5 / 2.1`

### How `--no-save` works
- Writes adjusted factors to `~/.config/app-scaling/scales.override` instead of modifying `scales.conf`
- `scaled-launch` checks for the override file first
- Original `scales.conf` is preserved
- Remove the override: `rm ~/.config/app-scaling/scales.override`

### What it does under the hood
1. Calculates the xrandr scale factor from the percentage
2. Runs: `xrandr --output <output> --scale <factor>x<factor> --mode <native_mode>`
3. Saves the new percentage to `~/.config/app-scaling/global-scale`
4. Regenerates wrappers and desktop patches

## Monitor Auto-Detection

### How it works
A udev rule watches for display hardware changes (monitor plug/unplug). When triggered:
1. The handler script detects the new resolution via `xrandr`
2. Looks up the target GNOME percentage in the `[monitors]` section of `scales.conf`
3. Calls `app-scaling global <target%> --relative` to adjust everything
4. Sends a desktop notification

### udev rule
Installed at: `/etc/udev/rules.d/99-app-scaling-monitor.rules`
```
SUBSYSTEM=="drm", ACTION=="change", RUN+="/home/jeroen/.local/bin/app-scaling-monitor-handler"
```

### Lock mechanism
The handler uses a lock file (`/tmp/app-scaling-monitor.lock`) to prevent duplicate triggers — udev often fires multiple `change` events for a single hotplug.

### Log file
All monitor events are logged to: `~/.config/app-scaling/monitor.log`

## Complete Footprint on the System

Everything this system touches, for a full revert:

### Files added to `~/.local/bin/`
- `~/.local/bin/scaled-launch`
- `~/.local/bin/patch-desktop-scaling`
- `~/.local/bin/generate-wrappers`
- `~/.local/bin/app-scaling`
- `~/.local/bin/app-scaling-monitor-handler`

### Files added to `~/.local/bin/scaled/` (PATH wrappers)
- `~/.local/bin/scaled/code`
- `~/.local/bin/scaled/google-chrome`
- (one file per configured app that's installed)

### Files added to `~/.local/share/applications/` (patched .desktop files)
- `~/.local/share/applications/code.desktop`
- `~/.local/share/applications/google-chrome.desktop`
- `~/.local/share/applications/notepad-plus-plus_notepad-plus-plus.desktop`

### Files added to `~/.config/app-scaling/`
- `~/.config/app-scaling/scales.conf`
- `~/.config/app-scaling/scales.override` (only if `--no-save` was used)
- `~/.config/app-scaling/global-scale` (stores current GNOME scaling percentage)
- `~/.config/app-scaling/monitor.log` (monitor change events log)
- `~/.config/app-scaling/desktop-backups/patched-files.list`

### System-level files (require sudo to remove)
- `/etc/udev/rules.d/99-app-scaling-monitor.rules` (monitor hotplug udev rule)

### Modifications to existing files
- **`~/.bashrc`**: added `export PATH="$HOME/.local/bin/scaled:$PATH"`
- **Wine registry** (for Wine apps only): `~/snap/notepad-plus-plus/common/.wine/user.reg` and `system.reg` — the `LogPixels` dword value is modified each launch

## How to Fully Revert Everything

### Option A: Automated teardown (recommended)
```bash
# Remove wrappers and restore .desktop files
app-scaling teardown

# Refresh the desktop database
update-desktop-database ~/.local/share/applications

# Remove the scripts
rm ~/.local/bin/{scaled-launch,patch-desktop-scaling,generate-wrappers,app-scaling,app-scaling-monitor-handler}

# Remove config and state
rm -rf ~/.config/app-scaling

# Remove the PATH line from ~/.bashrc
# Look for: export PATH="$HOME/.local/bin/scaled:$PATH"
nano ~/.bashrc  # find and delete the line and the comment above it

# Remove the udev rule
sudo rm /etc/udev/rules.d/99-app-scaling-monitor.rules
sudo udevadm control --reload-rules

# Reset Wine DPI back to 96 for notepad-plus-plus
sed -i 's/"LogPixels"=dword:[0-9a-fA-F]*/"LogPixels"=dword:00000060/' \
  ~/snap/notepad-plus-plus/common/.wine/user.reg \
  ~/snap/notepad-plus-plus/common/.wine/system.reg
```

### Option B: Manual cleanup
1. Delete `~/.local/bin/scaled/` (the wrapper directory)
2. Delete the 5 scripts from `~/.local/bin/`
3. Delete patched `.desktop` files from `~/.local/share/applications/` (only the ones listed in `~/.config/app-scaling/desktop-backups/patched-files.list`)
4. Delete `~/.config/app-scaling/`
5. Remove the PATH export line from `~/.bashrc`
6. Run `update-desktop-database ~/.local/share/applications`
7. Remove `/etc/udev/rules.d/99-app-scaling-monitor.rules` (sudo required)
8. Run `sudo udevadm control --reload-rules`
9. For Wine apps: reset `LogPixels` to `dword:00000060` (96 DPI) in the Wine prefix registry files

## How to Add a New App

1. Figure out the toolkit:
   ```bash
   # For GTK/Qt:
   ldd $(which appname) | grep -Ei "qt|gtk"
   # For Electron: check if it's a wrapper script:
   head $(which appname)
   # For Wine/snap: check if it runs a .exe:
   cat /var/lib/snapd/desktop/applications/*appname*.desktop
   ```

2. Add a line to the `[apps]` section in `~/.config/app-scaling/scales.conf`:
   ```ini
   appname = 1.0 / 1.5 : electron   # scale_1080p / scale_4k : toolkit
   # or for a single scale factor on all resolutions:
   appname = 3.0 : wine
   # or to use the toolkit default from [defaults]:
   appname = : wine
   ```

3. Regenerate wrappers and patch desktop files:
   ```bash
   app-scaling setup
   ```
