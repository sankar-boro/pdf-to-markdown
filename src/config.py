"""
Config file support. Loads settings from config.yaml (or a custom path),
merges with CLI args (CLI always wins).

Example config.yaml:
    output: output/
    output_format: markdown
    retries: 3
    merge: true
    keep_pages: false
    chunk_size: 10
    verbose: false
"""

from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_PATH = Path("config.yaml")

DEFAULTS = {
    "output": "output",
    "output_format": "markdown",
    "retries": 2,
    "merge": False,
    "keep_pages": False,
    "chunk_size": 10,
    "overwrite": False,
    "verbose": False,
    "quiet": False,
    "extract_images": False,
    "page_range": None,
    "log_file": None,
    "report": None,
}


def load_config(config_path: Path = None) -> dict[str, Any]:
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return {**DEFAULTS, **data}
    return dict(DEFAULTS)


def merge_config_with_args(config: dict, args) -> dict:
    """
    Merge loaded config with parsed argparse namespace.
    Explicit CLI values override config file values.
    argparse sets unspecified flags to their default (False/None),
    so we only override when the CLI value differs from the argparse default.
    """
    merged = dict(config)
    args_dict = vars(args)

    for key, value in args_dict.items():
        # Always take CLI value if it's explicitly non-default
        if value is not None and value is not False:
            merged[key] = value
        elif key not in merged:
            merged[key] = value

    return merged


def write_default_config(path: Path = DEFAULT_CONFIG_PATH):
    """Write a commented default config.yaml for the user to customize."""
    content = """\
# pdf2md configuration file
# CLI arguments override these values when specified.

# Output directory for converted markdown files
output: output

# Output format: markdown, html, json
output_format: markdown

# Pages to process per chunk when using convert_large.py (0 = one page at a time)
chunk_size: 10

# Retry failed pages this many times
retries: 2

# Merge all per-page markdowns into one file with a TOC
merge: false

# Keep split page PDFs after conversion
keep_pages: false

# Re-convert pages even if output already exists
overwrite: false

# Extract images from PDFs alongside markdown
extract_images: false

# Write logs to this file (null = no log file)
log_file: null

# Save run report to this file (null = no report file)
report: null
"""
    path.write_text(content, encoding="utf-8")
