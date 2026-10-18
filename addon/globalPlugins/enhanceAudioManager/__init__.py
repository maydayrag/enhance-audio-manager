# -*- coding: UTF-8 -*-

"""Enhance Audio Manager 的 NVDA 全域外掛入口。"""

import sys
from pathlib import Path
import time
import os
import ctypes
from ctypes import wintypes
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any
from concurrent.futures import Future, ThreadPoolExecutor

# 第三方相依套件跟隨附加元件封裝，避免依賴 NVDA 內部剛好附帶的套件。
_vendorPath = str(Path(__file__).with_name("vendor"))
if _vendorPath not in sys.path:
	sys.path.insert(0, _vendorPath)

import addonHandler
import api
import config
import globalPluginHandler
from logHandler import log
import scriptHandler
import synthDriverHandler
import tones
import ui
from utils import mmdevice
import wx
from comtypes import COMError
from pycaw.api.audioclient import ISimpleAudioVolume
from pycaw.constants import DEVICE_STATE, EDataFlow, ERole
from pycaw.utils import AudioUtilities

addonHandler.initTranslation()

CATEGORY = _("Enhance Audio Manager")
_ENDPOINT_NOT_FOUND = -2147023728  # HRESULT_FROM_WIN32(ERROR_NOT_FOUND)


class GUID(ctypes.Structure):
	_fields_ = [
		("Data1", wintypes.DWORD),
		("Data2", wintypes.WORD),
		("Data3", wintypes.WORD),
		("Data4", ctypes.c_ubyte * 8),
	]

	@classmethod
	def fromString(cls, value: str):
		return cls.from_buffer_copy(uuid.UUID(value).bytes_le)


class AudioPolicy:
	"""設定或清除某個處理程序的播放／錄音裝置喜好。"""

	_RUNTIME_CLASS = "Windows.Media.Internal.AudioPolicyConfig"
	_IIDS = (
		"ab3d4648-e242-459f-b02f-541c70306324",  # Windows 11 21H2 以後
		"2a59116d-6c4f-45e0-a74f-707e3fef9258",  # 較舊 Windows 10
	)
	_RENDER_SUFFIX = "#{e6327cad-dcec-4949-ae8a-991e976a79d2}"
	_CAPTURE_SUFFIX = "#{2eef81be-33fa-4800-9670-1cd474972c3f}"
	_DEVICE_PREFIX = "\\\\?\\SWD#MMDEVAPI#"

	def __init__(self):
		self._combase = ctypes.WinDLL("combase", use_last_error=True)
		self._combase.RoInitialize.argtypes = (ctypes.c_int,)
		self._combase.RoInitialize.restype = ctypes.c_long
		self._combase.RoUninitialize.argtypes = ()
		# 1 代表多執行緒 Apartment；若執行緒已初始化為其他模式，仍可嘗試取用 Factory。
		self._roInitialized = self._combase.RoInitialize(1) >= 0
		self._combase.WindowsCreateString.argtypes = (
			wintypes.LPCWSTR,
			wintypes.UINT,
			ctypes.POINTER(ctypes.c_void_p),
		)
		self._combase.WindowsCreateString.restype = ctypes.c_long
		self._combase.WindowsDeleteString.argtypes = (ctypes.c_void_p,)
		self._combase.RoGetActivationFactory.argtypes = (
			ctypes.c_void_p,
			ctypes.POINTER(GUID),
			ctypes.POINTER(ctypes.c_void_p),
		)
		self._combase.RoGetActivationFactory.restype = ctypes.c_long

	def close(self) -> None:
		"""平衡由本物件成功執行的 RoInitialize。"""
		if self._roInitialized:
			self._combase.RoUninitialize()
			self._roInitialized = False

	def _check(self, result: int, operation: str) -> None:
		if result < 0:
			raise OSError(result, operation)

	def _createHString(self, text: str) -> ctypes.c_void_p:
		hstring = ctypes.c_void_p()
		self._check(
			self._combase.WindowsCreateString(text, len(text), ctypes.byref(hstring)),
			"WindowsCreateString failed",
		)
		return hstring

	def _getFactory(self) -> ctypes.c_void_p:
		className = self._createHString(self._RUNTIME_CLASS)
		try:
			for iidText in self._IIDS:
				factory = ctypes.c_void_p()
				iid = GUID.fromString(iidText)
				result = self._combase.RoGetActivationFactory(className, ctypes.byref(iid), ctypes.byref(factory))
				if result >= 0 and factory.value:
					return factory
			raise OSError("Windows audio policy activation factory is unavailable")
		finally:
			self._combase.WindowsDeleteString(className)

	def _method(self, factory: ctypes.c_void_p, slot: int, *argumentTypes):
		vtable = ctypes.cast(factory, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
		prototype = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argumentTypes)
		return prototype(vtable[slot])

	def setEndpoint(self, processId: int, flow: int, endpointId: str | None) -> None:
		"""為處理程序設定端點；endpointId 為 None 時恢復系統預設。"""
		factory = self._getFactory()
		hstring = ctypes.c_void_p()
		try:
			if endpointId:
				suffix = self._RENDER_SUFFIX if flow == 0 else self._CAPTURE_SUFFIX
				hstring = self._createHString(f"{self._DEVICE_PREFIX}{endpointId}{suffix}")
			setEndpoint = self._method(
				factory,
				25,
				wintypes.UINT,
				ctypes.c_int,
				ctypes.c_int,
				ctypes.c_void_p,
			)
			# 與參考專案相同，同時設定 Console 與 Multimedia 角色。
			for role in (0, 1):
				self._check(setEndpoint(factory, processId, flow, role, hstring), "Set endpoint failed")
		finally:
			if hstring.value:
				self._combase.WindowsDeleteString(hstring)
			self._method(factory, 2)(factory)

	def clearAll(self) -> None:
		"""清除所有應用程式保存的播放與錄音裝置喜好。"""
		factory = self._getFactory()
		try:
			clearAll = self._method(factory, 27)
			self._check(clearAll(factory), "Clear application endpoints failed")
		finally:
			self._method(factory, 2)(factory)

