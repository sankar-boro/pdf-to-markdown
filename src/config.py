"""
Config file support. Loads settings from config.json (or a custom path).
CLI arguments always override config file values.

Run `scripts/run.sh init-config` to generate a default config.json.
"""

import json
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_PATH = Path("config.json")

DEFAULTS: dict[str, Any] = {
    # ── Paths ──────────────────────────────────────────────────────────────────
    "pdf_path":   None,         # Input PDF (used by large, split)
    "output_dir": "output",     # Root output folder.
                                # large/split produce: <output_dir>/<stem>/pages/
                                #                      <output_dir>/<stem>/markdown/
                                #                      <output_dir>/<stem>/markdown/images/

    # ── Watch ──────────────────────────────────────────────────────────────────
    "watch_dir": None,          # Folder to monitor for new PDFs (watch command)
    "large": False,             # Use page-by-page pipeline in watch mode

    # ── Output ─────────────────────────────────────────────────────────────────
    "output_format": "markdown",  # markdown | html | json
    "page_range": None,           # e.g. "1-10,15" — null means all pages
    "merge": False,               # Merge per-page markdowns into one file with TOC
    "keep_pages": False,          # Keep split page PDFs after conversion
    "overwrite": False,           # Re-convert pages that already have output

    # ── Images ─────────────────────────────────────────────────────────────────
    "extract_images": True,     # Save images found in the PDF
    "image_format": "png",      # Image format: png | jpeg | webp

    # ── Reliability ────────────────────────────────────────────────────────────
    "retries": 3,               # Max attempts per page before logging failure and moving on
    "cooldown": 30,             # Seconds to pause between pages (0 = disabled)

    # ── Logging ────────────────────────────────────────────────────────────────
    "log_file": None,           # Write logs here in addition to terminal (null = terminal only)
    "verbose": False,           # Show debug-level output
    "quiet": False,             # Suppress everything except errors
}


def load_config(config_path: Path = None) -> dict[str, Any]:
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {**DEFAULTS, **data}
    return dict(DEFAULTS)


def merge_config_with_args(config: dict, args) -> dict:
    """CLI values override config. Only override when CLI value is explicitly set."""
    merged = dict(config)
    for key, value in vars(args).items():
        if value is not None and value is not False:
            merged[key] = value
        elif key not in merged:
            merged[key] = value
    return merged


def write_default_config(path: Path = DEFAULT_CONFIG_PATH):
    """Write a default config.json with all available settings."""
    config = {
        "_comment": "pdf2md config — edit these values, then run the desired command",

        "_section_paths": "── Paths ──────────────────────────────────────────",
        "pdf_path":   "/path/to/your.pdf",
        "output_dir": "output",

        "_section_watch": "── Watch ──────────────────────────────────────────",
        "watch_dir":  "/path/to/incoming/pdfs",
        "large":      False,

        "_section_output": "── Output ─────────────────────────────────────────",
        "output_format": "markdown",
        "page_range":  None,
        "merge":       False,
        "keep_pages":  False,
        "overwrite":   False,

        "_section_images": "── Images ─────────────────────────────────────────",
        "extract_images": True,
        "image_format":  "png",

        "_section_reliability": "── Reliability ────────────────────────────────",
        "retries":  3,
        "cooldown": 30,

        "_section_logging": "── Logging ────────────────────────────────────────",
        "log_file": None,
        "verbose":  False,
        "quiet":    False,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    print(f"Written: {path}")
