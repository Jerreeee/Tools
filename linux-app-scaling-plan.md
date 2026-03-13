# Linux Per-App Scaling System — Planning Notes

## System Info

- **Ubuntu 24.04.3 LTS** (Noble Numbat)
- **GNOME 46.0 on X11**
- **3840x2160** (4K) monitor, 708mm x 399mm
- Fractional scaling enabled (`x11-randr-fractional-scaling`)
- Display scale: 150% (renders at 5120x2880, downscales to 3840x2160)
- `text-scaling-factor`: 1.25
- `scaling-factor`: 0

## Problem

On a 4K monitor with 150% GNOME scaling, GTK/GNOME apps scale fine but many third-party apps (Qt, Electron) remain tiny. Need a per-application scaling system that also adapts to different screen resolutions (e.g., 1080p vs 4K).

## What `text-scaling-factor` does

`gsettings set org.gnome.desktop.interface text-scaling-factor 1.25` sets a **global GNOME text scaling multiplier**. It tells all GTK-based apps to render text 1.25x larger. It is NOT per-application — it affects everything using GTK/GNOME settings. VS Code respects it because Electron reads GTK settings for font sizing.

## Three UI Toolkits on Linux

| Toolkit | Apps | Scaling env var |
|---------|------|-----------------|
| **GTK** (3/4) | Files, Settings, Firefox, GIMP | `GDK_SCALE`, `GDK_DPI_SCALE` |
| **Qt** (5/6) | KDE apps, VLC, VirtualBox, OBS | `QT_SCALE_FACTOR`, `QT_AUTO_SCREEN_SCALE_FACTOR` |
| **Electron/Chromium** | VS Code, Slack, Discord, Spotify, Chrome | `--force-device-scale-factor=X` flag |

## All Known Scaling Mechanisms

| Method | What it does | Scope |
|--------|-------------|-------|
| `gsettings ... text-scaling-factor` | Scales text in GTK/GNOME apps | Global |
| `GDK_SCALE=2` | Integer scaling for GTK apps | Per-launch |
| `GDK_DPI_SCALE=1.5` | Fractional DPI for GTK3 | Per-launch |
| `QT_SCALE_FACTOR=1.5` | Fractional scaling for Qt apps | Per-launch |
| `QT_AUTO_SCREEN_SCALE_FACTOR=1` | Qt auto-detects DPI | Per-launch |
| `--force-device-scale-factor=1.5` | Chromium/Electron scaling | Per-launch |
| `Xft.dpi` in `~/.Xresources` | X11-level DPI (affects many apps) | Global |
| `xrandr --dpi 192` | Sets X11 DPI globally | Global |

## The Plan

### Phase 1: Identify problem apps
Figure out which apps are misbehaving and what toolkit they use:
```bash
ldd $(which vlc) | grep -E "Qt|gtk"
```

### Phase 2: Central config + launcher script

**`~/.config/app-scaling/scales.conf`**:
```ini
# app-name = scale_factor : toolkit
# toolkit: gtk | qt | electron
code = 1.4 : electron
slack = 1.5 : electron
discord = 1.4 : electron
spotify = 1.4 : electron
vlc = 1.5 : qt
obs = 1.5 : qt
virtualbox = 1.5 : qt
```

**`~/.local/bin/scaled-launch`** (launcher script):
```bash
#!/bin/bash
APP_NAME="$1"
shift
CONFIG="$HOME/.config/app-scaling/scales.conf"

LINE=$(grep "^$APP_NAME " "$CONFIG" 2>/dev/null)
if [[ -z "$LINE" ]]; then
    exec "$APP_NAME" "$@"
fi

SCALE=$(echo "$LINE" | sed 's/.*= *\([0-9.]*\).*/\1/')
TOOLKIT=$(echo "$LINE" | sed 's/.*: *\(.*\)/\1/' | tr -d ' ')

case "$TOOLKIT" in
    gtk)
        export GDK_SCALE=$SCALE
        export GDK_DPI_SCALE=$SCALE
        exec "$APP_NAME" "$@"
        ;;
    qt)
        export QT_SCALE_FACTOR=$SCALE
        exec "$APP_NAME" "$@"
        ;;
    electron)
        exec "$APP_NAME" --force-device-scale-factor="$SCALE" "$@"
        ;;
esac
```

### Phase 3: Auto-detect screen resolution
Extend config to support per-resolution scaling:
```ini
# app-name = scale_1080p / scale_4k : toolkit
code = 1.0 / 1.4 : electron
slack = 1.0 / 1.5 : electron
vlc = 1.0 / 1.5 : qt
```
Script detects resolution via `xrandr` and picks the right column.

### Phase 4: Hook into .desktop files
Override system .desktop files so app launcher icons use scaling too:
```bash
cp /usr/share/applications/code.desktop ~/.local/share/applications/
# Change Exec line to: Exec=scaled-launch code %F
```

### Phase 5: Auto-switch on monitor change (optional)
Use `xrandr` events or `udev` rules to detect monitor changes and update global GNOME scaling automatically.

## TODO
- [ ] List which specific apps are too small
- [ ] Identify toolkit for each problem app
- [ ] Build the `scaled-launch` script
- [ ] Create the config file
- [ ] Patch `.desktop` files
- [ ] Add resolution auto-detection
