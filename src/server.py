"""
server.py — FastAPI HTTP server for PDF-to-markdown conversion.

Usage:
    scripts/run.sh server
    scripts/run.sh server --host 0.0.0.0 --port 8000

Endpoints:
    POST /convert          Upload a PDF, get markdown back
    POST /convert/file     Upload a PDF, save to disk, get path back
    GET  /health           Health check
    GET  /docs             Swagger UI (auto-generated)
"""

import argparse
import shutil
import tempfile
import time
from pathlib import Path

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse

from src.converter import convert_single, PDFError, _get_models
from src.logger import setup_logging, get_logger

logger = get_logger()

app = FastAPI(
    title="pdf2md",
    description="Convert PDF files to Markdown using Marker.",
    version="1.0.0",
)

_startup_time = time.time()


@app.on_event("startup")
async def _load_models():
    logger.info("Pre-loading marker models...")
    _get_models()
    logger.info("Models ready.")


@app.get("/health")
def health():
    return {
        "status": "ok",
        "uptime_seconds": round(time.time() - _startup_time, 1),
    }


@app.post("/convert", response_class=PlainTextResponse, summary="Convert PDF → markdown text")
async def convert_to_text(
    file: UploadFile = File(..., description="PDF file to convert"),
    output_format: str = Form("markdown", description="markdown | html | json"),
    page_range: str = Form(None, description="e.g. '1-5,8' — omit for all pages"),
    extract_images: bool = Form(False, description="Save extracted images to output dir"),
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Uploaded file must be a .pdf")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_pdf = Path(tmpdir) / file.filename
        tmp_out = Path(tmpdir) / "out"

        with open(tmp_pdf, "wb") as f:
            shutil.copyfileobj(file.file, f)

        try:
            result = convert_single(
                str(tmp_pdf),
                str(tmp_out),
                output_format=output_format,
                page_range=page_range or None,
                overwrite=True,
                extract_images=extract_images,
            )
        except PDFError as e:
            raise HTTPException(status_code=422, detail=str(e))
        except Exception as e:
            logger.error(f"Conversion error: {e}")
            raise HTTPException(status_code=500, detail=f"Conversion failed: {e}")

        return result.output_file.read_text(encoding="utf-8")


@app.post("/convert/file", summary="Convert PDF → save to disk, return metadata")
async def convert_to_file(
    file: UploadFile = File(..., description="PDF file to convert"),
    output_dir: str = Form("output", description="Directory to save output"),
    output_format: str = Form("markdown", description="markdown | html | json"),
    page_range: str = Form(None, description="e.g. '1-5,8' — omit for all pages"),
    overwrite: bool = Form(True),
    extract_images: bool = Form(False),
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Uploaded file must be a .pdf")

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    tmp_pdf = out_dir / file.filename
    with open(tmp_pdf, "wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        result = convert_single(
            str(tmp_pdf),
            str(out_dir),
            output_format=output_format,
            page_range=page_range or None,
            overwrite=overwrite,
            extract_images=extract_images,
        )
    except PDFError as e:
        tmp_pdf.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        tmp_pdf.unlink(missing_ok=True)
        logger.error(f"Conversion error: {e}")
        raise HTTPException(status_code=500, detail=f"Conversion failed: {e}")
    finally:
        tmp_pdf.unlink(missing_ok=True)

    return JSONResponse({
        "output_file": str(result.output_file),
        "output_size_bytes": result.output_size,
        "duration_seconds": round(result.duration, 2),
        "images_saved": result.images_saved,
    })


def main():
    parser = argparse.ArgumentParser(description="Run the pdf2md HTTP server")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Port (default: 8000)")
    parser.add_argument("--reload", action="store_true", help="Auto-reload on code changes (dev)")
    parser.add_argument("--workers", type=int, default=1, help="Number of worker processes")
    args = parser.parse_args()

    setup_logging()
    logger.info(f"Starting server at http://{args.host}:{args.port}")
    logger.info(f"Docs at http://{args.host}:{args.port}/docs")

    uvicorn.run(
        "src.server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        workers=args.workers,
    )


if __name__ == "__main__":
    main()