class DeviceKind(Enum):
	"""音訊裝置的資料流方向。"""

	PLAYBACK = EDataFlow.eRender.value
	RECORDING = EDataFlow.eCapture.value


@dataclass
class AudioTarget:
	"""畫面閱讀器可以瀏覽及控制的一個音訊目標。"""

	identifier: str
	name: str
	volumeInterface: Any
	device: Any | None = None
	isEndpoint: bool = False
	isDefault: bool = False
	processId: int | None = None

	@property
	def volume(self) -> int:
		# Core Audio 使用 0 到 1 的小數；使用者聽到的是 0 到 100。
		value = (
			self.volumeInterface.GetMasterVolumeLevelScalar()
			if self.isEndpoint
			else self.volumeInterface.GetMasterVolume()
		)
		return round(value * 100)

	@property
	def muted(self) -> bool:
		return bool(self.volumeInterface.GetMute())

	def setVolume(self, percent: int) -> None:
		percent = max(0, min(100, percent))
		if self.isEndpoint:
			self.volumeInterface.SetMasterVolumeLevelScalar(percent / 100, None)
		else:
			self.volumeInterface.SetMasterVolume(percent / 100, None)

	def toggleMute(self) -> bool:
		newState = not self.muted
		self.volumeInterface.SetMute(newState, None)
		return newState


