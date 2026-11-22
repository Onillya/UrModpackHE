# UrModpackHE — Minecraft Modpack Auto-Translator

A Python utility that automatically scans a Minecraft modpack's `mods/` directory, extracts all mod language files, translates them into Hebrew (`he_il`), and packages everything into a ready-to-use **Minecraft Resource Pack** (`.zip`).

## Features

- **Automatic Mod Scanning**: Iterates through every `.jar` file in your `mods/` folder and extracts `assets/<modid>/lang/<source_lang>.json` files.
- **Minecraft Formatting Protection**: Safely preserves color/formatting codes (`§a`, `§l`, `§r`, etc.), dynamic placeholders (`%s`, `%1$s`, `%d`), and line breaks (`\n`) so translations never break in-game tooltips or UI text.
- **Batch Request Optimization**: Groups strings into character-limited chunks to minimize HTTP requests and avoid Google Translate rate limits.
- **Persistent Local Cache**: Saves progress to `translation_cache.json` after each mod. If the script is interrupted, re-running it resumes right where it left off without re-translating already cached strings.
- **Auto `pack_format` Detection**: Automatically maps your Minecraft version from `.env` to the correct `pack.mcmeta` format version.
- **Zero In-Game Performance Impact**: Outputs a standard Resource Pack compatible with Forge, Fabric, NeoForge, and Quilt.

## Prerequisites

- **Python 3.10+**
- Required Python packages:

```bash
pip install python-dotenv deep-translator