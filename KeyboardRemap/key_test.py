"""
Key combination tester.
Logs every key combination you press and shows what character it actually produces.

Requirements: pip install keyboard
Note: May need to run as Administrator on Windows.
"""

import sys
import json
import os
import time
import threading
import ctypes
import keyboard

user32 = ctypes.windll.user32

# Virtual key codes
VK_SHIFT    = 0x10
VK_LSHIFT   = 0xA0
VK_RSHIFT   = 0xA1
VK_CONTROL  = 0x11
VK_LCONTROL = 0xA2
VK_RCONTROL = 0xA3
VK_MENU     = 0x12   # Alt
VK_LMENU    = 0xA4
VK_RMENU    = 0xA5   # Right Alt = AltGr on European keyboards
VK_CAPITAL  = 0x14

MAPVK_VSC_TO_VK_EX = 3

KNOWN_LAYOUTS = {
    "00000409": "English (United States) - QWERTY",
    "00000813": "Dutch (Belgium) - AZERTY",
    "0000080C": "French (Belgium) - AZERTY",
    "0000040C": "French (France) - AZERTY",
    "00000407": "German - QWERTZ",
    "00000809": "English (United Kingdom) - QWERTY",
    "00000410": "Italian - QWERTY",
    "0000040A": "Spanish - QWERTY",
}

# Events that arrive within this window are printed as a group (synthetic follow-ups)
SYNTHETIC_WINDOW = 0.07   # 70ms


def get_keyboard_layout():
    buf = ctypes.create_string_buffer(9)
    user32.GetKeyboardLayoutNameA(buf)
    layout_id = buf.value.decode()
    name = KNOWN_LAYOUTS.get(layout_id, "Unknown layout")
    return layout_id, name


def get_hkl():
    thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
    return user32.GetKeyboardLayout(thread_id)


def scan_to_vk(scan_code):
    return user32.MapVirtualKeyExW(scan_code, MAPVK_VSC_TO_VK_EX, get_hkl())


def load_powertoys_shortcuts():
    path = os.path.expandvars(
        r"%LOCALAPPDATA%\Microsoft\PowerToys\Keyboard Manager\default.json"
    )
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        shortcuts = {}
        for entry in data.get("remapShortcutsToText", {}).get("global", []):
            vk_set = frozenset(int(v) for v in entry["originalKeys"].split(";"))
            shortcuts[vk_set] = entry["unicodeText"]
        return shortcuts
    except Exception:
        return {}


def get_output_char(scan_code, shift=False, altgr=False):
    hkl = get_hkl()
    vk_code = user32.MapVirtualKeyExW(scan_code, MAPVK_VSC_TO_VK_EX, hkl)
    if not vk_code:
        return None

    state = (ctypes.c_ubyte * 256)()

    if shift:
        state[VK_SHIFT]   = 0x80
        state[VK_LSHIFT]  = 0x80
    if altgr:
        state[VK_CONTROL]  = 0x80
        state[VK_LCONTROL] = 0x80
        state[VK_MENU]     = 0x80
        state[VK_RMENU]    = 0x80
    if user32.GetKeyState(VK_CAPITAL) & 1:
        state[VK_CAPITAL] = 0x01

    buf = (ctypes.c_wchar * 8)()
    result = user32.ToUnicodeEx(vk_code, scan_code, state, buf, 8, 0, hkl)

    if result > 0:
        return buf.value[:result]
    elif result < 0:
        user32.ToUnicodeEx(vk_code, scan_code, state, buf, 8, 0, hkl)
        return "(dead key)"
    return None


user32.GetAsyncKeyState.restype = ctypes.c_short


def phys(vk):
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def physical_mods():
    altgr = _altgr_physically_held or phys(VK_RMENU)
    shift = phys(VK_SHIFT)
    ctrl  = (phys(VK_LCONTROL) or phys(VK_RCONTROL)) and not altgr
    alt   = phys(VK_LMENU) and not altgr
    return shift, ctrl, alt, altgr


def lookup_powertoys(scan_code):
    vk = scan_to_vk(scan_code)
    if not vk:
        return None
    combo_vks = frozenset([VK_LCONTROL, VK_RMENU, vk])
    return powertoys_shortcuts.get(combo_vks)


# ---------------------------------------------------------------------------
# Grouped output — events within SYNTHETIC_WINDOW of each other are printed
# as one block, with synthetic follow-ups indented.
# ---------------------------------------------------------------------------

_group   = []          # list of (combo, output) tuples
_timer   = None
_lock    = threading.Lock()
_counter = 0


