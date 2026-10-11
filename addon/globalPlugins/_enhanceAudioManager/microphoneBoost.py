"""以 Windows DeviceTopology 存取麥克風增量（dB），不操作端點音量。

介面順序、GUID、參數依 Windows SDK 10.0.28000.0 devicetopology.idl。
只宣告各介面實際需要的方法及其前面的槽位。
"""
import ctypes
from ctypes import HRESULT, POINTER, c_float, c_int, c_void_p
from ctypes.wintypes import BOOL, DWORD, UINT, ULONG
import math
import winreg

from comtypes import CLSCTX_ALL, COMMETHOD, COMError, GUID, IUnknown
from pycaw.constants import EDataFlow, ERole
from pycaw.utils import AudioUtilities


class IPart(IUnknown):
    _iid_ = GUID("{AE2DE0E4-5BCA-4F2D-AA46-5D13F8FDB3A9}")


class IPartsList(IUnknown):
    _iid_ = GUID("{6DAA848C-5EB0-45CC-AEA5-998A2CDA1FFB}")
    _methods_ = [
        COMMETHOD([], HRESULT, "GetCount", (["out"], POINTER(UINT), "count")),
        COMMETHOD([], HRESULT, "GetPart", (["in"], UINT, "index"), (["out"], POINTER(POINTER(IPart)), "part")),
    ]


class IConnector(IUnknown):
    _iid_ = GUID("{9C2C4058-23F5-41DE-877A-DF3AF236A09E}")


IConnector._methods_ = [
    COMMETHOD([], HRESULT, "GetType", (["out"], POINTER(c_int), "kind")),
    COMMETHOD([], HRESULT, "GetDataFlow", (["out"], POINTER(c_int), "flow")),
    COMMETHOD([], HRESULT, "ConnectTo", (["in"], POINTER(IConnector), "other")),
    COMMETHOD([], HRESULT, "Disconnect"),
    COMMETHOD([], HRESULT, "IsConnected", (["out"], POINTER(BOOL), "connected")),
    COMMETHOD([], HRESULT, "GetConnectedTo", (["out"], POINTER(POINTER(IConnector)), "other")),
]


class IDeviceTopology(IUnknown):
    _iid_ = GUID("{2A07407E-6497-4A18-9787-32F79BD0D98F}")
    _methods_ = [
        COMMETHOD([], HRESULT, "GetConnectorCount", (["out"], POINTER(UINT), "count")),
        COMMETHOD([], HRESULT, "GetConnector", (["in"], UINT, "index"), (["out"], POINTER(POINTER(IConnector)), "connector")),
    ]


IPart._methods_ = [
    # 用原始指標保留 Windows 配置的字串，讀取後由 _partString 釋放。
    COMMETHOD([], HRESULT, "GetName", (["out"], POINTER(c_void_p), "name")),
    COMMETHOD([], HRESULT, "GetLocalId", (["out"], POINTER(UINT), "identifier")),
    COMMETHOD([], HRESULT, "GetGlobalId", (["out"], POINTER(c_void_p), "identifier")),
    COMMETHOD([], HRESULT, "GetPartType", (["out"], POINTER(c_int), "kind")),
    COMMETHOD([], HRESULT, "GetSubType", (["out"], POINTER(GUID), "subtype")),
    COMMETHOD([], HRESULT, "GetControlInterfaceCount", (["out"], POINTER(UINT), "count")),
    COMMETHOD([], HRESULT, "GetControlInterface", (["in"], UINT, "index"), (["out"], POINTER(POINTER(IUnknown)), "control")),
    COMMETHOD([], HRESULT, "EnumPartsIncoming", (["out"], POINTER(POINTER(IPartsList)), "parts")),
    COMMETHOD([], HRESULT, "EnumPartsOutgoing", (["out"], POINTER(POINTER(IPartsList)), "parts")),
    COMMETHOD([], HRESULT, "GetTopologyObject", (["out"], POINTER(POINTER(IDeviceTopology)), "topology")),
    COMMETHOD([], HRESULT, "Activate", (["in"], DWORD, "context"), (["in"], POINTER(GUID), "iid"), (["out"], POINTER(POINTER(IUnknown)), "control")),
]


class IPerChannelDbLevel(IUnknown):
    _iid_ = GUID("{C2F8E001-F205-4BC9-99BC-C13B1E048CCB}")
    _methods_ = [
        COMMETHOD([], HRESULT, "GetChannelCount", (["out"], POINTER(UINT), "count")),
        COMMETHOD([], HRESULT, "GetLevelRange", (["in"], UINT, "channel"), (["out"], POINTER(c_float), "minimum"), (["out"], POINTER(c_float), "maximum"), (["out"], POINTER(c_float), "step")),
        COMMETHOD([], HRESULT, "GetLevel", (["in"], UINT, "channel"), (["out"], POINTER(c_float), "level")),
        COMMETHOD([], HRESULT, "SetLevel", (["in"], UINT, "channel"), (["in"], c_float, "level"), (["in"], POINTER(GUID), "context")),
        COMMETHOD([], HRESULT, "SetLevelUniform", (["in"], c_float, "level"), (["in"], POINTER(GUID), "context")),
        COMMETHOD([], HRESULT, "SetLevelAllChannels", (["in"], POINTER(c_float), "levels"), (["in"], ULONG, "count"), (["in"], POINTER(GUID), "context")),
    ]


