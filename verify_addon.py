"""Check the deliverable and microphone behavior without changing real devices."""
import ast
import gettext
import io
from pathlib import Path
import sys
import unittest
import zipfile
from build_translations import validated_catalogs

ROOT = Path(__file__).parent
SOURCE = ROOT / "addon"
PACKAGE = ROOT / "dist/enhanceAudioManager-1.1.nvda-addon"


def verify_package(path):
    assert path.read_bytes()[:4] == b"PK\x03\x04"
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None
        assert b'version = "1.1"' in archive.read("manifest.ini")
        assert b'lastTestedNVDAVersion = "2026.2"' in archive.read("manifest.ini")
        assert b'name = "enhanceAudioManager"' in archive.read("manifest.ini")
        assert b'summary = "Enhance Audio Manager"' in archive.read("manifest.ini")
        assert "globalPlugins/enhanceAudioManager/__init__.py" in archive.namelist()
        assert "globalPlugins/_enhanceAudioManager/microphoneBoost.py" in archive.namelist()
        # Check translations as gettext will load them, including the actual packaged bytes.
        for po_path, catalog in validated_catalogs():
            mo_name = po_path.with_suffix(".mo").relative_to(SOURCE).as_posix()
            mo_data = archive.read(mo_name)
            assert mo_data == catalog.to_binary(), mo_name
            translation = gettext.GNUTranslations(io.BytesIO(mo_data))
            for entry in catalog:
                assert translation.gettext(entry.msgid) == entry.msgstr, (mo_name, entry.msgid)
            language = po_path.parent.parent.name
            assert f"doc/{language}/readme.html" in archive.namelist()
            assert f"locale/{language}/manifest.ini" in archive.namelist()
        assert not any(n.startswith(("globalPlugins/audioManager/", "globalPlugins/_audioManager/", "globalPlugins/vendor/")) for n in archive.namelist())
        expected = {p.relative_to(SOURCE).as_posix() for p in SOURCE.rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix not in (".pyc", ".pyo")}
        assert {n for n in archive.namelist() if not n.endswith("/")} == expected
        for name in archive.namelist():
            assert "__pycache__" not in name and not name.endswith((".pyc", ".pyo"))
            if name.endswith("/"):
                continue
            assert archive.read(name) == (SOURCE / name).read_bytes(), name
            if name.endswith(".py"):
                compile(archive.read(name), name, "exec")


def verify_behavior():
    tree = ast.parse((SOURCE / "globalPlugins/enhanceAudioManager/__init__.py").read_text(encoding="utf-8"))
    plugin = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "GlobalPlugin")
    bindings = {}
    for node in plugin.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        for decorator in node.decorator_list:
            for keyword in decorator.keywords:
                if keyword.arg == "gestures":
                    for gesture in ast.literal_eval(keyword.value):
                        assert gesture not in bindings
                        bindings[gesture] = node.name
    assert bindings["kb(desktop):control+windows+numpad2"] == "script_defaultMicrophoneBoostDown"
    assert bindings["kb(desktop):control+windows+numpad8"] == "script_defaultMicrophoneBoostUp"
    assert bindings["kb(laptop):control+windows+downarrow"] == "script_defaultMicrophoneBoostDown"
    assert bindings["kb(laptop):control+windows+uparrow"] == "script_defaultMicrophoneBoostUp"
    assert bindings["kb:control+windows+alt+numpadminus"] == "script_resetSessions"
    assert bindings["kb(laptop):control+windows+alt+backspace"] == "script_resetSessions"


if __name__ == "__main__":
    verify_behavior()
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    if not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful():
        raise SystemExit(1)
    verify_package(Path(sys.argv[1]) if len(sys.argv) > 1 else PACKAGE)
    print("PASS: microphone behavior, gestures, bilingual catalogs and docs, ZIP integrity, version, syntax and source equality")
