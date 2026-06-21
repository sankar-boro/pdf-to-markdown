import argparse
import sys

from src.converter import convert_single, convert_batch, PDFError
from src.logger import setup_logging, add_logging_args, get_logger

logger = get_logger()


def main():
    parser = argparse.ArgumentParser(
        description="PDF to Markdown converter using Marker",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --input file.pdf
  python main.py --input file.pdf --output out/ --page-range 1-10
  python main.py --input folder/ --batch --output-format html
  python main.py --input file.pdf --no-overwrite
        """,
    )

    parser.add_argument("--input", required=True, help="Input PDF file or folder (with --batch)")
    parser.add_argument("--output", default="output", help="Output directory (default: output)")
    parser.add_argument("--batch", action="store_true", help="Batch convert all PDFs in a folder")
    parser.add_argument(
        "--output-format",
        choices=["markdown", "html", "json"],
        default="markdown",
        help="Output format (default: markdown)",
    )
    parser.add_argument(
        "--page-range",
        default=None,
        metavar="RANGE",
        help="Pages to convert, e.g. '1-5,8,10-12'. Single file only.",
    )
    parser.add_argument(
        "--no-overwrite",
        action="store_true",
        help="Skip files that already have output",
    )
    parser.add_argument(
        "--no-images",
        action="store_true",
        help="Skip image extraction (images are extracted by default)",
    )
    parser.add_argument(
        "--images-dir",
        default=None,
        metavar="DIR",
        help="Directory to save extracted images (default: <output>/<stem>_images/)",
    )
    parser.add_argument(
        "--image-format",
        choices=["png", "jpeg", "webp"],
        default="png",
        help="Format for extracted images (default: png)",
    )
    add_logging_args(parser)
    args = parser.parse_args()

    setup_logging(
        verbose=args.verbose,
        quiet=args.quiet,
        log_file=args.log_file,
    )

    try:
        if args.batch:
            if args.page_range:
                logger.warning("--page-range is ignored in batch mode")
            convert_batch(
                args.input,
                args.output,
                output_format=args.output_format,
                overwrite=not args.no_overwrite,
                extract_images=not args.no_images,
            )
        else:
            result = convert_single(
                args.input,
                args.output,
                output_format=args.output_format,
                page_range=args.page_range,
                overwrite=not args.no_overwrite,
                extract_images=not args.no_images,
                images_dir=args.images_dir,
                image_format=args.image_format,
            )
            logger.info(f"Converted: {result.output_file}  ({result.duration:.1f}s, {_fmt_size(result.output_size)})")
    except PDFError as e:
        logger.error(str(e))
        sys.exit(1)
    except KeyboardInterrupt:
        logger.warning("Interrupted.")
        sys.exit(130)


def _fmt_size(nbytes: int) -> str:
    if nbytes < 1024:
        return f"{nbytes} B"
    elif nbytes < 1024 ** 2:
        return f"{nbytes / 1024:.1f} KB"
    return f"{nbytes / 1024 ** 2:.2f} MB"


if __name__ == "__main__":
    main()
