"""Check query costs and lifecycle behavior without changing real audio."""
import ast
from dataclasses import dataclass
from pathlib import Path
import sys
from threading import Lock
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'addon/globalPlugins/enhanceAudioManager/vendor'))
from comtypes import GUID, COMError, CLSCTX_ALL
from pycaw.api.endpointvolume import IAudioEndpointVolume
from pycaw.api.mmdeviceapi.depend.structures import PROPERTYKEY
from pycaw.constants import DEVICE_STATE, EDataFlow, ERole, STGM
from pycaw.utils import AudioUtilities, AudioDevice


def load_code():
    tree = ast.parse((ROOT / 'addon/globalPlugins/enhanceAudioManager/__init__.py').read_text(encoding='utf-8'))
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name in ('AudioTarget', 'CoreAudioBackend', 'GlobalPlugin')]
    plugin = classes[-1]
    plugin.bases = []
    plugin.body = [n for n in plugin.body if isinstance(n, ast.FunctionDef) and n.name in ('_maintainMicrophoneVolume', '_onMicrophoneTimer', '_toggleMicrophoneVolumeLock', '_select', '_run')]
    ns = dict(dataclass=dataclass, ComGUID=GUID, PROPERTYKEY=PROPERTYKEY, AudioDevice=AudioDevice,
        AudioUtilities=AudioUtilities, COMError=COMError, CLSCTX_ALL=CLSCTX_ALL,
        IAudioEndpointVolume=IAudioEndpointVolume, ERole=ERole, STGM=STGM, EDataFlow=EDataFlow,
        DEVICE_STATE=DEVICE_STATE, DeviceKind=SimpleNamespace(RECORDING=SimpleNamespace(value=1)),
        _ENDPOINT_NOT_FOUND=-2147023728, time=time, log=Mock(), ui=Mock(),
        config=SimpleNamespace(conf={'enhanceAudioManager': {}}), _=lambda s:s)
    module = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), *classes], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), '<performance-test>', 'exec'), ns)
    return ns


class PerformanceTests(unittest.TestCase):
    def setUp(self):
        self.ns = load_code()
        cls = self.ns['CoreAudioBackend']
        self.backend = cls.__new__(cls)

    def test_name_reads_only_one_property_and_clears_variant(self):
        endpoint = Mock()
        endpoint.GetId.return_value = 'endpoint-id'
        variant = endpoint.OpenPropertyStore.return_value.GetValue.return_value
        variant.GetValue.return_value = 'Microphone'
        device = self.backend._namedDevice(endpoint)
        self.assertEqual(device.FriendlyName, 'Microphone')
        endpoint.OpenPropertyStore.return_value.GetValue.assert_called_once()
        endpoint.OpenPropertyStore.return_value.GetCount.assert_not_called()
        endpoint.OpenPropertyStore.return_value.GetAt.assert_not_called()
        variant.clear.assert_called_once()

    def test_variant_cleared_on_conversion_error(self):
        endpoint = Mock()
        variant = endpoint.OpenPropertyStore.return_value.GetValue.return_value
        variant.GetValue.side_effect = ValueError('Bad property')
        with self.assertRaises(ValueError):
            self.backend._namedDevice(endpoint)
        variant.clear.assert_called_once()

    def test_poll_resolves_new_default_without_reading_properties(self):
        endpoints = [Mock(), Mock()]
        enum = Mock()
        enum.GetDefaultAudioEndpoint.side_effect = endpoints
        with patch.object(AudioUtilities, 'GetDeviceEnumerator', return_value=enum), patch.object(AudioUtilities, 'CreateDevice') as create:
            targets = [self.backend.getDefaultDevice(self.ns['DeviceKind'].RECORDING, includeName=False) for _ in endpoints]
        create.assert_not_called()
        for endpoint, target in zip(endpoints, targets):
            endpoint.OpenPropertyStore.assert_not_called()
            self.assertIs(target.volumeInterface, endpoint.Activate.return_value.QueryInterface.return_value)

    def make_plugin(self):
        p = self.ns['GlobalPlugin']()
        p._backend = Mock()
        p._backend.getDefaultDevice.return_value = SimpleNamespace(name='Mic', volume=35)
        p._microphoneVolumeLocked = False
        p._microphoneStateLock = Lock()
        p._microphoneTimer = Mock()
        p._microphoneExecutor = Mock()
        p._microphoneFuture = None
        p._lastLockErrorTime = 0
        return p

    def test_lock_starts_timer_and_unlock_stops_timer(self):
        p = self.make_plugin()
        p._toggleMicrophoneVolumeLock()
        p._microphoneTimer.Start.assert_called_once_with(100)
        self.assertEqual(p._lockedMicrophoneVolume, 35)
        p._toggleMicrophoneVolumeLock()
        p._microphoneTimer.Stop.assert_called_once()
        self.assertFalse(p._microphoneVolumeLocked)

    def test_no_background_jobs_when_unlocked_or_already_running(self):
        p = self.make_plugin()
        p._onMicrophoneTimer(None)
        p._microphoneVolumeLocked = True
        p._microphoneFuture = Mock()
        p._microphoneFuture.done.return_value = False
        p._onMicrophoneTimer(None)
        p._microphoneExecutor.submit.assert_not_called()

    def test_inflight_poll_does_not_write_after_unlock(self):
        p = self.make_plugin()
        target = Mock(volume=20)
        p._backend.getDefaultDevice.return_value = target
        p._lockedMicrophoneVolume = 70
        with patch('comtypes.CoInitialize'), patch('comtypes.CoUninitialize') as uninit:
            p._maintainMicrophoneVolume()
        target.setVolume.assert_not_called()
        uninit.assert_called_once()

    def test_enabled_poll_uses_lightweight_query_and_corrects_volume(self):
        p = self.make_plugin()
        p._microphoneVolumeLocked = True
        p._lockedMicrophoneVolume = 70
        target = Mock(volume=20)
        p._backend.getDefaultDevice.return_value = target
        with patch('comtypes.CoInitialize'), patch('comtypes.CoUninitialize'):
            p._maintainMicrophoneVolume()
        p._backend.getDefaultDevice.assert_called_once_with(self.ns['DeviceKind'].RECORDING, includeName=False)
        target.setVolume.assert_called_once_with(70)

    def test_navigation_announces_lock_only_for_default_recording_device(self):
        for locked, recording, default, present in (
            (True, True, True, True), (False, True, True, True),
            (True, True, False, True), (True, False, True, True),
            (True, True, False, False),
        ):
            with self.subTest(locked=locked, recording=recording, default=default, present=present):
                p = self.make_plugin()
                p._microphoneVolumeLocked = locked
                nav = Mock()
                nav.move.return_value = 'Default device, Muted, Mic, volume 35' if present else 'No input devices'
                nav.current = SimpleNamespace(isDefault=default) if present else None
                p._recording = nav if recording else Mock()
                self.ns['ui'].reset_mock()
                p._select(nav, 1)
                expected = nav.move.return_value
                if locked and recording and default and present:
                    expected = 'Locked, ' + expected
                self.ns['ui'].message.assert_called_once_with(expected)
                nav.move.assert_called_once_with(1)
                p._backend.getDefaultDevice.assert_not_called()


if __name__ == '__main__':
    unittest.main()
