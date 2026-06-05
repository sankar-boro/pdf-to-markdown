import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from marker.config.parser import ConfigParser
from marker.models import create_model_dict
from marker.output import text_from_rendered, convert_if_not_rgb

from src.logger import get_logger
from src.postprocess import postprocess

logger = get_logger()

_models = None
_models_lock = threading.Lock()


def _get_models() -> dict:
    global _models
    if _models is None:
        with _models_lock:
            if _models is None:
                logger.debug("Loading marker models (first run only)...")
                _models = create_model_dict()
                logger.debug("Models loaded.")
    return _models


@dataclass
class ConvertResult:
    output_file: Path
    page_count: int
    duration: float
    output_size: int
    images_saved: int = 0


class PDFError(Exception):
    pass


def validate_pdf(pdf_path: Path):
    if not pdf_path.exists():
        raise PDFError(f"File not found: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise PDFError(f"Not a PDF file: {pdf_path}")
    if pdf_path.stat().st_size == 0:
        raise PDFError(f"File is empty: {pdf_path}")
    with open(pdf_path, "rb") as f:
        header = f.read(8)
        if not header.startswith(b"%PDF"):
            raise PDFError(f"Not a valid PDF (bad header): {pdf_path}")
    with open(pdf_path, "rb") as f:
        snippet = f.read(4096)
        if b"/Encrypt" in snippet:
            raise PDFError(f"PDF is encrypted and cannot be converted: {pdf_path}")


def _validate_output(output_file: Path, min_bytes: int = 32):
    """Raise if the output file is missing or suspiciously small."""
    if not output_file.exists():
        raise PDFError(f"Conversion produced no output file: {output_file}")
    if output_file.stat().st_size < min_bytes:
        raise PDFError(
            f"Output file is suspiciously small ({output_file.stat().st_size} bytes): {output_file}"
        )


def convert_single(
    pdf_path: str,
    output_dir: str,
    output_format: str = "markdown",
    page_range: Optional[str] = None,
    overwrite: bool = True,
    extract_images: bool = True,
    run_postprocess: bool = True,
    output_stem: Optional[str] = None,
) -> ConvertResult:
    pdf_path = Path(pdf_path)
    output_dir = Path(output_dir)

    validate_pdf(pdf_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    ext = "md" if output_format == "markdown" else output_format
    stem = output_stem if output_stem else pdf_path.stem
    output_file = output_dir / f"{stem}.{ext}"

    if not overwrite and output_file.exists():
        _validate_output(output_file)
        logger.debug(f"Skipping (already exists): {output_file.name}")
        return ConvertResult(
            output_file=output_file,
            page_count=0,
            duration=0.0,
            output_size=output_file.stat().st_size,
        )

    options: dict = {"output_format": output_format}
    if page_range:
        options["page_range"] = page_range
    if not extract_images:
        options["disable_image_extraction"] = True

    config_parser = ConfigParser(options)
    converter_cls = config_parser.get_converter_cls()
    converter = converter_cls(
        config=config_parser.generate_config_dict(),
        artifact_dict=_get_models(),
        processor_list=config_parser.get_processors(),
        renderer=config_parser.get_renderer(),
        llm_service=config_parser.get_llm_service(),
    )

    start = time.time()
    rendered = converter(str(pdf_path))
    duration = time.time() - start

    text, ext_actual, images = text_from_rendered(rendered)

    if run_postprocess and output_format == "markdown":
        text = postprocess(text)

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(text)

    _validate_output(output_file)

    # Save extracted images next to the markdown
    images_saved = 0
    if extract_images and images:
        img_dir = output_dir / f"{pdf_path.stem}_images"
        img_dir.mkdir(parents=True, exist_ok=True)
        for img_name, img in images.items():
            img = convert_if_not_rgb(img)
            img.save(str(img_dir / img_name))
            images_saved += 1
        logger.debug(f"Saved {images_saved} image(s) to {img_dir}")

    return ConvertResult(
        output_file=output_file,
        page_count=1,
        duration=duration,
        output_size=output_file.stat().st_size,
        images_saved=images_saved,
    )


def convert_batch(
    input_dir: str,
    output_dir: str,
    output_format: str = "markdown",
    overwrite: bool = True,
    extract_images: bool = True,
):
    input_dir = Path(input_dir)
    if not input_dir.is_dir():
        raise PDFError(f"Not a directory: {input_dir}")

    pdfs = sorted(input_dir.glob("*.pdf"))
    if not pdfs:
        logger.warning(f"No PDF files found in {input_dir}")
        return

    logger.info(f"Found {len(pdfs)} PDF(s) in {input_dir}")
    for pdf in pdfs:
        logger.info(f"Converting: {pdf.name}")
        try:
            result = convert_single(
                str(pdf), output_dir,
                output_format=output_format,
                overwrite=overwrite,
                extract_images=extract_images,
            )
            logger.info(f"  Saved: {result.output_file} ({result.duration:.1f}s)")
        except PDFError as e:
            logger.error(f"  Skipped: {e}")
        except Exception as e:
            logger.error(f"  Failed: {pdf.name} — {e}")
