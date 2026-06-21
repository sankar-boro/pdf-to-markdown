"""
watch.py — Watch a folder and auto-convert any new PDF that appears.

Settings are read from config.json:
  watch_dir    — folder to watch for new PDFs
  markdown_dir — where to write converted markdown
  large        — use page-by-page pipeline (true/false)
  merge, retries, cooldown, extract_images — passed to the large pipeline
"""

import argparse
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileMovedEvent
from watchdog.observers import Observer

from src.config import load_config
from src.converter import convert_single, PDFError, _get_models
from src.logger import setup_logging, add_logging_args, get_logger

logger = get_logger()


def _is_pdf(path: str) -> bool:
    return Path(path).suffix.lower() == ".pdf"


def _wait_until_stable(path: Path, interval: float = 0.5, retries: int = 6) -> bool:
    """Wait until a file stops growing (i.e. is fully written)."""
    prev_size = -1
    for _ in range(retries):
        time.sleep(interval)
        try:
            size = path.stat().st_size
        except FileNotFoundError:
            return False
        if size == prev_size and size > 0:
            return True
        prev_size = size
    return False


class PDFHandler(FileSystemEventHandler):
    def __init__(self, output_root: Path, use_large: bool, cfg: dict):
        self.output_root = output_root
        self.use_large = use_large
        self.cfg = cfg
        self._seen: set[str] = set()

    def _handle(self, path: str):
        if not _is_pdf(path):
            return
        if path in self._seen:
            return
        self._seen.add(path)

        pdf = Path(path)
        logger.info(f"Detected new PDF: {pdf.name}")

        if not _wait_until_stable(pdf):
            logger.warning(f"File does not appear stable, skipping: {pdf.name}")
            return

        # Per-PDF output dirs follow the same structure as the large command
        pdf_out      = self.output_root / pdf.stem
        pages_dir    = pdf_out / "pages"
        markdown_dir = pdf_out / "markdown"
        images_dir   = pdf_out / "markdown" / "images"

        if self.use_large:
            from src.convert_large import convert_large_pdf
            try:
                convert_large_pdf(
                    pdf_path=pdf,
                    markdown_dir=markdown_dir,
                    pages_dir=pages_dir,
                    images_dir=images_dir,
                    page_range=self.cfg.get("page_range"),
                    keep_pages=self.cfg.get("keep_pages", False),
                    max_attempts=self.cfg.get("retries", 3),
                    cooldown=self.cfg.get("cooldown", 30),
                    merge=self.cfg.get("merge", False),
                    dry_run=False,
                    overwrite=self.cfg.get("overwrite", False),
                    extract_images=self.cfg.get("extract_images", True),
                    cfg=self.cfg,
                )
            except Exception as e:
                logger.error(f"Failed (large): {pdf.name} — {e}")
        else:
            try:
                result = convert_single(
                    str(pdf), str(markdown_dir),
                    extract_images=self.cfg.get("extract_images", True),
                    images_dir=str(images_dir),
                    image_format=self.cfg.get("image_format", "png"),
                )
                logger.info(f"Converted: {result.output_file}")
            except PDFError as e:
                logger.error(f"Skipped: {e}")
            except Exception as e:
                logger.error(f"Failed: {pdf.name} — {e}")

    def on_created(self, event):
        if isinstance(event, FileCreatedEvent):
            self._handle(event.src_path)

    def on_moved(self, event):
        if isinstance(event, FileMovedEvent):
            self._handle(event.dest_path)


def main():
    parser = argparse.ArgumentParser(
        description="Watch a folder and auto-convert new PDFs to markdown. "
                    "All settings are read from config.json.",
    )
    parser.add_argument("--config", default=None, metavar="PATH",
                        help="Path to config.json (default: ./config.json)")
    add_logging_args(parser)
    args = parser.parse_args()

    cfg = load_config(args.config)
    setup_logging(
        verbose=cfg.get("verbose", False) or args.verbose,
        quiet=cfg.get("quiet", False) or args.quiet,
        log_file=args.log_file or cfg.get("log_file"),
    )

    watch_dir = cfg.get("watch_dir")
    if not watch_dir:
        logger.error("'watch_dir' is not set in config.json. Run: ./scripts/run.sh init-config")
        raise SystemExit(1)

    input_dir   = Path(watch_dir)
    output_root = Path(cfg.get("output_dir") or "output")

    if not input_dir.is_dir():
        logger.error(f"watch_dir does not exist: {input_dir}")
        raise SystemExit(1)

    output_root.mkdir(parents=True, exist_ok=True)

    use_large = cfg.get("large", False)

    logger.info("Pre-loading models...")
    _get_models()
    logger.info(f"Watching {input_dir} → {output_root}/<stem>/markdown. Press Ctrl+C to stop.")

    handler = PDFHandler(output_root, use_large=use_large, cfg=cfg)
    observer = Observer()
    observer.schedule(handler, str(input_dir), recursive=False)

    observer.start()

    try:
        while observer.is_alive():
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Stopping watcher...")
    finally:
        observer.stop()
        observer.join()


if __name__ == "__main__":
    main()
