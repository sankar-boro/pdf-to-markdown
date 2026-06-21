"""
convert_large.py — Split a PDF into pages, then convert each page to markdown.

Flow:
  1. Read paths and settings from config.json (CLI args override)
  2. Generate metadata.json in markdown_dir at the start
  3. Split the PDF into individual page PDFs
  4. Load models once
  5. Convert each page — up to 3 attempts per page
     - If all 3 fail: log reason to errors.log, move to next page
     - After each page: wait cooldown seconds before the next
  6. Post-process, optionally merge, finalize metadata.json
"""

import argparse
import json
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import psutil
import pypdfium2 as pdfium
from tqdm import tqdm

from src.split_pdf import split_pdf
from src.config import load_config, merge_config_with_args, write_default_config
from src.converter import convert_single, PDFError, _get_models
from src.logger import setup_logging, add_logging_args, get_logger
from src.postprocess import postprocess_pages
from src.report import RunReport, PageResult

logger = get_logger()

_MEMORY_WARN_GB = 2.0
_MEMORY_ABORT_GB = 0.5


# ── Memory guard ──────────────────────────────────────────────────────────────

def _check_memory():
    mem = psutil.virtual_memory()
    available_gb = mem.available / (1024 ** 3)
    if available_gb < _MEMORY_ABORT_GB:
        logger.error(
            f"Only {available_gb:.1f} GB RAM available. "
            "Free up memory and re-run to resume."
        )
        sys.exit(1)
    if available_gb < _MEMORY_WARN_GB:
        logger.warning(f"Low memory: {available_gb:.1f} GB available.")


# ── State file ────────────────────────────────────────────────────────────────

def _state_path(markdown_dir: Path, pdf_stem: str) -> Path:
    return markdown_dir / f".{pdf_stem}_progress.json"


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


# ── Error log ─────────────────────────────────────────────────────────────────

def _log_error(error_log: Path, page_num: int, page_file: str, attempts: int, error: str):
    error_log.parent.mkdir(parents=True, exist_ok=True)
    with open(error_log, "a", encoding="utf-8") as f:
        f.write("\n" + "=" * 72 + "\n")
        f.write(f"Page {page_num}: {page_file}\n")
        f.write(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Attempts: {attempts}\n")
        f.write(f"Error:\n{error}\n")


# ── Metadata ──────────────────────────────────────────────────────────────────

def _pdf_info(pdf_path: Path) -> dict:
    pdf = pdfium.PdfDocument(str(pdf_path))
    total = len(pdf)
    pdf.close()
    return {
        "name": pdf_path.name,
        "path": str(pdf_path.resolve()),
        "size_bytes": pdf_path.stat().st_size,
        "total_pages": total,
    }


def _init_metadata(pdf_path: Path, pages_dir: Path, markdown_dir: Path, images_dir: Path, cfg: dict) -> dict:
    return {
        "pdf": _pdf_info(pdf_path),
        "run": {
            "started_at": datetime.now(timezone.utc).isoformat(),
            "finished_at": None,
            "duration_seconds": None,
            "config": {k: str(v) if isinstance(v, Path) else v for k, v in cfg.items()},
        },
        "output": {
            "pages_dir":    str(pages_dir),
            "markdown_dir": str(markdown_dir),
            "images_dir":   str(images_dir),
        },
        "summary": {
            "total": 0,
            "succeeded": 0,
            "blank": 0,
            "skipped": 0,
            "failed": 0,
        },
        "pages": [],
    }


def _save_metadata(meta: dict, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)


def _finalize_metadata(meta: dict, results: list[PageResult], start_time: float, path: Path):
    meta["run"]["finished_at"] = datetime.now(timezone.utc).isoformat()
    meta["run"]["duration_seconds"] = round(time.time() - start_time, 1)

    meta["summary"]["total"] = len(results)
    meta["summary"]["succeeded"] = sum(1 for r in results if r.success and not r.skipped and not r.blank)
    meta["summary"]["blank"] = sum(1 for r in results if r.blank)
    meta["summary"]["skipped"] = sum(1 for r in results if r.skipped)
    meta["summary"]["failed"] = sum(1 for r in results if not r.success)

    meta["pages"] = [
        {
            "page": r.page_num,
            "source_pdf": r.source,
            "output_md": r.output.name if r.output else None,
            "status": "skipped" if r.skipped else "blank" if r.blank else "done" if r.success else "failed",
            "duration_seconds": round(r.duration, 2) if r.duration else None,
            "size_bytes": r.output_size if r.output_size else None,
            "error": r.error if r.error else None,
        }
        for r in results
    ]

    _save_metadata(meta, path)


# ── Merge ─────────────────────────────────────────────────────────────────────

def _merge_markdowns(md_files: list[Path], output_file: Path, pdf_name: str):
    toc = [f"# {pdf_name}\n\n## Table of Contents\n"]
    body = []
    for i, md_file in enumerate(sorted(md_files), start=1):
        anchor = f"page-{i}"
        toc.append(f"- [Page {i}](#{anchor})")
        body.append(f'\n\n<a name="{anchor}"></a>\n\n---\n\n## Page {i}\n\n')
        body.append(md_file.read_text(encoding="utf-8").strip())
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(toc))
        f.write("".join(body))
        f.write("\n")
    logger.info(f"Merged → {output_file} ({output_file.stat().st_size / 1024:.1f} KB)")