class IAudioVolumeLevel(IPerChannelDbLevel):
    _iid_ = GUID("{7FB7B48F-531D-44A2-BCB3-5AD5A134B3DC}")
    _methods_ = []


class NoMicrophoneError(Exception):
    """目前沒有 Windows 預設錄音裝置。"""


class BoostNotSupportedError(Exception):
    """無法明確辨識可調整 dB 的麥克風增量控制。"""


_NOT_FOUND = -2147023728
_NO_INTERFACE = -2147467262
_ole32 = ctypes.OleDLL("ole32")
_ole32.CoTaskMemFree.argtypes = [c_void_p]
_ole32.CoTaskMemFree.restype = None


def _partString(method):
    pointer = method()
    if not pointer:
        return ""
    try:
        return ctypes.wstring_at(pointer)
    finally:
        _ole32.CoTaskMemFree(pointer)


def _boostNames():
    # 使用 Windows 的標準增量名稱，支援目前系統語言及常見驅動名稱。
    names = {"microphone boost", "mic boost", "麥克風增量", "麥克風增強", "麦克风加强", "麦克风增强"}
    key = r"SYSTEM\CurrentControlSet\Control\MediaCategories\{2BC31D6A-96E3-11D2-AC4C-00C04F8EFB68}"
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key) as handle:
            name, _ = winreg.QueryValueEx(handle, "Name")
            names.add(name.strip().casefold())
    except OSError:
        pass
    return names


def _walkCaptureParts(endpoint):
    """只沿預設麥克風的訊號流向尋找，不掃描其他輸入端的控制。"""
    topology = endpoint.Activate(IDeviceTopology._iid_, CLSCTX_ALL, None).QueryInterface(IDeviceTopology)
    connector = topology.GetConnector(0)
    if connector.GetDataFlow() != 1:  # SDK 的 DataFlow.Out：錄音由端點流向音效卡。
        raise BoostNotSupportedError()
    if not connector.IsConnected():
        return
    pending = [connector.GetConnectedTo().QueryInterface(IPart)]
    visited = set()
    while pending:
        part = pending.pop()
        identifier = _partString(part.GetGlobalId)
        if identifier in visited:
            continue
        visited.add(identifier)
        if len(visited) > 256:
            raise BoostNotSupportedError("Unexpectedly large capture topology")
        yield part
        # 先走同一裝置內的下游連結；只有輸出接頭才跨到下一個裝置。
        try:
            outgoing = part.EnumPartsOutgoing()
        except COMError as error:
            if error.hresult != _NOT_FOUND:
                raise
        else:
            if outgoing:
                pending.extend(outgoing.GetPart(i) for i in range(outgoing.GetCount()))
        if part.GetPartType() == 0:
            connector = part.QueryInterface(IConnector)
            if connector.GetDataFlow() == 1 and connector.IsConnected():
                pending.append(connector.GetConnectedTo().QueryInterface(IPart))


def findDefaultBoost():
    """每次重新取得預設麥克風，避免切換裝置後調整到舊麥克風。"""
    try:
        endpoint = AudioUtilities.GetDeviceEnumerator().GetDefaultAudioEndpoint(
            EDataFlow.eCapture.value, ERole.eMultimedia.value,
        )
    except COMError as error:
        if error.hresult == _NOT_FOUND:
            raise NoMicrophoneError() from error
        raise
    if endpoint is None:
        raise NoMicrophoneError()
    names = _boostNames()
    matches = []
    try:
        for part in _walkCaptureParts(endpoint):
            try:
                name = _partString(part.GetName).strip().casefold()
            except COMError as error:
                if error.hresult == _NOT_FOUND:
                    continue
                raise
            if name not in names:
                continue
            try:
                control = part.Activate(CLSCTX_ALL, IAudioVolumeLevel._iid_).QueryInterface(IAudioVolumeLevel)
            except COMError as error:
                if error.hresult == _NO_INTERFACE:
                    continue
                raise
            matches.append(control)
    except COMError as error:
        if error.hresult == _NO_INTERFACE:
            raise BoostNotSupportedError() from error
        raise
    # 名稱不明或找到多個候選時，不猜測一般音量控制就是麥克風增量。
    if len(matches) != 1:
        raise BoostNotSupportedError()
    return matches[0]


def changeBoost(control, direction):
    """各聲道增減一個硬體支援的級距，並讀回實際 dB 值供報讀。"""
    count = control.GetChannelCount()
    if not 1 <= count <= 64:
        raise BoostNotSupportedError("Invalid channel count")
    levels = []
    for channel in range(count):
        minimum, maximum, step = control.GetLevelRange(channel)
        current = control.GetLevel(channel)
        if not all(math.isfinite(v) for v in (minimum, maximum, step, current)) or step <= 0 or maximum <= minimum:
            raise BoostNotSupportedError("Invalid boost range")
        # 以最小值為基準對齊硬體級距，並在上下限停止。
        position = (current - minimum) / step
        index = math.floor(position + 1e-5) + 1 if direction > 0 else math.ceil(position - 1e-5) - 1
        levels.append(max(minimum, min(maximum, minimum + index * step)))
    control.SetLevelAllChannels((c_float * count)(*levels), count, None)
    return [control.GetLevel(channel) for channel in range(count)]


def changeDefaultBoost(direction):
    return changeBoost(findDefaultBoost(), direction)