class CoreAudioBackend:
	"""列舉並控制 Windows 裝置與應用程式音訊工作階段。"""

	def __init__(self):
		self._policy = AudioPolicy()

	def close(self) -> None:
		self._policy.close()

	def listDevices(self, kind: DeviceKind) -> list[AudioTarget]:
		enumerator = AudioUtilities.GetDeviceEnumerator()
		devices = AudioUtilities.GetAllDevices(
			data_flow=kind.value,
			device_state=DEVICE_STATE.ACTIVE.value,
		)
		# 沒有端點是拔除 USB 裝置後的正常狀態。先回傳空清單，避免
		# GetDefaultAudioEndpoint 以「找不到項目」HRESULT 造成錯誤記錄。
		if not devices:
			return []
		try:
			defaultEndpoint = enumerator.GetDefaultAudioEndpoint(kind.value, ERole.eMultimedia.value)
		except COMError as error:
			# 裝置可能在列舉與取得預設值之間被拔除；這仍是正常的空狀態。
			if not error.args or error.args[0] != _ENDPOINT_NOT_FOUND:
				raise
			defaultEndpoint = None
		defaultIdentifier = defaultEndpoint.GetId() if defaultEndpoint is not None else None
		return [
			AudioTarget(
				device.id,
				device.FriendlyName,
				device.EndpointVolume,
				device,
				True,
				isDefault=device.id == defaultIdentifier,
			)
			for device in devices
		]

	def listSessions(self) -> list[AudioTarget]:
		results: list[AudioTarget] = []
		for session in AudioUtilities.GetAllSessions():
			volume = session.SimpleAudioVolume
			if volume is None:
				continue
			process = session.Process
			name = process.name() if process is not None else session.DisplayName
			if not name:
				name = f"PID {session.ProcessId}"
			results.append(
				AudioTarget(
					str(session.InstanceIdentifier),
					name,
					volume,
					processId=session.ProcessId,
				)
			)
		return results

	def getDefaultDevice(self, kind: DeviceKind) -> AudioTarget | None:
		"""取得 Windows 多媒體角色目前使用的預設裝置。"""
		enumerator = AudioUtilities.GetDeviceEnumerator()
		try:
			defaultEndpoint = enumerator.GetDefaultAudioEndpoint(kind.value, ERole.eMultimedia.value)
		except COMError as error:
			# Windows 在沒有此方向的有效端點時回傳 ERROR_NOT_FOUND。
			# 這是正常狀態，交由呼叫端報讀，不寫入 NVDA 記錄。
			if error.args and error.args[0] == _ENDPOINT_NOT_FOUND:
				return None
			raise
		if defaultEndpoint is None:
			return None
		# Avoid enumerating every endpoint here. Opening the property store for a
		# changing USB or Bluetooth device can block for several seconds.
		device = AudioUtilities.CreateDevice(defaultEndpoint)
		if device is None:
			return None
		return AudioTarget(
			device.id,
			device.FriendlyName,
			device.EndpointVolume,
			device,
			True,
			isDefault=True,
		)

	def setDefaultDevice(self, target: AudioTarget) -> None:
		# 同時設定主控台、多媒體與通訊角色，避免不同程式選到不同裝置。
		AudioUtilities.SetDefaultDevice(
			target.identifier,
			roles=[ERole.eConsole, ERole.eMultimedia, ERole.eCommunications],
		)

	def setSessionDevice(self, session: AudioTarget, kind: DeviceKind, device: AudioTarget | None) -> None:
		if session.processId is None:
			raise ValueError("The selected session has no process identifier")
		self._policy.setEndpoint(
			session.processId,
			kind.value,
			device.identifier if device is not None else None,
		)

	def resetAllSessionDevices(self) -> None:
		self._policy.clearAll()

	def resetAllSessionVolumes(self) -> int:
		"""重設每個啟用中播放裝置的工作階段，並回傳成功處理的數量。"""
		# GetAllSessions 只查看預設喇叭，會漏掉指定耳機等其他輸出的程式。
		devices = AudioUtilities.GetAllDevices(
			data_flow=EDataFlow.eRender.value,
			device_state=DEVICE_STATE.ACTIVE.value,
		)
		resetCount = 0
		failed = False
		for device in devices:
			try:
				enumerator = device.AudioSessionManager.GetSessionEnumerator()
				count = enumerator.GetCount()
			except Exception:
				failed = True
				log.exception("Unable to enumerate sessions on a playback device during reset")
				continue
			for index in range(count):
				try:
					control = enumerator.GetSession(index)
					if control is None:
						continue
					volume = control.QueryInterface(ISimpleAudioVolume)
					volume.SetMasterVolume(1.0, None)
					# 直接取消靜音，避免切換狀態時意外把已解除靜音的程式靜音。
					volume.SetMute(False, None)
					if abs(volume.GetMasterVolume() - 1.0) > 0.0001 or volume.GetMute():
						raise RuntimeError("Audio session reset did not retain the requested volume and mute state")
					resetCount += 1
				except Exception:
					# 單一程式結束或裝置移除，不應阻止其餘程式重設。
					failed = True
					log.exception("Unable to reset an audio session")
		if failed:
			# 已盡力處理其餘工作階段；有失敗時不可報讀全部成功。
			raise RuntimeError("One or more audio sessions could not be reset")
		return resetCount

	def toggleDefaultMute(self, kind: DeviceKind) -> tuple[bool, AudioTarget] | None:
		target = self.getDefaultDevice(kind)
		if target is None:
			return None
		return target.toggleMute(), target

	def toggleProcessMute(self, processId: int) -> tuple[bool, str] | None:
		sessions = [session for session in self.listSessions() if session.processId == processId]
		if not sessions:
			return None
		newState = not all(session.muted for session in sessions)
		for session in sessions:
			if session.muted != newState:
				session.toggleMute()
		return newState, sessions[0].name

