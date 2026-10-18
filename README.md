# Enhance Audio Manager

Author: roundface

## Introduction

Version: 1.1. Control Windows playback and recording devices, application volume, microphone boost, and NVDA's output device from the keyboard, with speech and braille feedback.

Supports NVDA 2026.2. Minimum required version: NVDA 2026.1.1.

English and Traditional Chinese interface translations and user guides are included. NVDA selects the language using its own language setting.

## Installation and operation

Download the installation package from [version 1.1](https://github.com/maydayrag/enhance-audio-manager/releases/tag/v1.1). User guides are included in [English](addon/doc/en/readme.html) and [Traditional Chinese](addon/doc/zh_TW/readme.html).

Open `enhanceAudioManager-1.1.nvda-addon` with NVDA running, follow the installation prompts, and restart NVDA. Use the shortcuts below to select a playback device, recording device, or audio application, then adjust its volume, mute state, or device. Laptop shortcuts apply to NVDA's laptop keyboard layout.

To reassign any command, open NVDA's **Input gestures** dialog and search for **Enhance Audio Manager**.

Each volume adjustment changes the volume by 1%. After a successful adjustment, NVDA immediately announces the current volume and displays it in braille. Lists do not wrap: trying to move past the first or last item produces a short beep.

After an audio device is connected or disconnected, the add-on refreshes the list of active Windows devices the next time you browse devices or toggle mute. Repeated volume adjustments reuse the current interface; the add-on refreshes it and retries only if that interface becomes invalid.

An empty list is a normal condition and is not written to the NVDA log. Depending on the operation, the add-on announces that there are no playback devices, recording devices, audio applications, or NVDA output devices.

When muting, unmuting, or setting a default device, the add-on announces the status first, followed by the device or application name.

When NVDA starts, the add-on checks all active playback devices, unmutes them, and sets any playback device with zero volume to 50%. Nonzero playback volume is preserved.

## Default keyboard shortcuts

### Desktop layout

- Previous playback device: Control+Windows+Alt+Numpad 4.
- Next playback device: Control+Windows+Alt+Numpad 6.
- Previous recording device: Control+Windows+Alt+Numpad 1.
- Next recording device: Control+Windows+Alt+Numpad 3.
- Previous audio application: Control+Windows+Alt+Numpad 7.
- Next audio application: Control+Windows+Alt+Numpad 9.
- Increase selected target's volume: Control+Windows+Alt+Numpad 8.
- Decrease selected target's volume: Control+Windows+Alt+Numpad 2.
- Increase microphone boost: Control+Windows+Numpad 8.
- Decrease microphone boost: Control+Windows+Numpad 2.
- Toggle selected target's mute: Control+Windows+Alt+Numpad 5.
- Set selected device as Windows default: Control+Windows+Alt+Numpad Enter.
- Next NVDA output device: Control+Windows+Alt+Numpad Plus.
- Previous NVDA output device: Shift+Control+Windows+Alt+Numpad Plus.
- Lock or unlock default microphone volume: Control+Windows+Alt+Numpad Delete.
- Next playback device for selected application: Control+Windows+Alt+Numpad Multiply.
- Previous playback device for selected application: Shift+Control+Windows+Alt+Numpad Multiply.
- Next recording device for selected application: Control+Windows+Alt+Numpad Divide.
- Previous recording device for selected application: Shift+Control+Windows+Alt+Numpad Divide.
- Reset all devices: Control+Windows+Alt+Numpad Minus. Press twice quickly to set playback devices to 50%, application and recording device volumes to 100%, and unmute them all.
- Toggle default microphone mute: Shift+Control+Windows+Alt+Numpad 2.
- Toggle default playback device mute: Shift+Control+Windows+Alt+Numpad 5.
- Toggle foreground application's mute: Shift+Control+Windows+Alt+Numpad 8.


### Laptop layout

- Previous playback device: Control+Windows+Alt+Page Up.
- Next playback device: Control+Windows+Alt+Page Down.
- Previous recording device: Control+Windows+Alt+Home.
- Next recording device: Control+Windows+Alt+End.
- Previous audio application: Control+Windows+Alt+Left Arrow.
- Next audio application: Control+Windows+Alt+Right Arrow.
- Increase selected target's volume: Control+Windows+Alt+Up Arrow.
- Decrease selected target's volume: Control+Windows+Alt+Down Arrow.
- Increase microphone boost: Control+Windows+Up Arrow.
- Decrease microphone boost: Control+Windows+Down Arrow.
- Toggle selected target's mute: Control+Windows+Alt+Space.
- Set selected device as Windows default: Control+Windows+Alt+Enter.
- Next NVDA output device: Control+Windows+Alt+Backslash.
- Previous NVDA output device: Shift+Control+Windows+Alt+Backslash.
- Lock or unlock default microphone volume: Control+Windows+Alt+Delete.
- Next playback device for selected application: Control+Windows+Alt+Right Bracket.
- Previous playback device for selected application: Shift+Control+Windows+Alt+Right Bracket.
- Next recording device for selected application: Control+Windows+Alt+Left Bracket.
- Previous recording device for selected application: Shift+Control+Windows+Alt+Left Bracket.
- Reset all devices: Control+Windows+Alt+Backspace. Press twice quickly to set playback devices to 50%, application and recording device volumes to 100%, and unmute them all.
- Toggle default microphone mute: Shift+Control+Windows+Alt+Down Arrow.
- Toggle default playback device mute: Shift+Control+Windows+Alt+Up Arrow.
- Toggle foreground application's mute: Shift+Control+Windows+Alt+Space.

Press the reset shortcut once to clear saved application playback and recording device preferences, even when no audio applications are currently listed. Press it twice quickly to also set all active playback devices (including speakers and headphones) to 50%, set application sessions and active recording devices to 100%, and unmute them all. If microphone volume lock is enabled, its locked volume becomes 100%. Microphone boost and Windows default device selections remain unchanged.

Turn off NVDA's Input Help with **NVDA+1** before using these commands. While Input Help is on, NVDA describes the shortcut without executing it.
