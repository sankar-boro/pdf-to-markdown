import argparse
import sys
import pypdfium2 as pdfium
from pathlib import Path

from src.logger import get_logger, setup_logging, add_logging_args

logger = get_logger()


def _parse_page_range(page_range: str, total: int) -> list[int]:
    """Parse '1-5,8,10-12' into a list of 0-based page indices."""
    indices = []
    for part in page_range.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            indices.extend(range(int(start) - 1, int(end)))
        else:
            indices.append(int(part) - 1)
    valid = [i for i in indices if 0 <= i < total]
    if not valid:
        raise ValueError(f"Page range '{page_range}' produced no valid pages for a {total}-page PDF.")
    return valid


def _check_encrypted(pdf_path: Path) -> bool:
    with open(pdf_path, "rb") as f:
        content = f.read(4096)
    return b"/Encrypt" in content


def split_pdf(
    pdf_path: str,
    output_dir: str,
    page_range: str = None,
    overwrite: bool = False,
) -> list[Path]:
    pdf_path = Path(pdf_path)
    output_dir = Path(output_dir)

    if not pdf_path.exists():
        raise FileNotFoundError(f"File not found: {pdf_path}")
    if pdf_path.stat().st_size == 0:
        raise ValueError(f"PDF is empty: {pdf_path}")
    if _check_encrypted(pdf_path):
        logger.error(f"PDF is encrypted: {pdf_path.name}. Cannot split.")
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    pdf = pdfium.PdfDocument(str(pdf_path))
    total = len(pdf)
    logger.info(f"{pdf_path.name}: {total} pages total.")

    indices = _parse_page_range(page_range, total) if page_range else list(range(total))
    logger.info(f"Splitting {len(indices)} page(s)...")

    page_files = []
    for i in indices:
        out_file = output_dir / f"{pdf_path.stem}_page_{i + 1:04d}.pdf"

        if out_file.exists() and not overwrite:
            logger.debug(f"  Already exists, skipping: {out_file.name}")
            page_files.append(out_file)
            continue

        out_pdf = pdfium.PdfDocument.new()
        out_pdf.import_pages(pdf, pages=[i])
        out_pdf.save(str(out_file))
        out_pdf.close()

        size = out_file.stat().st_size
        logger.debug(f"  Saved: {out_file.name} ({_fmt_size(size)})")
        page_files.append(out_file)

    pdf.close()
    logger.info(f"Done. {len(page_files)} page file(s) written to {output_dir}")
    return page_files


def _fmt_size(nbytes: int) -> str:
    if nbytes < 1024:
        return f"{nbytes} B"
    elif nbytes < 1024 ** 2:
        return f"{nbytes / 1024:.1f} KB"
    return f"{nbytes / 1024 ** 2:.2f} MB"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Split a PDF into individual page PDFs")
    parser.add_argument("--input", required=True, help="Input PDF file")
    parser.add_argument("--output", default="output/pages", help="Output directory")
    parser.add_argument("--page-range", default=None, metavar="RANGE",
                        help="Pages to split, e.g. '1-5,8,10-12'. Default: all pages.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing page PDFs")
    add_logging_args(parser)
    args = parser.parse_args()

    setup_logging(verbose=args.verbose, quiet=args.quiet,
                  log_file=args.log_file)

    split_pdf(args.input, args.output, page_range=args.page_range, overwrite=args.overwrite)