class TargetNavigator:
	"""每次操作前重新列舉，避免使用已拔除裝置或已結束程式。"""

	def __init__(
		self,
		provider: Callable[[], list[AudioTarget]],
		label: str,
		emptyMessage: str,
		*,
		cacheTargets: bool = False,
	):
		self._provider = provider
		self._label = label
		self._emptyMessage = emptyMessage
		self._cacheTargets = cacheTargets
		self._index = -1
		self._targets: list[AudioTarget] = []

	@property
	def current(self) -> AudioTarget | None:
		if 0 <= self._index < len(self._targets):
			return self._targets[self._index]
		return None

	@property
	def emptyMessage(self) -> str:
		"""傳回此清單沒有任何項目時應向使用者報讀的訊息。"""
		return self._emptyMessage

	def move(self, offset: int) -> str:
		currentIdentifier = self.current.identifier if self.current is not None else None
		# 音訊端點可能隨時插入或移除。每次移動前取得 Windows
		# 目前仍有效的清單，避免繼續報讀已拔除裝置的快取名稱。
		if not self._cacheTargets or not self._targets:
			self._targets = self._provider()
		if not self._targets:
			self._index = -1
			return self._emptyMessage
		# 第一次瀏覽時，「下一個」從第一項開始，「上一個」從最後一項開始。
		if currentIdentifier is not None:
			self._index = next(
				(index for index, target in enumerate(self._targets) if target.identifier == currentIdentifier),
				-1,
			)
		if self._index < 0:
			self._index = 0 if offset > 0 else len(self._targets) - 1
		else:
			requestedIndex = self._index + offset
			# 到達清單邊界後不循環；短嗶聲讓使用者知道已經到底。
			if requestedIndex < 0 or requestedIndex >= len(self._targets):
				tones.beep(880, 60)
			else:
				self._index = requestedIndex
		return self.describe()

	def setTargets(self, targets: list[AudioTarget]) -> None:
		"""Prime or replace the navigation cache without changing its selection."""
		currentIdentifier = self.current.identifier if self.current is not None else None
		self._targets = targets
		self._index = next(
			(index for index, target in enumerate(targets) if target.identifier == currentIdentifier),
			-1,
		)

	def markDefault(self, identifier: str) -> None:
		"""Update default-device announcements without enumerating endpoints again."""
		for target in self._targets:
			if target.isEndpoint:
				target.isDefault = target.identifier == identifier

	def refreshCurrent(self) -> AudioTarget | None:
		"""重新列舉並傳回仍有效的目前項目；項目消失時清除選取。"""
		target = self.current
		if target is None:
			return None
		return self._refreshTarget(target.identifier)

	def missingCurrentMessage(self) -> str:
		"""依刷新後是否仍有其他項目，說明空清單或單一項目移除。"""
		return self._emptyMessage if not self._targets else _("The selected audio device has been removed")

	def describe(self) -> str:
		target = self.current
		if target is None:
			return self._emptyMessage if not self._targets else _("Select an audio target first")
		# 先報讀重要狀態，再報讀目標名稱，讓使用者立即知道是否靜音。
		state = _("Muted, ") if target.muted else ""
		defaultState = _("Default device, ") if target.isDefault else ""
		return _("{defaultState}{state}{name}, volume {volume}").format(
			name=target.name,
			volume=target.volume,
			state=state,
			defaultState=defaultState,
		)

	def changeVolume(self, amount: int) -> str:
		target = self.current
		if target is None:
			return self._emptyMessage if not self._targets else _("Select an audio target first")
		# 音量鍵可能被快速連按。正常路徑直接使用瀏覽清單時取得的介面，
		# 避免每 1% 都完整列舉裝置，讓新數值能立刻送到語音與點字顯示。
		# 若介面確實已失效，下方的例外路徑仍會重新列舉並重試一次。
		desiredVolume = max(0, min(100, target.volume + amount))
		try:
			target.setVolume(desiredVolume)
		except Exception:
			# Some drivers (notably virtual loopback endpoints) apply the level and
			# then return a failing HRESULT. Reading from the existing interface is
			# cheap, so verify the result before doing an expensive device enumeration.
			try:
				actualVolume = target.volume
			except Exception:
				actualVolume = None
			if actualVolume == desiredVolume:
				return str(actualVolume)
			# The interface is genuinely stale or the operation was not applied.
			# Refresh once and retry with the newly acquired interface.
			target = self._refreshTarget(target.identifier)
			if target is None:
				return _("The selected audio target is no longer available")
			if target.volume != desiredVolume:
				target.setVolume(desiredVolume)
		# 設定成功後直接顯示要求的數值，不再為顯示而同步讀回一次。
		# 驅動程式回報失敗的特殊情況已在上方讀回確認。
		return str(desiredVolume)

	def _refreshTarget(self, identifier: str) -> AudioTarget | None:
		freshTargets = self._provider()
		freshIndex = next(
			(index for index, item in enumerate(freshTargets) if item.identifier == identifier),
			None,
		)
		self._targets = freshTargets
		if freshIndex is None:
			self._index = -1
			return None
		self._index = freshIndex
		return self._targets[self._index]

	def toggleMute(self) -> str:
		target = self.current
		if target is None:
			return self._emptyMessage if not self._targets else _("Select an audio target first")
		# 靜音切換和音量調整採相同的熱插拔驗證，絕不操作失效介面。
		target = self.refreshCurrent()
		if target is None:
			return self.missingCurrentMessage()
		muted = target.toggleMute()
		return _("{state}, {name}").format(
			name=target.name,
			state=_("Muted") if muted else _("Unmuted"),
		)


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	"""提供可在 NVDA 輸入手勢對話框重新指定的完整鍵盤指令。"""

	def __init__(self):
		super().__init__()
		config.conf.spec["enhanceAudioManager"] = {
			"lockMicrophoneVolume": "boolean(default=False)",
			"microphoneVolume": "integer(default=50, min=0, max=100)",
		}
		self._backend = CoreAudioBackend()
		self._playback = TargetNavigator(
			lambda: self._backend.listDevices(DeviceKind.PLAYBACK),
			_("Playback devices"),
			_("No output devices"),
		)
		self._recording = TargetNavigator(
			lambda: self._backend.listDevices(DeviceKind.RECORDING),
			_("Recording devices"),
			_("No input devices"),
		)
		self._sessions = TargetNavigator(
			self._backend.listSessions,
			_("Audio applications"),
			_("No audio applications"),
		)
		self._activeNavigator: TargetNavigator | None = None
		self._sessionDeviceIndexes: dict[tuple[int, DeviceKind], int] = {}
		self._microphoneVolumeLocked = config.conf["enhanceAudioManager"]["lockMicrophoneVolume"]
		self._lockedMicrophoneVolume = config.conf["enhanceAudioManager"]["microphoneVolume"]
		self._lastLockErrorTime = 0.0
		self._microphoneExecutor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="EnhanceAudioManagerMic")
		self._microphoneFuture: Future | None = None
		# 與參考專案相同，每 100 毫秒檢查一次預設麥克風音量。
		self._microphoneTimer = wx.Timer()
		self._microphoneTimer.Bind(wx.EVT_TIMER, self._onMicrophoneTimer)
		self._microphoneTimer.Start(100)
		# 等 NVDA 啟動流程回到 GUI 事件迴圈後，再執行一次播放裝置取消靜音。
		wx.CallAfter(self._unmutePlaybackDevicesOnStartup)

	def _unmutePlaybackDevicesOnStartup(self) -> None:
		"""NVDA 啟動後，只取消目前確實處於靜音狀態的播放裝置。"""
		try:
			targets = self._backend.listDevices(DeviceKind.PLAYBACK)
			self._playback.setTargets(targets)
			for target in targets:
				if target.muted:
					target.toggleMute()
		except Exception:
			log.exception("Unable to unmute playback devices during Enhance Audio Manager startup")

	def terminate(self):
		"""NVDA 卸載外掛時停止計時器，避免留下仍在執行的回呼。"""
		self._microphoneTimer.Stop()
		self._microphoneTimer.Unbind(wx.EVT_TIMER, handler=self._onMicrophoneTimer)
		self._microphoneExecutor.shutdown(wait=False, cancel_futures=True)
		self._backend.close()
		super().terminate()

	def _onMicrophoneTimer(self, event) -> None:
		"""鎖定啟用時，把預設麥克風維持在使用者記住的音量。"""
		if not self._microphoneVolumeLocked:
			return
		# Core Audio discovery may block while devices reconnect. Keep it away from
		# NVDA's wx thread and do not queue overlapping polls.
		if self._microphoneFuture is not None and not self._microphoneFuture.done():
			return
		self._microphoneFuture = self._microphoneExecutor.submit(self._maintainMicrophoneVolume)

	def _maintainMicrophoneVolume(self) -> None:
		try:
			import comtypes

			comtypes.CoInitialize()
			try:
				target = self._backend.getDefaultDevice(DeviceKind.RECORDING)
				if target is not None and target.volume != self._lockedMicrophoneVolume:
					target.setVolume(self._lockedMicrophoneVolume)
			finally:
				comtypes.CoUninitialize()
		except Exception:
			# 最多每十秒記錄一次，避免裝置暫時中斷時大量灌入 nvda.log。
			now = time.monotonic()
			if now - self._lastLockErrorTime >= 10:
				log.debugWarning("Unable to maintain locked microphone volume", exc_info=True)
				self._lastLockErrorTime = now

	def _run(self, operation, errorMessage: str) -> None:
		"""統一報讀結果並把完整錯誤寫入 NVDA 記錄。"""
		try:
			ui.message(operation())
		except Exception:
			log.exception(errorMessage)
			ui.message(_("Audio operation failed; details have been written to the NVDA log"))

	def _select(self, navigator: TargetNavigator, offset: int) -> None:
		self._activeNavigator = navigator
		self._run(lambda: navigator.move(offset), "Unable to enumerate audio targets")

	def _volume(self, direction: int) -> str:
		if self._activeNavigator is None:
			return _("Select a playback device, recording device, or audio application first")
		# 一次固定調整 1%，不受舊設定檔中可能殘留的數值影響。
		message = self._activeNavigator.changeVolume(direction)
		# 鎖定期間若調整的是預設麥克風，就以新音量更新鎖定值。
		if self._microphoneVolumeLocked and self._activeNavigator is self._recording:
			try:
				target = self._recording.current
				# 瀏覽錄音裝置時已記錄預設狀態；不要在每次按音量鍵後再次
				# 列舉預設裝置，以免延後這次數值的顯示。
				if target is not None and target.isDefault and message.isdecimal():
					self._lockedMicrophoneVolume = int(message)
					config.conf["enhanceAudioManager"]["microphoneVolume"] = self._lockedMicrophoneVolume
			except Exception:
				# The volume operation already succeeded. Failure of this follow-up query
				# must not produce a misleading operation-failed announcement.
				log.debugWarning("Unable to update the locked microphone volume", exc_info=True)
		return message

	@scriptHandler.script(
		category=CATEGORY,
		description=_("Next playback device"),
		gestures=["kb:control+windows+alt+numpad6", "kb(laptop):control+windows+alt+pagedown"],
	)
	def script_nextPlayback(self, gesture):
		self._select(self._playback, 1)

	@scriptHandler.script(
		category=CATEGORY,
		description=_("Previous playback device"),
		gestures=["kb:control+windows+alt+numpad4", "kb(laptop):control+windows+alt+pageup"],
	)
	def script_previousPlayback(self, gesture):
		self._select(self._playback, -1)

	@scriptHandler.script(
		category=CATEGORY,
		description=_("Next recording device"),
		gestures=["kb:control+windows+alt+numpad3", "kb(laptop):control+windows+alt+end"],
	)
	def script_nextRecording(self, gesture):
		self._select(self._recording, 1)

	@scriptHandler.script(
		category=CATEGORY,
		description=_("Previous recording device"),
		gestures=["kb:control+windows+alt+numpad1", "kb(laptop):control+windows+alt+home"],
	)
	def script_previousRecording(self, gesture):
		self._select(self._recording, -1)

	@scriptHandler.script(
		category=CATEGORY,
		description=_("Next audio application"),
		gestures=["kb:control+windows+alt+numpad9", "kb(laptop):control+windows+alt+rightarrow"],
	)
	def script_nextSession(self, gesture):
		self._select(self._sessions, 1)

	@scriptHandler.script(
		category=CATEGORY,
		description=_("Previous audio application"),
		gestures=["kb:control+windows+alt+numpad7", "kb(laptop):control+windows+alt+leftarrow"],
	)
	def script_previousSession(self, gesture):
		self._select(self._sessions, -1)

	@scriptHandler.script(
		category=CATEGORY,
		description=_("Increase the selected audio target volume"),
		gestures=["kb:control+windows+alt+numpad8", "kb(laptop):control+windows+alt+uparrow"],
	)
	def script_volumeUp(self, gesture):
		self._run(lambda: self._volume(1), "Unable to increase audio volume")

	@scriptHandler.script(
		category=CATEGORY,
		description=_("Decrease the selected audio target volume"),
		gestures=["kb:control+windows+alt+numpad2", "kb(laptop):control+windows+alt+downarrow"],
	)
	def script_volumeDown(self, gesture):
		self._run(lambda: self._volume(-1), "Unable to decrease audio volume")

	@scriptHandler.script(
		category=CATEGORY,
		description=_("Toggle mute for the selected audio target"),
		gestures=["kb:control+windows+alt+numpad5", "kb(laptop):control+windows+alt+space"],
	)
	def script_toggleMute(self, gesture):
		def toggle() -> str:
			if self._activeNavigator is None:
				return _("Select a playback device, recording device, or audio application first")
			return self._activeNavigator.toggleMute()
		self._run(toggle, "Unable to toggle audio mute")

	@scriptHandler.script(
		category=CATEGORY,
		description=_("Set the selected device as the Windows default"),
		gestures=["kb:control+windows+alt+numpadenter", "kb(laptop):control+windows+alt+enter"],
	)
	def script_setDefault(self, gesture):
		def setDefault() -> str:
			if self._activeNavigator not in (self._playback, self._recording):
				return _("Select a playback or recording device first")
			target = self._activeNavigator.current
			if target is None:
				return self._activeNavigator.emptyMessage
			target = self._activeNavigator.refreshCurrent()
			if target is None:
				return self._activeNavigator.missingCurrentMessage()
			self._backend.setDefaultDevice(target)
			self._activeNavigator.markDefault(target.identifier)
			return _("Set as Windows default device, {name}").format(name=target.name)
		self._run(setDefault, "Unable to set the default audio device")

	@scriptHandler.script(
		category=CATEGORY,
		description=_("Next NVDA output device"),
		gestures=["kb:control+windows+alt+numpadplus", "kb(laptop):control+windows+alt+backslash"],
	)
	def script_nextNVDAOutput(self, gesture):
		self._run(lambda: self._changeNVDAOutput(1), "Unable to change NVDA output device")

	@scriptHandler.script(
		category=CATEGORY,
		description=_("Previous NVDA output device"),
		gestures=[
			"kb:shift+control+windows+alt+numpadplus",
			"kb(laptop):shift+control+windows+alt+backslash",
		],
	)
	def script_previousNVDAOutput(self, gesture):
		self._run(lambda: self._changeNVDAOutput(-1), "Unable to change NVDA output device")

	@scriptHandler.script(
		category=CATEGORY,
		description=_("Lock or unlock microphone volume"),
		gestures=[
			"kb:control+windows+alt+numpaddelete",
			"kb(laptop):control+windows+alt+delete",
		],
	)
	def script_toggleMicrophoneVolumeLock(self, gesture):
		self._run(self._toggleMicrophoneVolumeLock, "Unable to toggle microphone volume lock")

	def _toggleMicrophoneVolumeLock(self) -> str:
		"""記住目前預設麥克風音量，或解除既有鎖定。"""
		target = self._backend.getDefaultDevice(DeviceKind.RECORDING)
		if target is None:
			return _("No input devices")
		self._microphoneVolumeLocked = not self._microphoneVolumeLocked
		if self._microphoneVolumeLocked:
			self._lockedMicrophoneVolume = target.volume
			config.conf["enhanceAudioManager"]["microphoneVolume"] = self._lockedMicrophoneVolume
			message = _("Locked, {name}, volume {volume}").format(
				name=target.name,
				volume=self._lockedMicrophoneVolume,
			)
		else:
			message = _("Unlocked, {name}").format(name=target.name)
		config.conf["enhanceAudioManager"]["lockMicrophoneVolume"] = self._microphoneVolumeLocked
		return message

	def _changeSessionDevice(self, kind: DeviceKind, offset: int) -> str:
		"""切換目前選取之應用程式的播放或錄音裝置。"""
		if self._activeNavigator is not self._sessions or self._sessions.current is None:
			return _("Select an audio application first")
		session = self._sessions.current
		if session.processId is None:
			return _("Unable to identify the selected application process")
		if session.processId == os.getpid():
			return _("Use the NVDA output device shortcuts to change NVDA playback device")
		devices = self._backend.listDevices(kind)
		if not devices:
			return _("No output devices") if kind is DeviceKind.PLAYBACK else _("No input devices")
		key = (session.processId, kind)
		currentIndex = self._sessionDeviceIndexes.get(key, -1 if offset > 0 else 0)
		newIndex = (currentIndex + offset) % len(devices)
		device = devices[newIndex]
		self._backend.setSessionDevice(session, kind, device)
		self._sessionDeviceIndexes[key] = newIndex
		return device.name

	@scriptHandler.script(
		category=CATEGORY,
		description=_("Next playback device for the selected audio application"),
		gestures=[
			"kb:control+windows+alt+numpadmultiply",
			"kb(laptop):control+windows+alt+]",
		],
	)
	def script_nextSessionPlaybackDevice(self, gesture):
		self._run(
			lambda: self._changeSessionDevice(DeviceKind.PLAYBACK, 1),
			"Unable to change the application playback device",
		)

	@scriptHandler.script(
		category=CATEGORY,
		description=_("Previous playback device for the selected audio application"),
		gestures=[
			"kb:shift+control+windows+alt+numpadmultiply",
			"kb(laptop):shift+control+windows+alt+]",
		],
	)
	def script_previousSessionPlaybackDevice(self, gesture):
		self._run(
			lambda: self._changeSessionDevice(DeviceKind.PLAYBACK, -1),
			"Unable to change the application playback device",
		)

	@scriptHandler.script(
		category=CATEGORY,
		description=_("Next recording device for the selected audio application"),
		gestures=[
			"kb:control+windows+alt+numpaddivide",
			"kb(laptop):control+windows+alt+[",
		],
	)
	def script_nextSessionRecordingDevice(self, gesture):
		self._run(
			lambda: self._changeSessionDevice(DeviceKind.RECORDING, 1),
			"Unable to change the application recording device",
		)

	@scriptHandler.script(
		category=CATEGORY,
		description=_("Previous recording device for the selected audio application"),
		gestures=[
			"kb:shift+control+windows+alt+numpaddivide",
			"kb(laptop):shift+control+windows+alt+[",
		],
	)
	def script_previousSessionRecordingDevice(self, gesture):
		self._run(
			lambda: self._changeSessionDevice(DeviceKind.RECORDING, -1),
			"Unable to change the application recording device",
		)

	@scriptHandler.script(
		category=CATEGORY,
		description=_("Reset devices for all audio applications; press twice to reset volume and unmute"),
		gestures=[
			"kb:control+windows+alt+numpadminus",
			"kb(laptop):control+windows+alt+backspace",
		],
	)
	def script_resetSessions(self, gesture):
		if scriptHandler.getLastScriptRepeatCount() == 0:
			def resetDevices() -> str:
				# 即使程式目前沒有播放聲音，也可能保存了自訂裝置設定。
				self._backend.resetAllSessionDevices()
				self._sessionDeviceIndexes.clear()
				return _("Playback and recording devices reset for all audio applications")
			self._run(resetDevices, "Unable to reset application audio devices")
		else:
			def resetVolumes() -> str:
				if self._backend.resetAllSessionVolumes() == 0:
					return _("No audio applications")
				return _("All audio application volumes set to 100 and unmuted")
			self._run(resetVolumes, "Unable to reset application audio volumes")

	@scriptHandler.script(
		category=CATEGORY,
		description=_("Decrease default microphone boost (dB)"),
		gestures=["kb(desktop):control+windows+numpad2", "kb(laptop):control+windows+downarrow"],
	)
	def script_defaultMicrophoneBoostDown(self, gesture):
		self._run(
			lambda: self._changeDefaultMicrophoneBoost(-1),
			"Unable to decrease the default microphone boost",
		)

	@scriptHandler.script(
		category=CATEGORY,
		description=_("Increase default microphone boost (dB)"),
		gestures=["kb(desktop):control+windows+numpad8", "kb(laptop):control+windows+uparrow"],
	)
	def script_defaultMicrophoneBoostUp(self, gesture):
		self._run(
			lambda: self._changeDefaultMicrophoneBoost(1),
			"Unable to increase the default microphone boost",
		)

	def _changeDefaultMicrophoneBoost(self, direction: int) -> str:
		# 硬體增量與 0～100 的麥克風音量各自獨立，因此不用更動音量鎖定。
		from .._enhanceAudioManager.microphoneBoost import (
			BoostNotSupportedError, NoMicrophoneError, changeDefaultBoost,
		)
		try:
			levels = changeDefaultBoost(direction)
		except NoMicrophoneError:
			return _("No input devices")
		except BoostNotSupportedError:
			return _("The default microphone has no recognizable boost (dB) control")
		# 多聲道值相同時只報一次；不同時依聲道順序報讀。
		values = [f"{value:g}" for value in levels]
		levelText = values[0] if len(set(values)) == 1 else "、".join(values)
		return _("Microphone boost {level} dB").format(level=levelText)

	def _toggleDefaultDeviceMute(self, kind: DeviceKind) -> str:
		result = self._backend.toggleDefaultMute(kind)
		if result is None:
			return _("No output devices") if kind is DeviceKind.PLAYBACK else _("No input devices")
		muted, target = result
		return _("{state}, {name}").format(
			state=_("Muted") if muted else _("Unmuted"),
			name=target.name,
		)

	@scriptHandler.script(
		category=CATEGORY,
		description=_("Toggle mute for the default microphone"),
		gestures=[
			"kb:shift+control+windows+alt+numpad2",
			"kb(laptop):shift+control+windows+alt+downarrow",
		],
	)
	def script_microphoneSwitch(self, gesture):
		self._run(
			lambda: self._toggleDefaultDeviceMute(DeviceKind.RECORDING),
			"Unable to toggle the default microphone mute state",
		)

	@scriptHandler.script(
		category=CATEGORY,
		description=_("Toggle mute for the default playback device"),
		gestures=[
			"kb:shift+control+windows+alt+numpad5",
			"kb(laptop):shift+control+windows+alt+uparrow",
		],
	)
	def script_soundSwitch(self, gesture):
		self._run(
			lambda: self._toggleDefaultDeviceMute(DeviceKind.PLAYBACK),
			"Unable to toggle the default playback device mute state",
		)

	@scriptHandler.script(
		category=CATEGORY,
		description=_("Toggle mute for the foreground application"),
		gestures=[
			"kb:shift+control+windows+alt+numpad8",
			"kb(laptop):shift+control+windows+alt+space",
		],
	)
	def script_muteCurrentWindow(self, gesture):
		def toggleWindow() -> str:
			focus = api.getFocusObject()
			result = self._backend.toggleProcessMute(focus.processID)
			if result is None:
				return _("The foreground application has no controllable audio session")
			muted, name = result
			return _("{state}, {name}").format(
				state=_("Muted") if muted else _("Unmuted"),
				name=name,
			)
		self._run(toggleWindow, "Unable to toggle the current window mute state")

	def _changeNVDAOutput(self, offset: int) -> str:
		"""依 NVDA 2026.1.1 的 mmdevice 與 audio 設定切換語音輸出。"""
		devices = list(mmdevice.getOutputDevices(includeDefault=True))
		if not devices:
			return _("No NVDA output devices")
		current = config.conf["audio"]["outputDevice"]
		currentIndex = next((index for index, device in enumerate(devices) if device.id == current), 0)
		target = devices[(currentIndex + offset) % len(devices)]
		config.conf["audio"]["outputDevice"] = target.id
		currentSynth = synthDriverHandler.getSynth()
		if currentSynth is None or not synthDriverHandler.setSynth(currentSynth.name):
			raise RuntimeError("NVDA synthesizer could not be reloaded")
		tones.terminate()
		tones.initialize()
		return _("NVDA output device: {name}").format(name=target.friendlyName)
