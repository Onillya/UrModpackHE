import json
import os
import re
import zipfile
from pathlib import Path

import argostranslate.package
import argostranslate.translate
from dotenv import load_dotenv

load_dotenv()

MODS_DIR = os.getenv("MODS_DIR", "./mods")
MC_VERSION = os.getenv("MC_VERSION", "1.20.1").strip()
SOURCE_MC_LANG = os.getenv("SOURCE_LANG", "en_us").strip().lower()
OUTPUT_ZIP = os.getenv("OUTPUT_ZIP", "Modpack_Hebrew_Pack.zip")

CACHE_FILE = "translation_cache.json"
API_TARGET_LANG = "he"
MC_TARGET_LANG = "he_il"

# Maps Minecraft versions to their Resource Pack pack_format
VERSION_TO_PACK_FORMAT = {
    "1.16.5": 6,
    "1.17.1": 7,
    "1.18.2": 8,
    "1.19.2": 9,
    "1.19.3": 12,
    "1.19.4": 13,
    "1.20": 15,
    "1.20.1": 15,
    "1.20.2": 18,
    "1.20.4": 22,
    "1.20.6": 32,
    "1.21": 34,
    "1.21.1": 34,
    "1.21.3": 42,
    "1.21.4": 46,
}

# Matches Minecraft color codes (§a), format specifiers (%s, %1$s, %d), and newlines
PLACEHOLDER_REGEX = re.compile(r"(§[0-9a-fk-or]|%\d*\$?[sdif]|\\n|\n)")


def get_pack_format(version: str) -> int:
    if version in VERSION_TO_PACK_FORMAT:
        return VERSION_TO_PACK_FORMAT[version]
    print(f"[!] Unknown version '{version}', defaulting to pack_format=15.")
    return 15


def load_cache() -> dict[str, str]:
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_cache(cache: dict[str, str]) -> None:
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def protect_placeholders(text: str) -> tuple[str, list[str]]:
    tokens: list[str] = []

    def replacer(match: re.Match) -> str:
        tokens.append(match.group(0))
        return f"[[{len(tokens) - 1}]]"

    return PLACEHOLDER_REGEX.sub(replacer, text), tokens


def restore_placeholders(text: str, tokens: list[str]) -> str:
    for i, token in enumerate(tokens):
        text = re.sub(rf"\[\[\s*{i}\s*\]\]", lambda _: token, text)
    return text


def setup_local_translator(source_lang: str, target_lang: str) -> None:
    """Ensure the required Argos Translate offline model is installed."""
    installed = argostranslate.package.get_installed_packages()
    if any(p.from_code == source_lang and p.to_code == target_lang for p in installed):
        return

    print(f"[*] Downloading offline model ({source_lang} -> {target_lang})...")
    argostranslate.package.update_package_index()
    available = argostranslate.package.get_available_packages()
    pkg = next(
        (p for p in available if p.from_code == source_lang and p.to_code == target_lang),
        None,
    )
    if not pkg:
        raise RuntimeError(f"No offline model found for {source_lang} -> {target_lang}")

    argostranslate.package.install_from_path(pkg.download())
    print("[OK] Offline model installed.")


def extract_lang_files(mods_dir: str, source_mc_lang: str) -> dict[str, dict[str, str]]:
    """Extract assets/<modid>/lang/<source_mc_lang>.json from all .jar files."""
    mods_path = Path(mods_dir)
    if not mods_path.exists():
        raise FileNotFoundError(f"Mods folder not found: '{mods_dir}'. Check your .env file.")

    extracted: dict[str, dict[str, str]] = {}
    source_suffix = f"/lang/{source_mc_lang}.json"
    jar_files = list(mods_path.glob("*.jar"))
    print(f"[*] {len(jar_files)} .jar files found in '{mods_dir}'.")

    for jar_path in jar_files:
        try:
            with zipfile.ZipFile(jar_path, "r") as jar:
                for file_info in jar.namelist():
                    if not (file_info.startswith("assets/") and file_info.endswith(source_suffix)):
                        continue
                    raw_data = jar.read(file_info).decode("utf-8-sig", errors="ignore")
                    try:
                        lang_dict = json.loads(raw_data)
                        if isinstance(lang_dict, dict) and lang_dict:
                            target_path = file_info.replace(
                                f"{source_mc_lang}.json", f"{MC_TARGET_LANG}.json"
                            )
                            extracted.setdefault(target_path, {}).update(lang_dict)
                    except json.JSONDecodeError:
                        print(f"  [!] Invalid JSON ignored: {jar_path.name} -> {file_info}")
        except zipfile.BadZipFile:
            print(f"  [!] Corrupted archive ignored: {jar_path.name}")

    return extracted


def build_resource_pack(
    translated_files: dict[str, dict[str, str]], output_zip: str, pack_format: int
) -> None:
    pack_mcmeta = {
        "pack": {
            "pack_format": pack_format,
            "description": f"Hebrew translation generated (MC {MC_VERSION})",
        }
    }

    with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("pack.mcmeta", json.dumps(pack_mcmeta, ensure_ascii=False, indent=2))
        for file_path, content in translated_files.items():
            zf.writestr(file_path, json.dumps(content, ensure_ascii=False, indent=2))

    print(f"\n[OK] Created Resource Pack: {output_zip} (pack_format: {pack_format})")


def main() -> None:
    pack_format = get_pack_format(MC_VERSION)
    api_source_lang = SOURCE_MC_LANG.split("_")[0]

    print(f"[*] Config: MC {MC_VERSION} (format {pack_format}) | {SOURCE_MC_LANG} -> {MC_TARGET_LANG}")

    setup_local_translator(api_source_lang, API_TARGET_LANG)
    cache = load_cache()
    lang_files = extract_lang_files(MODS_DIR, SOURCE_MC_LANG)
    print(f"[*] {len(lang_files)} lang files found.\n")

    translated_files: dict[str, dict[str, str]] = {}

    for idx, (target_path, entries) in enumerate(lang_files.items(), 1):
        mod_name = target_path.split("/")[1]
        print(f"[{idx}/{len(lang_files)}] Translating '{mod_name}' ({len(entries)} keys)...")

        translated_entries: dict[str, str] = {}

        for key, value in entries.items():
            if not isinstance(value, str) or not value.strip():
                translated_entries[key] = value
                continue

            if value in cache:
                translated_entries[key] = cache[value]
                continue

            protected, tokens = protect_placeholders(value)
            try:
                translated = argostranslate.translate.translate(
                    protected, api_source_lang, API_TARGET_LANG
                )
                restored = restore_placeholders(translated, tokens)
                translated_entries[key] = restored
                cache[value] = restored
            except Exception:
                # Keep original string on failure without polluting the cache
                translated_entries[key] = value

        translated_files[target_path] = translated_entries
        save_cache(cache)

    build_resource_pack(translated_files, OUTPUT_ZIP, pack_format)


if __name__ == "__main__":
    main()