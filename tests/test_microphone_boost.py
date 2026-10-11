"""Use simulated hardware to verify dB behavior without changing real devices."""
import ctypes
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

PLUGINS = Path(__file__).resolve().parents[1] / "addon/globalPlugins"
sys.path.insert(0, str(PLUGINS / "vendor"))
sys.path.insert(0, str(PLUGINS))
from _audioManager import microphoneBoost as boost
from comtypes import COMObject


class Control:
    def __init__(self, levels=(0,), limits=(0, 30, 10)):
        self.levels = list(levels)
        self.limits = limits
        self.writes = []

    def GetChannelCount(self):
        return len(self.levels)

    def GetLevelRange(self, channel):
        return self.limits

    def GetLevel(self, channel):
        return self.levels[channel]

    def SetLevelAllChannels(self, levels, count, context):
        self.levels = list(levels)
        self.writes.append(self.levels[:])


class ComControl(COMObject):
    # Validate the actual COM method layout, including inherited dB methods.
    _com_interfaces_ = [boost.IAudioVolumeLevel]

    def __init__(self):
        super().__init__()
        self.level = 10.0

    def GetChannelCount(self):
        return 1

    def GetLevelRange(self, channel):
        return 0.0, 30.0, 10.0

    def GetLevel(self, channel):
        return self.level

    def SetLevelAllChannels(self, levels, count, context):
        self.level = levels[0]


class Part:
    def __init__(self, name, control=None):
        self.name = name
        self.control = control

    def GetName(self):
        return self.name

    def Activate(self, *args):
        return self

    def QueryInterface(self, interface):
        return self.control


class BoostTests(unittest.TestCase):
    def test_hardware_steps_and_limits(self):
        for current, direction, expected in [(0, 1, 10), (20, -1, 10), (0, -1, 0), (30, 1, 30)]:
            with self.subTest(current=current, direction=direction):
                control = Control((current,))
                self.assertEqual(boost.changeBoost(control, direction), [expected])

    def test_fractional_steps_and_channels(self):
        control = Control((1.5, 3), (0, 6, 1.5))
        self.assertEqual(boost.changeBoost(control, 1), [3, 4.5])
        self.assertEqual(boost.changeBoost(control, -1), [1.5, 3])

    def test_invalid_range_does_not_write(self):
        for limits in [(0, 30, 0), (30, 0, 10), (0, float("nan"), 10)]:
            control = Control(limits=limits)
            with self.assertRaises(boost.BoostNotSupportedError):
                boost.changeBoost(control, 1)
            self.assertEqual(control.writes, [])

    def test_readback_is_used(self):
        control = Control()
        control.SetLevelAllChannels = lambda *args: setattr(control, "levels", [9.5])
        self.assertEqual(boost.changeBoost(control, 1), [9.5])

    def test_write_error_propagates(self):
        control = Control()
        with patch.object(control, "SetLevelAllChannels", side_effect=RuntimeError("removed")):
            with self.assertRaises(RuntimeError):
                boost.changeBoost(control, 1)

    def test_real_com_marshalling(self):
        server = ComControl()
        pointer = server.QueryInterface(boost.IAudioVolumeLevel)
        self.assertEqual(boost.changeBoost(pointer, 1), [20])
        self.assertEqual(boost.changeBoost(pointer, -1), [10])

    def test_identifies_boost_not_master_volume(self):
        control = Control()
        endpoint = object()
        parts = [Part("Microphone", Control()), Part("Microphone Boost", control)]
        with patch.object(boost.AudioUtilities, "GetDeviceEnumerator") as enumerator, \
                patch.object(boost, "_walkCaptureParts", return_value=parts), \
                patch.object(boost, "_partString", side_effect=lambda method: method()):
            enumerator.return_value.GetDefaultAudioEndpoint.return_value = endpoint
            self.assertIs(boost.findDefaultBoost(), control)

    def test_missing_and_ambiguous_boost(self):
        for parts in [[Part("Microphone", Control())], [Part("Microphone Boost", Control()), Part("Mic Boost", Control())]]:
            with patch.object(boost.AudioUtilities, "GetDeviceEnumerator"), \
                    patch.object(boost, "_walkCaptureParts", return_value=parts), \
                    patch.object(boost, "_partString", side_effect=lambda method: method()):
                with self.assertRaises(boost.BoostNotSupportedError):
                    boost.findDefaultBoost()

    def test_no_default_microphone(self):
        with patch.object(boost.AudioUtilities, "GetDeviceEnumerator") as enumerator:
            enumerator.return_value.GetDefaultAudioEndpoint.return_value = None
            with self.assertRaises(boost.NoMicrophoneError):
                boost.findDefaultBoost()

    def test_default_is_resolved_for_every_press(self):
        first, second = Control((0,)), Control((20,))
        with patch.object(boost, "findDefaultBoost", side_effect=[first, second]) as find:
            self.assertEqual(boost.changeDefaultBoost(1), [10])
            self.assertEqual(boost.changeDefaultBoost(-1), [10])
            self.assertEqual(find.call_count, 2)


if __name__ == "__main__":
    unittest.main()
