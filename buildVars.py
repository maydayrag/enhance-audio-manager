# -*- coding: UTF-8 -*-

"""NVDA 官方附加元件範本所使用的建置中介資料。"""


def _(text):
	# 建置階段尚未啟動 NVDA 翻譯系統，因此只原樣回傳文字。
	return text


addon_info = {
	"addon_name": "audioManager",
	"addon_summary": _("Enhance Audio Manager 音訊管理器"),
	"addon_description": _("以鍵盤管理 Windows 音訊裝置、應用程式音量及 NVDA 輸出裝置。"),
	"addon_version": "2.0.6",
	"addon_author": "圓臉",
	"addon_url": "https://github.com/maydayrag/enhance-audio-manager",
	"addon_sourceURL": "https://github.com/maydayrag/enhance-audio-manager",
	"addon_docFileName": "readme.html",
	"addon_minimumNVDAVersion": "2026.1.1",
	"addon_lastTestedNVDAVersion": "2026.1.1",
	"addon_updateChannel": None,
	"addon_license": "GPL-2.0-or-later",
	"addon_licenseURL": "https://www.gnu.org/licenses/old-licenses/gpl-2.0.html",
}

pythonSources = ["addon/globalPlugins/audioManager/__init__.py", "addon/globalPlugins/_audioManager/*.py"]
i18nSources = pythonSources + ["buildVars.py"]
excludedFiles = ["**/__pycache__/**", "**/*.pyc"]
baseLanguage = "zh_TW"
markdownExtensions = []
brailleTables = {}
symbolDictionaries = {}
