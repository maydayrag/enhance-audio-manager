# Development

## Build and verify

With Python available on PATH, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

The output is `dist/enhanceAudioManager-1.1.nvda-addon`. The build bundles `comtypes 1.4.13`, `pycaw 20251023`, and `psutil 7.2.1`. It uses `polib 1.2.0` to compile the translation catalogs before packaging.

Edit `addon/locale/en/LC_MESSAGES/nvda.po` and `addon/locale/zh_TW/LC_MESSAGES/nvda.po` to maintain translations. English is the source language. The build checks coverage and formatting placeholders and regenerates `nvda.mo`. Localized manifest files provide the translated name and description. User guides are in `addon/doc/en` and `addon/doc/zh_TW`.

`verify_addon.py` checks the final ZIP signature, CRC, manifest version and name, entry points, file list, Python syntax, source equality, and packaged translations. Microphone boost tests cover device selection, hardware steps, limits, channel values, unsupported controls, readback, errors, and COM marshalling.

## Implementation references

The local development workspace includes these required references:

- `../nvda_dev.md`: NVDA API and packaging requirements.
- `../nvda-2026.2-docs/developerGuide.html`: manifest fields, localization, documentation, scripts, and gesture categories.
- `../nvda-addon-dev-guide-wiki/NVDA-Add-on-Development-Guide.md`: add-on structure, packaging, scripts, and translation initialization.
- `../nvda-2026.2-source/source/addonHandler/__init__.py`: manifest identity, `initTranslation`, `getTranslationsInstance`, and localized documentation lookup.
- `../nvda-2026.2-source/source/globalPluginHandler.py`: plugin discovery and loading.
- `../nvda-2026.2-source/source/inputCore.py`: gesture module identity.
- `../nvda-2026.2-source/source/scriptHandler.py` and `../nvda-2026.2-source/source/ui.py`: scripts and speech/braille messages.

The internal add-on ID and configuration section are `enhanceAudioManager`. The plugin module is `globalPlugins.enhanceAudioManager`, with its entry point at `addon/globalPlugins/enhanceAudioManager/__init__.py`.

Microphone boost uses Windows DeviceTopology and IAudioVolumeLevel. Interface definitions were checked against Windows SDK 10.0.28000.0 (`devicetopology.idl` and `ksmedia.h`). Controls must have a recognized boost name and support dB volume; missing or ambiguous controls are rejected.

Automated verification does not replace testing installation, language selection, and shortcuts in a running NVDA instance or testing microphone boost on supported physical hardware.

## Reset verification

- NVDA 2026.2 `source/inputCore.py` (`_inputHelpCaptor`) suppresses command execution during Input Help. The local NVDA log showed the reset gesture being described in this mode.
- `source/scriptHandler.py` documents `getLastScriptRepeatCount`: zero for a first press and one for a repeated press. The reset command keeps the documented single/double press behavior.
- The bundled pycaw `GetAllSessions` reads only the default multimedia playback endpoint. Volume reset therefore enumerates sessions on every active render endpoint through each device's `AudioSessionManager`.
- Microsoft documents [GetSessionEnumerator](https://learn.microsoft.com/en-us/windows/win32/api/audiopolicy/nf-audiopolicy-iaudiosessionmanager2-getsessionenumerator), [SetMasterVolume](https://learn.microsoft.com/en-us/windows/win32/api/audioclient/nf-audioclient-isimpleaudiovolume-setmastervolume), and [SetMute](https://learn.microsoft.com/en-us/windows/win32/api/audioclient/nf-audioclient-isimpleaudiovolume-setmute). Reset uses 1.0 and false, then reads back both values.
- Saved device preferences are cleared without requiring a current audio session. The existing policy interface layout was cross-checked against [EarTrumpet's 21H2 interface](https://github.com/File-New-Project/EarTrumpet/blob/master/EarTrumpet/Interop/MMDeviceAPI/IAudioPolicyConfigFactoryVariantFor21H2.cs); this Windows internal interface remains undocumented by Microsoft.
- `tests/test_reset.py` executes the actual reset methods with simulated endpoints and sessions. It covers multiple endpoints, empty lists, disappeared sessions/devices, failed readback, cached routes, and both press counts without altering the user's audio settings.
- Double-press reset also enumerates all active render and capture endpoints separately using `EDataFlow.eRender` (50%) and `EDataFlow.eCapture` (100%). Each endpoint uses [SetMasterVolumeLevelScalar](https://learn.microsoft.com/en-us/windows/win32/api/endpointvolume/nf-endpointvolume-iaudioendpointvolume-setmastervolumelevelscalar) and `SetMute`, followed by readback. Failed endpoints do not prevent attempts on the remaining endpoints.
- An enabled microphone volume lock is updated to 100 on reset. A shared Python lock serializes this update with background microphone volume writes, so an in-flight poll cannot restore the previous value afterward. Device discovery stays outside this lock. NVDA configuration and spoken feedback remain on the script's main thread.
