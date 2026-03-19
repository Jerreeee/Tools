#Requires AutoHotkey v2.0
; Key remaps for Belgian AZERTY keyboard
;
; Problem this solves:
;   On Belgian AZERTY, AltGr+, and AltGr+; should produce < and >, but Windows
;   does not map these by default. PowerToys Keyboard Manager can remap them,
;   but it inserts the character via Ctrl+V (clipboard paste) and then resets
;   AltGr. This means you cannot type consecutive AltGr combos without releasing
;   and re-pressing AltGr each time, which is slow and annoying.
;
; Why AutoHotkey instead:
;   SendText injects the Unicode character directly via SendInput, no clipboard
;   involved. AltGr stays held, so consecutive combos work naturally.
;   If you previously used PowerToys for this, disable those shortcuts in
;   PowerToys Keyboard Manager before running this script to avoid conflicts.
;
; Why VK codes (vkXX) instead of scan codes (SCXXX):
;   VK (Virtual Key) codes are assigned by Windows based on the active keyboard
;   layout, so vkBE always means the logical "," key on Belgian AZERTY regardless
;   of keyboard brand or hardware. Scan codes identify physical key positions and
;   are consistent too, but VK codes are more semantically correct and portable
;   across non-standard keyboards.
;
; Hotkey prefix syntax:
;   <^>!  = LCtrl + RAlt = physical AltGr
;
; Setup:
;   1. (If using PowerToys) Disable the conflicting shortcuts in PowerToys Keyboard Manager
;   2. Run this script (double-click), or place a shortcut in shell:startup
;      to run it automatically at login

<^>!vkBE::SendText "<"   ; AltGr + , key → <
<^>!vkBF::SendText ">"   ; AltGr + ; key → >
vkDE::SendText "~"        ; ² key (left of 1) → ~
