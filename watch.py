"""
watch.py — Watch a folder and auto-convert any new PDF that appears.

Usage:
    python watch.py --input-dir pdfs/ --output-dir output/
    python watch.py --input-dir pdfs/ --output-dir output/ --large --chunk-size 5
"""

import argparse
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileMovedEvent
from watchdog.observers import Observer

from src.config import load_config, merge_config_with_args
from src.converter import convert_single, PDFError
from src.logger import setup_logging, add_logging_args, get_logger, get_logger
from src.converter import _get_models

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
    def __init__(self, output_dir: Path, use_large: bool, large_kwargs: dict):
        self.output_dir = output_dir
        self.use_large = use_large
        self.large_kwargs = large_kwargs
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

        if self.use_large:
            # Import here to avoid circular issues with module-level setup
            from convert_large import convert_large_pdf
            try:
                convert_large_pdf(
                    pdf_path=pdf,
                    output_dir=self.output_dir,
                    **self.large_kwargs,
                )
            except Exception as e:
                logger.error(f"Failed (large): {pdf.name} — {e}")
        else:
            try:
                result = convert_single(str(pdf), str(self.output_dir))
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
        description="Watch a folder and auto-convert new PDFs to markdown.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python watch.py --input-dir pdfs/ --output-dir output/
  python watch.py --input-dir pdfs/ --output-dir output/ --large --chunk-size 5 --merge
        """,
    )
    parser.add_argument("--input-dir", required=True, help="Folder to watch for new PDFs")
    parser.add_argument("--output-dir", default="output", help="Where to write markdown files")
    parser.add_argument("--large", action="store_true",
                        help="Use chunk-based conversion (for large PDFs)")
    parser.add_argument("--chunk-size", type=int, default=10,
                        help="Pages per chunk when --large is set (default: 10)")
    parser.add_argument("--merge", action="store_true",
                        help="Merge per-chunk markdowns into one file (with --large)")
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--extract-images", action="store_true")
    parser.add_argument("--config", default=None, metavar="PATH")
    add_logging_args(parser)
    args = parser.parse_args()

    cfg = load_config(args.config)
    cfg = merge_config_with_args(cfg, args)

    setup_logging(
        verbose=cfg.get("verbose", False),
        quiet=cfg.get("quiet", False),
        log_file=cfg.get("log_file"),
    )

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)

    if not input_dir.is_dir():
        logger.error(f"Input directory does not exist: {input_dir}")
        raise SystemExit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    # Pre-load models so first conversion is fast
    logger.info("Pre-loading models...")
    _get_models()
    logger.info(f"Watching {input_dir} for new PDFs. Press Ctrl+C to stop.")

    large_kwargs = dict(
        chunk_size=args.chunk_size,
        page_range=None,
        keep_chunks=False,
        retries=args.retries,
        merge=args.merge,
        dry_run=False,
        overwrite=False,
        extract_images=args.extract_images,
        report_file=None,
    )

    handler = PDFHandler(output_dir, use_large=args.large, large_kwargs=large_kwargs)
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
