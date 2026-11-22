import os
import re
import json
import time
import zipfile
from pathlib import Path
from dotenv import load_dotenv
from deep_translator import GoogleTranslator

# ================= CONFIG (.env) =======================
load_dotenv()
MODS_DIR = os.getenv("MODS_DIR", "./mods")
MC_VERSION = os.getenv("MC_VERSION", "1.20.1").strip()
SOURCE_MC_LANG = os.getenv("SOURCE_LANG", "en_us").strip().lower()
OUTPUT_ZIP = os.getenv("OUTPUT_ZIP", "Modpack_Hebrew_Pack.zip")

CACHE_FILE = "translation_cache.json"
API_TARGET_LANG = "iw"  # hebrew's id for Google Translate
MC_TARGET_LANG = "he_il"  # hebrew's id for Minecraft
BATCH_SIZE = 5
# ========================================================

# Minecraft version -> pack_format (Resource Pack)
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

PLACEHOLDER_REGEX = re.compile(r'(§[0-9a-fk-or]|%\d*\$?[sdif]|\\n|\n)')


def get_pack_format(version: str) -> int:
    if version in VERSION_TO_PACK_FORMAT:
        return VERSION_TO_PACK_FORMAT[version]
    print(f"[!] Version '{version}' unknown in table, using pack_format=15 by default.")
    return 15


def get_api_source_lang(mc_lang: str) -> str:
    # Convert a Minecraft format (ex: en_us, fr_fr) to Google Translate format (ex: en, fr)
    return mc_lang.split("_")[0]


def load_cache() -> dict:
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_cache(cache: dict):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def protect_placeholders(text: str):
    tokens = []

    def replacer(match):
        tokens.append(match.group(0))
        return f"[[{len(tokens) - 1}]]"

    return PLACEHOLDER_REGEX.sub(replacer, text), tokens


def restore_placeholders(text: str, tokens: list) -> str:
    for i, token in enumerate(tokens):
        text = re.sub(rf'\[\[\s*{i}\s*\]\]', lambda _: token, text)
    return text


MAX_CHARS_PER_REQUEST = 4000  # Limite Google Translate : 5000 caractères max


def translate_batch_api(texts: list[str], translator: GoogleTranslator) -> list[str | None]:
    # Sends the whole set in one HTTP request
    joined_text = "\n".join(texts)

    for attempt in range(3):
        try:
            translated_joined = translator.translate(joined_text)
            if translated_joined:
                lines = translated_joined.split("\n")
                # If google kept the same lines amount
                if len(lines) == len(texts):
                    return lines
            break
        except Exception as e:
            wait = 2 * (attempt + 1)
            print(f"  [!] Rate limit / Error ({e}). Time out {wait}s...")
            time.sleep(wait)

    # Fallback line by line with a time outif the set fails
    results = []
    for t in texts:
        try:
            results.append(translator.translate(t))
            time.sleep(0.5)
        except Exception:
            results.append(None)  # None = failure, won't be in cache
    return results


def extract_lang_files(mods_dir: str, source_mc_lang: str) -> dict:
    extracted = {}
    mods_path = Path(mods_dir)

    if not mods_path.exists():
        raise FileNotFoundError(f"The program was unable to find the '{mods_dir}' folder. Check your .env file.")

    source_filename = f"/lang/{source_mc_lang}.json"
    jar_files = list(mods_path.glob("*.jar"))
    print(f"[*] {len(jar_files)} files .jar found in '{mods_dir}'.")

    for jar_path in jar_files:
        try:
            with zipfile.ZipFile(jar_path, "r") as jar:
                for file_info in jar.namelist():
                    if file_info.startswith("assets/") and file_info.endswith(source_filename):
                        raw_data = jar.read(file_info).decode("utf-8-sig", errors="ignore")
                        try:
                            lang_dict = json.loads(raw_data)
                            if isinstance(lang_dict, dict) and lang_dict:
                                target_path = file_info.replace(
                                    f"{source_mc_lang}.json", f"{MC_TARGET_LANG}.json"
                                )
                                extracted.setdefault(target_path, {}).update(lang_dict)
                        except json.JSONDecodeError:
                            print(f"  [!] Invalid JSON ignored in {jar_path.name} -> {file_info}")
        except zipfile.BadZipFile:
            print(f"  [!] Ignored corrumpted archive : {jar_path.name}")

    return extracted


def build_resource_pack(translated_files: dict, output_zip: str, pack_format: int):
    pack_mcmeta = {
        "pack": {
            "pack_format": pack_format,
            "description": f"Hebrew translation generated (MC {MC_VERSION})"
        }
    }

    with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("pack.mcmeta", json.dumps(pack_mcmeta, ensure_ascii=False, indent=2))
        for file_path, content in translated_files.items():
            zf.writestr(file_path, json.dumps(content, ensure_ascii=False, indent=2))

    print(f"\n[OK] Created Resource Pack : {output_zip} (pack_format: {pack_format})")


def main():
    pack_format = get_pack_format(MC_VERSION)
    api_source_lang = get_api_source_lang(SOURCE_MC_LANG)

    print(f"[*] Config : MC {MC_VERSION} (format {pack_format}) | {SOURCE_MC_LANG} -> {MC_TARGET_LANG}")

    cache = load_cache()
    translator = GoogleTranslator(source=api_source_lang, target=API_TARGET_LANG)

    lang_files = extract_lang_files(MODS_DIR, SOURCE_MC_LANG)
    print(f"[*] {len(lang_files)} total lang files found.\n")

    translated_files = {}

    for idx, (target_path, entries) in enumerate(lang_files.items(), 1):
        mod_name = target_path.split("/")[1]
        print(f"[{idx}/{len(lang_files)}] Treating '{mod_name}' ({len(entries)} keys)...")

        translated_entries = {}
        to_translate = []

        for key, value in entries.items():
            if not isinstance(value, str) or not value.strip():
                translated_entries[key] = value
                continue

            if value in cache:
                translated_entries[key] = cache[value]
            else:
                protected, tokens = protect_placeholders(value)
                to_translate.append((key, value, protected, tokens))

        current_batch = []
        current_chars = 0

        def process_batch(batch_items):
            texts_to_send = [item[2] for item in batch_items]
            translated_batch = translate_batch_api(texts_to_send, translator)

            for (key, orig_val, _, tokens), trans_val in zip(batch_items, translated_batch):
                if trans_val:
                    restored = restore_placeholders(trans_val, tokens)
                    translated_entries[key] = restored
                    cache[orig_val] = restored
                else:
                    translated_entries[key] = orig_val
            time.sleep(1.5)

        for item in to_translate:
            text_len = len(item[2]) + 1
            if current_batch and (current_chars + text_len > MAX_CHARS_PER_REQUEST):
                process_batch(current_batch)
                current_batch = []
                current_chars = 0
            current_batch.append(item)
            current_chars += text_len

        if current_batch:
            process_batch(current_batch)

        translated_files[target_path] = translated_entries
        save_cache(cache)

    build_resource_pack(translated_files, OUTPUT_ZIP, pack_format)


if __name__ == "__main__":
    main()
