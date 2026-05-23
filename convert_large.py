"""
convert_large.py — Convert large PDFs by processing them in page chunks.

Instead of splitting to single-page PDFs and spawning a subprocess per page,
this script passes page ranges directly to marker on the original PDF.
Models load once in-process. Crashes are resumable via a state file.
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Optional

import psutil
import pypdfium2 as pdfium
from tqdm import tqdm

from src.config import load_config, merge_config_with_args, write_default_config
from src.converter import convert_single, PDFError, _get_models, validate_pdf
from src.logger import setup_logging, add_logging_args, get_logger
from src.postprocess import postprocess_pages
from src.report import RunReport, PageResult

logger = get_logger()

# ── Memory guard ─────────────────────────────────────────────────────────────

_MEMORY_WARN_GB = 2.0
_MEMORY_ABORT_GB = 0.5


def _check_memory():
    mem = psutil.virtual_memory()
    available_gb = mem.available / (1024 ** 3)
    if available_gb < _MEMORY_ABORT_GB:
        logger.error(
            f"Only {available_gb:.1f} GB RAM available — aborting to prevent OOM crash. "
            f"Free up memory or use a smaller --chunk-size."
        )
        sys.exit(1)
    if available_gb < _MEMORY_WARN_GB:
        logger.warning(f"Low memory: {available_gb:.1f} GB available. Consider reducing --chunk-size.")


# ── State file ────────────────────────────────────────────────────────────────

def _state_path(output_dir: Path, pdf_stem: str) -> Path:
    return output_dir / f".{pdf_stem}_progress.json"


def _load_state(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    return {}


def _save_state(path: Path, state: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2))


# ── Page range helpers ────────────────────────────────────────────────────────

def _parse_user_range(page_range: str, total: int) -> list[int]:
    """Parse '1-5,8,10-12' into sorted 0-based indices, clamped to [0, total)."""
    indices = []
    for part in page_range.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            indices.extend(range(int(a) - 1, int(b)))
        else:
            indices.append(int(part) - 1)
    return sorted(set(i for i in indices if 0 <= i < total))


def _chunk_indices(indices: list[int], size: int) -> list[list[int]]:
    """Split a list of page indices into chunks of `size`."""
    return [indices[i: i + size] for i in range(0, len(indices), size)]


def _marker_range_str(indices: list[int]) -> str:
    """Convert 0-based indices to the comma-separated string marker expects."""
    return ",".join(str(i) for i in indices)


# ── Merge helpers ─────────────────────────────────────────────────────────────

def _merge_markdowns(chunk_files: list[Path], output_file: Path, pdf_name: str):
    toc = [f"# {pdf_name}\n\n## Table of Contents\n"]
    body = []

    for i, md_file in enumerate(sorted(chunk_files), start=1):
        label = f"Chunk {i}"
        anchor = f"chunk-{i}"
        toc.append(f"- [{label}](#{anchor})")
        body.append(f'\n\n<a name="{anchor}"></a>\n\n---\n\n## {label}\n\n')
        body.append(md_file.read_text(encoding="utf-8").strip())

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(toc))
        f.write("".join(body))
        f.write("\n")

    size_kb = output_file.stat().st_size / 1024
    logger.info(f"Merged → {output_file} ({size_kb:.1f} KB)")


# ── Core conversion ───────────────────────────────────────────────────────────

def convert_large_pdf(
    pdf_path: Path,
    output_dir: Path,
    chunk_size: int,
    page_range: Optional[str],
    keep_chunks: bool,
    retries: int,
    merge: bool,
    dry_run: bool,
    overwrite: bool,
    extract_images: bool,
    report_file: Optional[Path],
):
    validate_pdf(pdf_path)

    pdf = pdfium.PdfDocument(str(pdf_path))
    total_pages = len(pdf)
    pdf.close()

    # Resolve which pages to process
    all_indices = (
        _parse_user_range(page_range, total_pages)
        if page_range
        else list(range(total_pages))
    )
    chunks = _chunk_indices(all_indices, chunk_size)
    total_chunks = len(chunks)

    logger.info(
        f"{pdf_path.name}: {total_pages} pages, "
        f"{len(all_indices)} to convert, "
        f"{total_chunks} chunk(s) of ≤{chunk_size}"
    )

    if dry_run:
        for i, chunk in enumerate(chunks, 1):
            rng = f"{chunk[0]+1}-{chunk[-1]+1}"
            logger.info(f"  [dry-run] Chunk {i}/{total_chunks}: pages {rng}")
        return

    # Warm up models once before the loop
    _check_memory()
    logger.info("Loading models (once)...")
    _get_models()

    output_dir.mkdir(parents=True, exist_ok=True)
    state_file = _state_path(output_dir, pdf_path.stem)
    state = _load_state(state_file)
    report = RunReport(pdf_name=pdf_path.name, total_pages=total_chunks)
    chunk_md_files: list[Path] = []

    with tqdm(total=total_chunks, unit="chunk", desc=pdf_path.stem, ncols=80) as pbar:
        for chunk_idx, page_indices in enumerate(chunks, start=1):
            chunk_label = f"{pdf_path.stem}_chunk_{chunk_idx:04d}"
            md_file = output_dir / f"{chunk_label}.md"
            state_key = chunk_label

            # Resume: skip already-done chunks
            if state.get(state_key) == "done" and md_file.exists() and not overwrite:
                logger.debug(f"  Skipping (done): {chunk_label}")
                report.results.append(PageResult(
                    page_num=chunk_idx, source=chunk_label,
                    output=md_file, success=True, skipped=True,
                    output_size=md_file.stat().st_size,
                ))
                chunk_md_files.append(md_file)
                pbar.update(1)
                continue

            _check_memory()

            marker_range = _marker_range_str(page_indices)
            rng_label = f"pages {page_indices[0]+1}-{page_indices[-1]+1}"

            last_error = None
            chunk_start = time.time()

            for attempt in range(1, retries + 2):
                try:
                    result = convert_single(
                        str(pdf_path),
                        str(output_dir),
                        page_range=marker_range,
                        overwrite=True,
                        extract_images=extract_images,
                        run_postprocess=False,  # batch postprocess below
                    )
                    # Rename the output to our chunk filename
                    default_out = output_dir / f"{pdf_path.stem}.md"
                    if default_out.exists() and default_out != md_file:
                        default_out.rename(md_file)

                    duration = time.time() - chunk_start
                    report.results.append(PageResult(
                        page_num=chunk_idx, source=chunk_label,
                        output=md_file, success=True,
                        duration=duration, output_size=md_file.stat().st_size,
                    ))
                    state[state_key] = "done"
                    _save_state(state_file, state)
                    chunk_md_files.append(md_file)
                    last_error = None
                    break
                except Exception as e:
                    last_error = str(e)
                    if attempt <= retries:
                        logger.warning(f"  Chunk {chunk_idx} attempt {attempt} failed: {e}. Retrying...")
                        time.sleep(2 ** attempt)

            if last_error:
                logger.error(f"  Chunk {chunk_idx} ({rng_label}) FAILED: {last_error}")
                state[state_key] = "failed"
                _save_state(state_file, state)
                report.results.append(PageResult(
                    page_num=chunk_idx, source=chunk_label,
                    success=False, error=last_error,
                ))

            pbar.set_postfix_str(rng_label)
            pbar.update(1)

    # Cross-chunk post-processing (header/footer deduplication)
    if chunk_md_files:
        logger.info("Post-processing chunks...")
        texts = [f.read_text(encoding="utf-8") for f in chunk_md_files]
        cleaned = postprocess_pages(texts)
        for f, text in zip(chunk_md_files, cleaned):
            f.write_text(text, encoding="utf-8")

    # Merge into single file
    if merge and chunk_md_files:
        merged_file = output_dir / f"{pdf_path.stem}.md"
        logger.info("Merging chunks...")
        _merge_markdowns(chunk_md_files, merged_file, pdf_path.stem)

    # Cleanup chunk files if merged
    if merge and not keep_chunks:
        for f in chunk_md_files:
            f.unlink(missing_ok=True)

    report.finish()
    print(report.format())

    if report_file:
        report.save(Path(report_file))
        logger.info(f"Report saved: {report_file}")

    # Remove state file on fully clean run
    if not report.failed:
        state_file.unlink(missing_ok=True)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Convert large PDF(s) to markdown via chunk-based processing.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python convert_large.py --input big.pdf
  python convert_large.py --input a.pdf b.pdf --merge --output out/
  python convert_large.py --input big.pdf --page-range 1-50 --chunk-size 5
  python convert_large.py --input big.pdf --dry-run --verbose
  python convert_large.py --init-config          # write a default config.yaml
        """,
    )

    parser.add_argument("--input", nargs="+", help="Input PDF file(s)")
    parser.add_argument("--output", default=None, help="Output directory")
    parser.add_argument("--chunk-size", type=int, default=None,
                        help="Pages per chunk (default: 10)")
    parser.add_argument("--page-range", default=None, metavar="RANGE",
                        help="Only process these pages, e.g. '1-20,25'")
    parser.add_argument("--keep-chunks", action="store_true",
                        help="Keep per-chunk markdown files when --merge is used")
    parser.add_argument("--retries", type=int, default=None,
                        help="Retry failed chunks N times (default: 2)")
    parser.add_argument("--merge", action="store_true",
                        help="Merge all chunk markdowns into one file with a TOC")
    parser.add_argument("--overwrite", action="store_true",
                        help="Re-convert chunks even if output already exists")
    parser.add_argument("--extract-images", action="store_true",
                        help="Save images extracted from PDF alongside markdown")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be done without converting anything")
    parser.add_argument("--report", default=None, metavar="PATH",
                        help="Save run report to this file")
    parser.add_argument("--config", default=None, metavar="PATH",
                        help="Path to config.yaml (default: ./config.yaml if it exists)")
    parser.add_argument("--init-config", action="store_true",
                        help="Write a default config.yaml and exit")
    add_logging_args(parser)
    args = parser.parse_args()

    if args.init_config:
        write_default_config()
        print("Written: config.yaml")
        return

    if not args.input:
        parser.error("--input is required")

    cfg = load_config(args.config)
    cfg = merge_config_with_args(cfg, args)

    setup_logging(
        verbose=cfg.get("verbose", False),
        quiet=cfg.get("quiet", False),
        log_file=cfg.get("log_file"),
    )

    output_dir = Path(cfg["output"])

    for input_path in args.input:
        pdf_path = Path(input_path)
        if not pdf_path.exists():
            logger.error(f"File not found: {pdf_path}")
            sys.exit(1)

        try:
            convert_large_pdf(
                pdf_path=pdf_path,
                output_dir=output_dir,
                chunk_size=cfg.get("chunk_size", 10),
                page_range=cfg.get("page_range"),
                keep_chunks=cfg.get("keep_pages", False),
                retries=cfg.get("retries", 2),
                merge=cfg.get("merge", False),
                dry_run=args.dry_run,
                overwrite=cfg.get("overwrite", False),
                extract_images=cfg.get("extract_images", False),
                report_file=cfg.get("report"),
            )
        except PDFError as e:
            logger.error(str(e))
            sys.exit(1)
        except KeyboardInterrupt:
            logger.warning("Interrupted. Re-run the same command to resume.")
            sys.exit(130)


if __name__ == "__main__":
    main()