def _flush():
    global _counter
    with _lock:
        if not _group:
            return
        _counter += 1
        first_combo, first_output, first_keycode = _group[0]
        print(f"\n  {_counter:<4} {first_combo:<40}  →  {first_output:<30}  [{first_keycode}]")
        for combo, output, keycode in _group[1:]:
            print(f"       ↳ {combo:<38}  →  {output:<30}  [{keycode}]  ← synthetic")
        _group.clear()


def _queue(combo, output, keycode):
    global _timer
    with _lock:
        _group.append((combo, output, keycode))
    if _timer is not None:
        _timer.cancel()
    _timer = threading.Timer(SYNTHETIC_WINDOW, _flush)
    _timer.daemon = True
    _timer.start()


# ---------------------------------------------------------------------------

MODIFIER_NAMES = {
    "left shift", "right shift", "shift",
    "left ctrl",  "right ctrl",  "ctrl",
    "left alt",   "right alt",   "alt", "altgr", "alt gr",
    "caps lock",
}

held_keys           = set()
powertoys_shortcuts = {}

# After a PowerToys combo fires, suppress its synthetic follow-up events for this window
PT_SUPPRESS_WINDOW = 0.20   # 200ms
_pt_followup = None          # (base_scan_code, expiry_time)

# Track physical AltGr state ourselves — PowerToys clears GetAsyncKeyState(VK_RMENU)
# after intercepting AltGr+X combos, so we can't rely on it alone.
_altgr_physically_held = False
ALTGR_NAMES = {"right alt", "altgr", "alt gr"}


def on_key(event):
    global _pt_followup, _altgr_physically_held
    name = (event.name or "").lower()

    # Track AltGr physical state before any early-return
    if name in ALTGR_NAMES:
        if event.event_type == keyboard.KEY_DOWN:
            _altgr_physically_held = True
        elif event.event_type == keyboard.KEY_UP:
            _altgr_physically_held = False
            held_keys.discard(name)
        return

    if event.event_type == keyboard.KEY_UP:
        held_keys.discard(name)
        return

    if event.event_type != keyboard.KEY_DOWN:
        return

    if not name or name in MODIFIER_NAMES:
        return

    shift, ctrl, alt, altgr = physical_mods()

    # Suppress synthetic artifacts that PowerToys emits after intercepting a combo:
    #   - a Ctrl+V (clipboard paste of the mapped text)
    #   - a bare replay of the original base key (to cancel AltGr state)
    if _pt_followup is not None:
        base_sc, expiry = _pt_followup
        if time.time() < expiry:
            if (ctrl and name == "v") or \
               (event.scan_code == base_sc and not altgr and not ctrl):
                return   # suppress silently
        else:
            _pt_followup = None

    # Suppress key repeat
    if name in held_keys:
        return
    held_keys.add(name)

    # Build readable combo string
    parts = []
    if ctrl:
        parts.append("Ctrl")
    if shift:
        parts.append("Shift")
    if altgr:
        parts.append("AltGr")
    elif alt:
        parts.append("Alt")
    parts.append(event.name)
    combo = "+".join(parts)

    # Determine actual output
    if altgr:
        pt_char = lookup_powertoys(event.scan_code)
        if pt_char:
            output = f"'{pt_char}'  (via PowerToys)"
            # Arm suppression for the synthetic follow-ups PowerToys will now send
            _pt_followup = (event.scan_code, time.time() + PT_SUPPRESS_WINDOW)
        else:
            char = get_output_char(event.scan_code, shift=shift, altgr=True)
            output = f"'{char}'" if char and char.strip() else "(no printable output)"
    else:
        char = get_output_char(event.scan_code, shift=shift, altgr=False)
        if char and char.strip():
            output = f"'{char}'"
        elif char == "(dead key)":
            output = "(dead key)"
        else:
            output = "(no printable output)"

    vk = scan_to_vk(event.scan_code)
    keycode = f"scan=0x{event.scan_code:02X}  vk=0x{vk:02X}" if vk else f"scan=0x{event.scan_code:02X}"
    _queue(combo, output, keycode)


def main():
    global powertoys_shortcuts
    powertoys_shortcuts = load_powertoys_shortcuts()

    layout_id, layout_name = get_keyboard_layout()
    print(f"\n  Detected keyboard layout : {layout_name}  [{layout_id}]")
    print(f"  Caps Lock currently      : {'ON' if user32.GetKeyState(VK_CAPITAL) & 1 else 'off'}")
    print(f"  PowerToys shortcuts loaded: {len(powertoys_shortcuts)}")
    print()
    print(f"  Start typing combinations. Press Ctrl+C to quit.")
    print(f"  {'#':<4} {'Combination':<40}     {'Output':<30}  Keycode")
    print("  " + "─" * 85)

    keyboard.hook(on_key)

    try:
        keyboard.wait()
    except KeyboardInterrupt:
        _flush()
        print("\n  Exiting.")
        sys.exit(0)


if __name__ == "__main__":
    main()
