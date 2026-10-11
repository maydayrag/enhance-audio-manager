# -*- coding: UTF-8 -*-

"""NVDA 官方附加元件範本所使用的建置中介資料。"""


def _(text):
	# 建置階段尚未啟動 NVDA 翻譯系統，因此只原樣回傳文字。
	return text


addon_info = {
	"addon_name": "enhanceAudioManager",
	"addon_summary": _("Enhance Audio Manager"),
	"addon_description": _("Manage Windows audio devices, application volume, and NVDA output devices from the keyboard."),
	"addon_version": "1.0",
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

pythonSources = ["addon/globalPlugins/enhanceAudioManager/__init__.py", "addon/globalPlugins/_enhanceAudioManager/*.py"]
i18nSources = pythonSources + ["buildVars.py"]
excludedFiles = ["**/__pycache__/**", "**/*.pyc"]
baseLanguage = "en"
markdownExtensions = []
brailleTables = {}
symbolDictionaries = {}
