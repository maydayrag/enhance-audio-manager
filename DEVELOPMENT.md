# 2.0.6 名稱調整查證紀錄（2026-10-11）

- 顯示名稱改為 Enhance Audio Manager，內部識別碼與設定區段仍為 `audioManager`。
- `../nvda-2026.2-docs/developerGuide.html#manifestFields` 區分內部識別碼 `name` 與顯示名稱 `summary`。
- `../nvda-2026.2-source/source/addonHandler/__init__.py` 的 `AddonBase.name` 取自 manifest 的 `name`；保留它以延續更新識別。
- `../nvda-2026.2-source/source/inputCore.py` 使用類別的 `__module__` 識別手勢，故保留 `globalPlugins.audioManager`。
- 依 `../nvda_dev.md` 的封裝規範將入口整理為 `globalPlugins/audioManager/__init__.py`，並調整第三方套件與支援模組的相對路徑。`../nvda-2026.2-source/source/globalPluginHandler.py` 的 `listPlugins` 以相同名稱載入模組或套件。
- 同時參考 `../nvda-addon-dev-guide-wiki/NVDA-Add-on-Development-Guide.md` 的附加元件目錄與封裝章節。
- 本次未變更音訊控制邏輯；尚未在執行中的 NVDA 實測升級及快捷鍵。

# 2.0.5 開發查證紀錄（2026-09-10）

需求：Ctrl+Shift+Numpad2 降低、Ctrl+Shift+Numpad8 提高預設麥克風增量（dB）。2.0.4 誤解為百分比音量，2.0.5 已修正。

## NVDA 依據

- `../nvda_dev.md`：API 查證、script 裝飾器、翻譯、封裝與成品驗證。
- `../nvda-2026.2-docs/developerGuide.html#DefiningScriptProperties`：手勢、說明、分類的定義。
- `../nvda-addon-dev-guide-wiki/NVDA-Add-on-Development-Guide.md`：scripts、UI messages 章節。
- `../nvda-2026.2-source/source/scriptHandler.py`：`script`、`executeScript`。
- `../nvda-2026.2-source/source/ui.py`：`message` 同時送出語音與點字。
- `../nvda-2026.2-source/source/globalPluginHandler.py`：底線開頭的支援模組不會被當成獨立外掛載入。

沿用現有 `_run` 的同步指令與錯誤報讀方式；這次不新增背景執行緒或生命週期回呼。

## Windows 依據

- 本機 Windows SDK `10.0.28000.0/um/devicetopology.idl`：IPart、IPartsList、IConnector、IDeviceTopology、IPerChannelDbLevel、IAudioVolumeLevel 的 GUID、方法順序及參數。
- 同版 `shared/ksmedia.h`：`KSAUDFNAME_MICROPHONE_BOOST` 名稱 GUID。
- [Device Topologies](https://learn.microsoft.com/en-us/windows/win32/coreaudio/device-topologies)：由錄音端點經接頭跨至硬體，再沿下游連結巡覽。只讀取拓樸，不切換多工器或連線。
- [Microphone boost notification](https://learn.microsoft.com/en-us/windows/win32/api/audioengineextensionapo/ns-audioengineextensionapo-audio_microphone_boost_notification)：增量為獨立 part，使用 dB 範圍及步進值。
- [GetLevelRange](https://learn.microsoft.com/en-us/windows/win32/api/devicetopology/nf-devicetopology-iperchanneldblevel-getlevelrange)：按聲道取得最小、最大與步進值。
- [IPart::GetName](https://learn.microsoft.com/en-us/previous-versions/ms679058%28v%3Dvs.85%29)：取得名稱後須釋放 Windows 配置的字串。

辨識策略：只接受系統 MediaCategories 中增量 GUID 的 Name，或列出的常見中英文增量名稱，並要求可啟用 IAudioVolumeLevel。未找到或有多個候選時報讀無法辨識；不以一般音量範圍推測增量。其他廠商自訂名稱尚未查證。

## 驗證與限制

- 模擬測試涵蓋硬體級距、上下限、多聲道、小數 dB、無效範圍、寫入失敗、實際讀回值、預設裝置變更及模糊候選。
- 使用 comtypes COMObject 實際經 COM 介面測試 dB 方法槽位與浮點陣列傳遞。
- 本機唯讀查證：預設錄音端點為 Loop-back 1/2，拓樸可正常巡覽，未提供增量控制。尚未對具備麥克風增量的實體裝置或 NVDA 執行中的快捷鍵做寫入測試。
- `verify_addon.py` 驗證最終安裝包的 ZIP 簽章、CRC、版本、完整檔案清單、來源一致性及 Python 語法。