# ── Cooldown ──────────────────────────────────────────────────────────────────

def _cooldown(seconds: int, current: int, total: int):
    if seconds <= 0 or current >= total:
        return
    logger.info(f"Cooling down for {seconds}s before next page...")
    for remaining in range(seconds, 0, -1):
        print(f"\r  Cooldown: {remaining:3d}s ", end="", flush=True)
        time.sleep(1)
    print()


# ── Core ──────────────────────────────────────────────────────────────────────

def convert_large_pdf(
    pdf_path: Path,
    markdown_dir: Path,
    pages_dir: Path,
    images_dir: Path,
    page_range: Optional[str],
    keep_pages: bool,
    max_attempts: int,
    cooldown: int,
    merge: bool,
    dry_run: bool,
    overwrite: bool,
    extract_images: bool,
    cfg: dict,
):
    markdown_dir.mkdir(parents=True, exist_ok=True)

    metadata_path = markdown_dir / f"{pdf_path.stem}_metadata.json"
    error_log = markdown_dir / f"{pdf_path.stem}_errors.log"

    # ── Generate metadata at the start ───────────────────────────────────────
    meta = _init_metadata(pdf_path, pages_dir, markdown_dir, images_dir, cfg)
    _save_metadata(meta, metadata_path)
    logger.info(f"Metadata: {metadata_path}")

    # ── Step 1: Split ────────────────────────────────────────────────────────
    logger.info(f"Step 1: Splitting {pdf_path.name} into pages...")
    if dry_run:
        page_files = split_pdf(str(pdf_path), str(pages_dir), page_range=page_range, overwrite=False)
        logger.info(f"[dry-run] Would convert {len(page_files)} page(s) → {markdown_dir}")
        return

    page_files = split_pdf(str(pdf_path), str(pages_dir), page_range=page_range, overwrite=False)
    total = len(page_files)
    meta["pdf"]["total_pages"] = total
    _save_metadata(meta, metadata_path)
    logger.info(f"Step 1 done: {total} page(s) ready in {pages_dir}")

    # ── Step 2: Load models once ──────────────────────────────────────────────
    logger.info("Step 2: Loading models (once)...")
    _get_models()

    # ── Step 3: Convert page by page ──────────────────────────────────────────
    logger.info(f"Step 3: Converting {total} page(s) — up to {max_attempts} attempts each, "
                f"{cooldown}s cooldown between pages.")

    state_file = _state_path(markdown_dir, pdf_path.stem)
    state = _load_state(state_file)

    if state:
        done_count = sum(1 for v in state.values() if v == "done")
        logger.info(f"Resuming — {done_count}/{total} pages already done.")

    run_start = time.time()
    report = RunReport(pdf_name=pdf_path.name, total_pages=total)
    converted_md_files: list[Path] = []

    with tqdm(total=total, unit="page", desc=pdf_path.stem, ncols=80) as pbar:
        for idx, page_file in enumerate(page_files, start=1):
            md_file = markdown_dir / (page_file.stem + ".md")
            state_key = page_file.name

            # Resume: skip already-done pages
            if state.get(state_key) == "done" and md_file.exists() and not overwrite:
                report.results.append(PageResult(
                    page_num=idx, source=page_file.name,
                    output=md_file, success=True, skipped=True,
                    output_size=md_file.stat().st_size,
                ))
                converted_md_files.append(md_file)
                pbar.update(1)
                continue

            _check_memory()

            last_error = None
            last_tb = None
            page_start = time.time()

            for attempt in range(1, max_attempts + 1):
                try:
                    result = convert_single(
                        str(page_file),
                        str(markdown_dir),
                        overwrite=True,
                        extract_images=extract_images,
                        images_dir=str(images_dir),
                        image_format=cfg.get("image_format", "png"),
                        run_postprocess=False,
                    )
                    duration = time.time() - page_start
                    if result.blank:
                        logger.info(f"  Page {idx}: blank (no extractable text, skipping retries)")
                    report.results.append(PageResult(
                        page_num=idx, source=page_file.name,
                        output=result.output_file, success=True,
                        blank=result.blank, duration=duration,
                        output_size=result.output_size,
                    ))
                    state[state_key] = "done"
                    _save_state(state_file, state)
                    if not result.blank:
                        converted_md_files.append(result.output_file)
                    last_error = None
                    break
                except Exception as e:
                    last_error = str(e)
                    last_tb = traceback.format_exc()
                    if attempt < max_attempts:
                        logger.warning(
                            f"  Page {idx}: attempt {attempt}/{max_attempts} failed — {e}. Retrying..."
                        )
                        time.sleep(5)

            if last_error:
                logger.error(
                    f"  Page {idx} ({page_file.name}) FAILED after {max_attempts} attempt(s). "
                    f"See {error_log.name}"
                )
                _log_error(error_log, idx, page_file.name, max_attempts, last_tb or last_error)
                state[state_key] = "failed"
                _save_state(state_file, state)
                report.results.append(PageResult(
                    page_num=idx, source=page_file.name,
                    success=False, error=last_error,
                ))

            pbar.update(1)

            # Cooldown between pages (skip after the last one)
            _cooldown(cooldown, idx, total)

    # ── Post-process ──────────────────────────────────────────────────────────
    if converted_md_files:
        logger.info("Post-processing (removing repeated headers/footers)...")
        texts = [f.read_text(encoding="utf-8") for f in converted_md_files]
        cleaned = postprocess_pages(texts)
        for f, text in zip(converted_md_files, cleaned):
            f.write_text(text, encoding="utf-8")

    # ── Merge ─────────────────────────────────────────────────────────────────
    if merge and converted_md_files:
        merged_file = markdown_dir / f"{pdf_path.stem}.md"
        logger.info("Merging pages into single markdown with TOC...")
        _merge_markdowns(converted_md_files, merged_file, pdf_path.stem)
        if not keep_pages:
            for f in converted_md_files:
                f.unlink(missing_ok=True)

    # ── Cleanup split page PDFs ───────────────────────────────────────────────
    if not keep_pages:
        for f in page_files:
            f.unlink(missing_ok=True)
        if pages_dir.exists() and not any(pages_dir.iterdir()):
            pages_dir.rmdir()

    # ── Finalize metadata ─────────────────────────────────────────────────────
    _finalize_metadata(meta, report.results, run_start, metadata_path)
    logger.info(f"Metadata updated: {metadata_path}")

    # ── Report ────────────────────────────────────────────────────────────────
    report.finish()
    print(report.format())

    if not report.failed:
        state_file.unlink(missing_ok=True)
    else:
        logger.warning(f"Error details: {error_log}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Split a PDF into pages then convert each page to markdown.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  scripts/run.sh large                              # uses config.json
  scripts/run.sh large --input big.pdf             # override pdf_path
  scripts/run.sh large --input big.pdf --merge
  scripts/run.sh large --input big.pdf --page-range 1-20
  scripts/run.sh large --dry-run
  scripts/run.sh init-config                       # generate config.json
        """,
    )

    parser.add_argument("--input", default=None, nargs="+",
                        help="Input PDF file(s). Overrides pdf_path in config.json")
    parser.add_argument("--output", default=None,
                        help="Root output directory. Overrides output_dir in config.json. "
                             "Structure: <output>/<stem>/pages|markdown|markdown/images")
    parser.add_argument("--page-range", default=None, metavar="RANGE",
                        help="Only process these pages, e.g. '1-10,15'")
    parser.add_argument("--keep-pages", action="store_true",
                        help="Keep split page PDFs after conversion")
    parser.add_argument("--retries", type=int, default=None,
                        help="Max attempts per page including first try (default: 3)")
    parser.add_argument("--cooldown", type=int, default=None,
                        help="Seconds to wait between pages (default: 30)")
    parser.add_argument("--merge", action="store_true",
                        help="Merge all page markdowns into one file with a TOC")
    parser.add_argument("--overwrite", action="store_true",
                        help="Re-convert pages even if output already exists")
    parser.add_argument("--no-images", action="store_true",
                        help="Skip image extraction (images are extracted by default)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be done without converting")
    parser.add_argument("--config", default=None, metavar="PATH",
                        help="Path to config.json (default: ./config.json)")
    parser.add_argument("--init-config", action="store_true",
                        help="Write a default config.json and exit")
    add_logging_args(parser)
    args = parser.parse_args()

    if args.init_config:
        write_default_config()
        return

    cfg = load_config(args.config)
    cfg = merge_config_with_args(cfg, args)

    setup_logging(
        verbose=cfg.get("verbose", False),
        quiet=cfg.get("quiet", False),
        log_file=cfg.get("log_file"),
    )

    # Resolve input PDFs — CLI --input wins, then config pdf_path
    input_paths = []
    if args.input:
        input_paths = [Path(p) for p in args.input]
    elif cfg.get("pdf_path"):
        input_paths = [Path(cfg["pdf_path"])]
    else:
        parser.error("No input PDF specified. Use --input or set pdf_path in config.json")

    # Resolve root output dir — CLI --output wins, then config output_dir
    output_root = Path(args.output or cfg.get("output_dir") or "output")

    for pdf_path in input_paths:
        if not pdf_path.exists():
            logger.error(f"File not found: {pdf_path}")
            sys.exit(1)

        # All output lives under <output_root>/<stem>/
        pdf_out = output_root / pdf_path.stem
        pages_dir    = pdf_out / "pages"
        markdown_dir = pdf_out / "markdown"

        try:
            convert_large_pdf(
                pdf_path=pdf_path,
                markdown_dir=markdown_dir,
                pages_dir=pages_dir,
                images_dir=markdown_dir / "images",
                page_range=cfg.get("page_range"),
                keep_pages=cfg.get("keep_pages", False),
                max_attempts=cfg.get("retries", 3),
                cooldown=cfg.get("cooldown", 30),
                merge=cfg.get("merge", False),
                dry_run=args.dry_run,
                overwrite=cfg.get("overwrite", False),
                extract_images=not args.no_images,
                cfg=cfg,
            )
        except PDFError as e:
            logger.error(str(e))
            sys.exit(1)
        except KeyboardInterrupt:
            logger.warning("Interrupted. Re-run the same command to resume.")
            sys.exit(130)


if __name__ == "__main__":
    main()
