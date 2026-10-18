"""Exercise the real reset methods without changing the user's audio settings."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
from threading import Lock


SOURCE = Path(__file__).resolve().parents[1] / "addon/globalPlugins/enhanceAudioManager/__init__.py"


def load_reset_code():
    # Extract the actual methods so tests never start an NVDA plugin or audio timer.
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    backend = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "CoreAudioBackend")
    plugin = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "GlobalPlugin")
    plugin.bases = []
    plugin.body = [node for node in plugin.body if isinstance(node, ast.FunctionDef) and node.name in ("script_resetSessions", "_run", "_unmutePlaybackDevicesOnStartup")]
    for method in plugin.body:
        method.decorator_list = []
    module = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), backend, plugin], type_ignores=[])
    namespace = {
        "AudioUtilities": Mock(),
        "EDataFlow": SimpleNamespace(eRender=SimpleNamespace(value=0), eCapture=SimpleNamespace(value=1)),
        "DeviceKind": SimpleNamespace(PLAYBACK=0),
        "config": SimpleNamespace(conf={"enhanceAudioManager": {"microphoneVolume": 40}}),
        "DEVICE_STATE": SimpleNamespace(ACTIVE=SimpleNamespace(value=1)),
        "ISimpleAudioVolume": object(),
        "scriptHandler": Mock(),
        "ui": Mock(),
        "log": Mock(),
        "_": lambda text: text,
    }
    exec(compile(ast.fix_missing_locations(module), str(SOURCE), "exec"), namespace)
    return namespace


class Volume:
    def __init__(self, level=0.25, muted=True, fail=False, ignore=False):
        self.level = level
        self.muted = muted
        self.fail = fail
        self.ignore = ignore

    def SetMasterVolume(self, level, context):
        if self.fail:
            raise OSError("Session has ended")
        if not self.ignore:
            self.level = level

    def SetMute(self, muted, context):
        self.muted = bool(muted)

    def GetMasterVolume(self):
        return self.level

    def GetMute(self):
        return self.muted

    SetMasterVolumeLevelScalar = SetMasterVolume
    GetMasterVolumeLevelScalar = GetMasterVolume


def device_with_sessions(*volumes):
    controls = [None if volume is None else SimpleNamespace(QueryInterface=Mock(return_value=volume)) for volume in volumes]
    enumerator = SimpleNamespace(GetCount=lambda: len(controls), GetSession=lambda index: controls[index])
    return SimpleNamespace(AudioSessionManager=SimpleNamespace(GetSessionEnumerator=lambda: enumerator))


class ResetTests(unittest.TestCase):
    def setUp(self):
        self.code = load_reset_code()
        cls = self.code["CoreAudioBackend"]
        self.backend = cls.__new__(cls)
        self.utilities = self.code["AudioUtilities"]

    def test_reset_covers_multiple_playback_devices_and_unmutes(self):
        speaker, headset = Volume(), Volume(0.6, False)
        self.utilities.GetAllDevices.return_value = [device_with_sessions(speaker), device_with_sessions(headset)]
        self.assertEqual(self.backend.resetAllSessionVolumes(), 2)
        self.assertEqual((speaker.level, speaker.muted), (1.0, False))
        self.assertEqual((headset.level, headset.muted), (1.0, False))
        self.utilities.GetAllDevices.assert_called_once_with(data_flow=0, device_state=1)
        self.utilities.GetAllSessions.assert_not_called()

    def test_no_devices_returns_zero(self):
        self.utilities.GetAllDevices.return_value = []
        self.assertEqual(self.backend.resetAllSessionVolumes(), 0)

    def test_null_and_empty_sessions_are_normal(self):
        self.utilities.GetAllDevices.return_value = [device_with_sessions(None), device_with_sessions()]
        self.assertEqual(self.backend.resetAllSessionVolumes(), 0)

    def test_one_session_failure_does_not_skip_other_sessions(self):
        healthy = Volume()
        self.utilities.GetAllDevices.return_value = [device_with_sessions(Volume(fail=True), healthy)]
        with self.assertRaises(RuntimeError):
            self.backend.resetAllSessionVolumes()
        self.assertEqual((healthy.level, healthy.muted), (1.0, False))

    def test_one_device_failure_does_not_skip_other_devices(self):
        broken = SimpleNamespace(AudioSessionManager=SimpleNamespace(GetSessionEnumerator=Mock(side_effect=OSError("Unplugged"))))
        healthy = Volume()
        self.utilities.GetAllDevices.return_value = [broken, device_with_sessions(healthy)]
        with self.assertRaises(RuntimeError):
            self.backend.resetAllSessionVolumes()
        self.assertEqual((healthy.level, healthy.muted), (1.0, False))

    def test_readback_failure_is_not_reported_as_success(self):
        self.utilities.GetAllDevices.return_value = [device_with_sessions(Volume(ignore=True))]
        with self.assertRaises(RuntimeError):
            self.backend.resetAllSessionVolumes()

    def make_plugin(self, repeat_count):
        plugin = self.code["GlobalPlugin"]()
        plugin._backend = Mock()
        plugin._backend.listSessions.side_effect = AssertionError("Default endpoint must not gate reset")
        plugin._sessionDeviceIndexes = {(123, "playback"): 1}
        plugin._microphoneStateLock = Lock()
        plugin._microphoneVolumeLocked = False
        plugin._lockedMicrophoneVolume = 40
        self.code["scriptHandler"].getLastScriptRepeatCount.return_value = repeat_count
        return plugin

    def test_single_press_clears_saved_routes_without_active_sessions(self):
        plugin = self.make_plugin(0)
        plugin.script_resetSessions(None)
        plugin._backend.resetAllSessionDevices.assert_called_once_with()
        plugin._backend.listSessions.assert_not_called()
        self.assertEqual(plugin._sessionDeviceIndexes, {})
        self.code["ui"].message.assert_called_once_with("Playback and recording devices reset for all audio applications")

    def test_double_press_resets_volume_without_default_endpoint_precheck(self):
        plugin = self.make_plugin(1)
        plugin._backend.resetAllSessionVolumes.return_value = 2
        plugin.script_resetSessions(None)
        plugin._backend.resetAllSessionVolumes.assert_called_once_with()
        plugin._backend.resetAllSessionDevices.assert_not_called()
        plugin._backend.resetAllDeviceVolumes.assert_called_once_with()
        self.code["ui"].message.assert_called_once_with("Playback device volumes set to 50; audio application and recording device volumes set to 100; all unmuted")

    def test_double_press_with_no_sessions_still_resets_devices(self):
        plugin = self.make_plugin(1)
        plugin._backend.resetAllSessionVolumes.return_value = 0
        plugin.script_resetSessions(None)
        plugin._backend.resetAllDeviceVolumes.assert_called_once_with()
        self.code["ui"].message.assert_called_once_with("Playback device volumes set to 50; audio application and recording device volumes set to 100; all unmuted")

    def test_reset_updates_enabled_microphone_lock(self):
        plugin = self.make_plugin(1)
        plugin._microphoneVolumeLocked = True
        plugin.script_resetSessions(None)
        self.assertEqual(plugin._lockedMicrophoneVolume, 100)
        self.assertEqual(self.code["config"].conf["enhanceAudioManager"]["microphoneVolume"], 100)

    def test_reset_keeps_disabled_lock_setting(self):
        plugin = self.make_plugin(1)
        plugin.script_resetSessions(None)
        self.assertEqual(plugin._lockedMicrophoneVolume, 40)
        self.assertFalse(plugin._microphoneVolumeLocked)

    def test_session_failure_still_attempts_device_reset(self):
        plugin = self.make_plugin(1)
        plugin._backend.resetAllSessionVolumes.side_effect = OSError("Disconnected")
        plugin.script_resetSessions(None)
        plugin._backend.resetAllDeviceVolumes.assert_called_once_with()
        self.code["ui"].message.assert_called_once_with("Audio operation failed; details have been written to the NVDA log")

    def test_device_reset_covers_render_and_capture(self):
        volumes = [Volume(), Volume(0.7, False)]
        self.utilities.GetAllDevices.side_effect = [[SimpleNamespace(EndpointVolume=volumes[0])], [SimpleNamespace(EndpointVolume=volumes[1])]]
        self.assertEqual(self.backend.resetAllDeviceVolumes(), 2)
        self.assertEqual([c.kwargs for c in self.utilities.GetAllDevices.call_args_list], [dict(data_flow=0, device_state=1), dict(data_flow=1, device_state=1)])
        self.assertEqual([(v.level, v.muted) for v in volumes], [(0.5, False), (1.0, False)])

    def test_broken_endpoint_does_not_skip_healthy_endpoint(self):
        healthy = Volume()
        self.utilities.GetAllDevices.return_value = [SimpleNamespace(EndpointVolume=v) for v in (Volume(fail=True), healthy)]
        with self.assertRaises(RuntimeError):
            self.backend.resetAllDeviceVolumes()
        self.assertEqual((healthy.level, healthy.muted), (1.0, False))

    def test_endpoint_readback_failure(self):
        self.utilities.GetAllDevices.return_value = [SimpleNamespace(EndpointVolume=Volume(ignore=True))]
        with self.assertRaises(RuntimeError):
            self.backend.resetAllDeviceVolumes()

    def test_reset_failure_keeps_cache_and_reports_failure(self):
        plugin = self.make_plugin(0)
        plugin._backend.resetAllSessionDevices.side_effect = OSError("Policy failed")
        plugin.script_resetSessions(None)
        self.assertTrue(plugin._sessionDeviceIndexes)
        self.code["ui"].message.assert_called_once_with("Audio operation failed; details have been written to the NVDA log")

    def test_startup_unmutes_and_only_raises_exact_zero(self):
        for level in (0, 0.001, 0.3, 1.0):
            for muted in (False, True):
                with self.subTest(level=level, muted=muted):
                    plugin = self.make_plugin(0)
                    volume = Volume(level, muted)
                    target = SimpleNamespace(volumeInterface=volume, setVolume=Mock(side_effect=lambda value: volume.SetMasterVolume(value / 100, None)))
                    plugin._playback = Mock()
                    plugin._backend.listDevices.return_value = [target]
                    plugin._unmutePlaybackDevicesOnStartup()
                    self.assertEqual(volume.level, 0.5 if level == 0 else level)
                    self.assertFalse(volume.muted)
                    plugin._backend.listDevices.assert_called_once_with(0)
                    if level != 0:
                        target.setVolume.assert_not_called()

    def test_startup_continues_after_device_failure(self):
        plugin = self.make_plugin(0)
        plugin._playback = Mock()
        broken = SimpleNamespace(volumeInterface=Mock())
        broken.volumeInterface.GetMasterVolumeLevelScalar.side_effect = OSError("Disconnected")
        healthy = Volume(0, True)
        target = SimpleNamespace(volumeInterface=healthy, setVolume=lambda value: healthy.SetMasterVolume(value / 100, None))
        plugin._backend.listDevices.return_value = [broken, target]
        plugin._unmutePlaybackDevicesOnStartup()
        self.assertEqual((healthy.level, healthy.muted), (0.5, False))

    def test_render_enumeration_failure_still_resets_capture(self):
        healthy = Volume()
        self.utilities.GetAllDevices.side_effect = [OSError("Disconnected"), [SimpleNamespace(EndpointVolume=healthy)]]
        with self.assertRaises(RuntimeError):
            self.backend.resetAllDeviceVolumes()
        self.assertEqual((healthy.level, healthy.muted), (1.0, False))


if __name__ == "__main__":
    unittest.main()
