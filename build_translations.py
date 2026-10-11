"""Validate complete catalogs and compile the translations NVDA loads."""
import ast
from pathlib import Path
from string import Formatter

import polib

ROOT = Path(__file__).resolve().parent
LANGUAGES = ("en", "zh_TW")


def source_messages():
    # Read only translation calls, without importing NVDA or touching audio devices.
    messages = set()
    paths = [ROOT / "buildVars.py", *sorted((ROOT / "addon/globalPlugins").rglob("*.py"))]
    for path in paths:
        if "vendor" in path.parts:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_":
                if not node.args or not isinstance(node.args[0], ast.Constant):
                    raise ValueError(f"Translation call must use a literal string: {path}:{node.lineno}")
                messages.add(node.args[0].value)
    return messages


def placeholders(text):
    # Keep format field names and format specifications identical in each language.
    return sorted((field, spec, conversion or "") for _, field, spec, conversion in Formatter().parse(text) if field is not None)


def validated_catalogs():
    messages = source_messages()
    for language in LANGUAGES:
        path = ROOT / "addon/locale" / language / "LC_MESSAGES/nvda.po"
        catalog = polib.pofile(str(path), check_for_duplicates=True)
        if catalog.metadata.get("Language") != language:
            raise ValueError(f"Wrong catalog language: {path}")
        entries = {entry.msgid: entry for entry in catalog if not entry.obsolete}
        if set(entries) != messages:
            raise ValueError(f"Catalog coverage mismatch in {language}: {set(entries) ^ messages}")
        for entry in entries.values():
            if not entry.msgstr or "fuzzy" in entry.flags:
                raise ValueError(f"Unfinished translation in {language}: {entry.msgid}")
            if placeholders(entry.msgid) != placeholders(entry.msgstr):
                raise ValueError(f"Format placeholders differ in {language}: {entry.msgid}")
        yield path, catalog


if __name__ == "__main__":
    for path, catalog in validated_catalogs():
        catalog.save_as_mofile(str(path.with_suffix(".mo")))
        print(f"Compiled {path.parent.parent.name}: {len(catalog)} messages")
