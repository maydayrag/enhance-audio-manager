"""Check the deliverable and microphone behavior without changing real devices."""
import ast
from pathlib import Path
import sys
import unittest
import zipfile

ROOT = Path(__file__).parent
SOURCE = ROOT / "addon"
PACKAGE = ROOT / "dist/enhanceAudioManager-2.0.6.nvda-addon"


def verify_package(path):
    assert path.read_bytes()[:4] == b"PK\x03\x04"
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None
        assert b'version = "2.0.6"' in archive.read("manifest.ini")
        assert b'name = "audioManager"' in archive.read("manifest.ini")
        assert 'summary = "Enhance Audio Manager 音訊管理器"' in archive.read("manifest.ini").decode("utf-8")
        assert "globalPlugins/audioManager/__init__.py" in archive.namelist()
        assert "globalPlugins/_audioManager/microphoneBoost.py" in archive.namelist()
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
    tree = ast.parse((SOURCE / "globalPlugins/audioManager/__init__.py").read_text(encoding="utf-8"))
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
    assert bindings["kb:control+shift+numpad2"] == "script_defaultMicrophoneBoostDown"
    assert bindings["kb:control+shift+numpad8"] == "script_defaultMicrophoneBoostUp"


if __name__ == "__main__":
    verify_behavior()
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    if not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful():
        raise SystemExit(1)
    verify_package(Path(sys.argv[1]) if len(sys.argv) > 1 else PACKAGE)
    print("PASS: microphone behavior, gestures, ZIP integrity, version, syntax and source equality")
