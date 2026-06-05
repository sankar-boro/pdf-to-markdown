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
    # Paths
    "pdf_path": None,
    "pages_dir": None,
    "markdown_dir": "output",

    # Conversion
    "output_format": "markdown",
    "page_range": None,
    "merge": False,
    "keep_pages": False,
    "overwrite": False,
    "extract_images": True,

    # Reliability
    "retries": 3,
    "cooldown": 30,

    # Watch
    "watch_dir": None,          # Folder to watch for new PDFs (used by watch command)
    "large": False,             # Use large pipeline in watch mode (page-by-page)

    # Logging
    "verbose": False,
    "quiet": False,
    "log_file": None,
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
    """Write a default config.json."""
    config = {
        "_comment": "pdf2md config — CLI arguments override these values",

        "pdf_path": "/path/to/your.pdf",
        "pages_dir": "output/pages",
        "markdown_dir": "output/markdown",
        "watch_dir": "/path/to/watch/folder",
        "large": False,

        "output_format": "markdown",
        "page_range": None,
        "merge": False,
        "keep_pages": False,
        "overwrite": False,
        "extract_images": True,

        "retries": 3,
        "cooldown": 30,

        "log_file": None,
        "verbose": False,
        "quiet": False,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    print(f"Written: {path}")
