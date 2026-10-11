# Enhance Audio Manager

Author: roundface

## Introduction

Enhance Audio Manager 1.0 is an NVDA add-on for controlling Windows audio from the keyboard. Manage playback and recording devices, application volume, microphone boost, and NVDA's output device with speech and braille feedback.

Supports NVDA 2026.2. Minimum required version: NVDA 2026.1.1. English and Traditional Chinese interface translations and user guides are included. NVDA selects the language using its own language setting.

## Getting started

Download the installation package from [version 1.0](https://github.com/maydayrag/enhance-audio-manager/releases/tag/v1.0). User guides are included in [English](addon/doc/en/readme.html) and [Traditional Chinese](addon/doc/zh_TW/readme.html).

Open `enhanceAudioManager-1.0.nvda-addon` with NVDA running, follow the installation prompts, and restart NVDA when prompted.

Use the shortcuts below to select a playback device, recording device, or audio application. Then adjust its volume, toggle mute, or change its device as needed. Volume changes use 1% steps. Device and application lists do not wrap; a short beep indicates the beginning or end of a list. Unavailable devices and empty lists are announced.

When NVDA starts, the add-on unmutes active playback devices that are muted.

To customize shortcuts, open NVDA's **Preferences > Input gestures** and find the **Enhance Audio Manager** category. Laptop shortcuts use NVDA's laptop keyboard layout.

## Keyboard shortcuts

In the table below, **Base** means **Ctrl+Windows+Alt**. Numpad keys refer to the numeric keypad.

| Action | Desktop shortcut | Laptop shortcut |
| --- | --- | --- |
| Previous playback device | Base+Numpad 4 | Base+Page Up |
| Next playback device | Base+Numpad 6 | Base+Page Down |
| Previous recording device | Base+Numpad 1 | Base+Home |
| Next recording device | Base+Numpad 3 | Base+End |
| Previous audio application | Base+Numpad 7 | Base+Left Arrow |
| Next audio application | Base+Numpad 9 | Base+Right Arrow |
| Increase selected target's volume | Base+Numpad 8 | Base+Up Arrow |
| Decrease selected target's volume | Base+Numpad 2 | Base+Down Arrow |
| Increase microphone boost | Ctrl+Windows+Numpad 8 | Ctrl+Windows+Up Arrow |
| Decrease microphone boost | Ctrl+Windows+Numpad 2 | Ctrl+Windows+Down Arrow |
| Toggle selected target's mute | Base+Numpad 5 | Base+Space |
| Set selected device as Windows default | Base+Numpad Enter | Base+Enter |
| Next NVDA output device | Base+Numpad Plus | Base+Backslash |
| Previous NVDA output device | Shift+Base+Numpad Plus | Shift+Base+Backslash |
| Lock or unlock default microphone volume | Base+Numpad Delete | Base+Delete |
| Next playback device for selected application | Base+Numpad Multiply | Base+Right Bracket |
| Previous playback device for selected application | Shift+Base+Numpad Multiply | Shift+Base+Right Bracket |
| Next recording device for selected application | Base+Numpad Divide | Base+Left Bracket |
| Previous recording device for selected application | Shift+Base+Numpad Divide | Shift+Base+Left Bracket |
| Reset devices for all audio applications | Base+Numpad Minus | Base+Backspace |
| Toggle default microphone mute | Shift+Base+Numpad 2 | Shift+Base+Down Arrow |
| Toggle default playback device mute | Shift+Base+Numpad 5 | Shift+Base+Up Arrow |
| Toggle foreground application's mute | Shift+Base+Numpad 8 | Shift+Base+Space |

Press the reset shortcut twice quickly to set all audio application volumes to 100% and unmute them.

## Microphone boost

The microphone boost shortcuts use the numeric keypad in NVDA's desktop layout and the arrow keys in NVDA's laptop layout. No device selection is needed first. Each press changes the default microphone's boost by one hardware-supported step, such as 0, 10, 20, or 30 dB, and announces the resulting value. Boost is separate from ordinary microphone volume and its volume lock. If no default microphone or recognizable boost control is available, the add-on announces this.
