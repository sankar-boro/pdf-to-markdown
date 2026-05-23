"""
Post-processing pipeline for marker-generated markdown.

Fixes common artifacts:
- Repeated page headers/footers (lines appearing on most pages)
- Excessive blank lines (collapses 3+ consecutive to 2)
- Trailing whitespace
- Garbled unicode ligatures (ﬁ -> fi, etc.)
"""

import re
from collections import Counter
from pathlib import Path
from typing import List

from src.logger import get_logger

logger = get_logger()

# Common ligature replacements marker sometimes mis-encodes
_LIGATURES = {
    "ﬀ": "ff",
    "ﬁ": "fi",
    "ﬂ": "fl",
    "ﬃ": "ffi",
    "ﬄ": "ffl",
    "ﬅ": "st",
    "ﬆ": "st",
}


def _fix_ligatures(text: str) -> str:
    for lig, repl in _LIGATURES.items():
        text = text.replace(lig, repl)
    return text


def _collapse_blank_lines(text: str) -> str:
    # Replace 3+ consecutive blank lines with exactly 2
    return re.sub(r"\n{4,}", "\n\n\n", text)


def _strip_trailing_whitespace(text: str) -> str:
    lines = [line.rstrip() for line in text.splitlines()]
    return "\n".join(lines)


def _detect_repeated_lines(pages: List[str], threshold: float = 0.6) -> set[str]:
    """
    Find lines that appear in more than `threshold` fraction of pages.
    These are likely headers/footers injected by the PDF on every page.
    Only considers short lines (< 120 chars) to avoid matching real content.
    """
    if len(pages) < 3:
        return set()

    line_counts: Counter = Counter()
    for page_text in pages:
        seen_on_this_page = set()
        for line in page_text.splitlines():
            stripped = line.strip()
            if stripped and len(stripped) < 120:
                if stripped not in seen_on_this_page:
                    line_counts[stripped] += 1
                    seen_on_this_page.add(stripped)

    min_pages = max(2, int(len(pages) * threshold))
    return {line for line, count in line_counts.items() if count >= min_pages}


def _remove_repeated_lines(text: str, repeated: set[str]) -> str:
    if not repeated:
        return text
    lines = []
    for line in text.splitlines():
        if line.strip() not in repeated:
            lines.append(line)
    return "\n".join(lines)


def postprocess(text: str) -> str:
    """Apply all post-processing steps to a single markdown string."""
    text = _fix_ligatures(text)
    text = _strip_trailing_whitespace(text)
    text = _collapse_blank_lines(text)
    return text.strip() + "\n"


def postprocess_pages(page_texts: List[str]) -> List[str]:
    """
    Post-process a list of per-page markdown strings together,
    so cross-page repeated header/footer detection can run.
    """
    repeated = _detect_repeated_lines(page_texts)
    if repeated:
        logger.debug(f"Removing {len(repeated)} repeated header/footer line(s).")

    result = []
    for text in page_texts:
        text = _remove_repeated_lines(text, repeated)
        text = postprocess(text)
        result.append(text)
    return result


def postprocess_file(path: Path) -> int:
    """Post-process a markdown file in-place. Returns bytes saved."""
    path = Path(path)
    original = path.read_text(encoding="utf-8")
    processed = postprocess(original)
    saved = len(original.encode()) - len(processed.encode())
    if original != processed:
        path.write_text(processed, encoding="utf-8")
        logger.debug(f"Post-processed {path.name} (saved {saved} bytes)")
    return max(saved, 0)
