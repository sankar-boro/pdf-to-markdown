# pdf2md

Convert PDF files to Markdown using [Marker](https://github.com/VikParuchuri/marker).

Handles small and very large PDFs. Splits large PDFs page by page, converts each page individually with automatic resume on crash, retries on failure, cooldown between pages, and generates a full metadata report.

---

## Requirements

- Python 3.12+
- Linux / macOS

---

## Installation

```bash
git clone <repo>
cd loony-pdf-to-markdown

# Create venv and install all dependencies
./scripts/run.sh install
```

---

## Project Structure

```
loony-pdf-to-markdown/
├── main.py                   # Single PDF or batch conversion
├── config.json               # Your settings (generate with init-config)
├── requirements.txt
├── pyproject.toml
│
├── scripts/
│   ├── run.sh                # Main entry point for all commands
│   └── convert_ai.sh         # Example script for a specific PDF
│
└── src/
    ├── convert_large.py      # Large PDF pipeline (split → convert → report)
    ├── split_pdf.py          # Split a PDF into individual page PDFs
    ├── watch.py              # Watch a folder, auto-convert new PDFs
    ├── server.py             # FastAPI HTTP server
    ├── converter.py          # Marker conversion wrapper
    ├── config.py             # JSON config loader
    ├── postprocess.py        # Markdown cleanup (headers, ligatures, blank lines)
    ├── logger.py             # Centralized logging
    └── report.py             # Run report (timing, success/fail counts)
```

---

## Quick Start

```bash
# 1. Generate config.json
./scripts/run.sh init-config

# 2. Edit config.json — set pdf_path, pages_dir, markdown_dir

# 3. Convert a large PDF page by page
./scripts/run.sh large

# 4. Or convert a single small PDF directly
./scripts/run.sh convert --input file.pdf --output output/
```

---

## Configuration

All commands read settings from `config.json`. Generate a default one:

```bash
./scripts/run.sh init-config
```

This writes `config.json`:

```json
{
  "pdf_path":     "/path/to/your.pdf",
  "pages_dir":    "output/pages",
  "markdown_dir": "output/markdown",
  "watch_dir":    "/path/to/watch/folder",
  "large":        false,

  "output_format":  "markdown",
  "page_range":     null,
  "merge":          false,
  "keep_pages":     false,
  "overwrite":      false,
  "extract_images": true,

  "retries":  3,
  "cooldown": 30,

  "log_file": null,
  "verbose":  false,
  "quiet":    false
}
```

### Config reference

| Key | Used by | Description |
|---|---|---|
| `pdf_path` | `large`, `split` | Path to the PDF to process. |
| `pages_dir` | `large`, `split` | Where to write the split page PDFs. |
| `markdown_dir` | `large`, `watch` | Where to write the output markdown files. |
| `watch_dir` | `watch` | Folder to monitor for new PDFs. |
| `large` | `watch` | `true` = use page-by-page pipeline for every detected PDF. |
| `output_format` | `large`, `convert` | `markdown`, `html`, or `json`. |
| `page_range` | `large`, `split` | Pages to process, e.g. `"1-10,15"`. `null` = all pages. |
| `merge` | `large`, `watch` | Merge all per-page markdowns into one file with a table of contents. |
| `keep_pages` | `large`, `watch` | Keep the split page PDFs after conversion finishes. |
| `overwrite` | `large`, `split` | Re-process pages/files that already have output. |
| `extract_images` | `large`, `convert`, `watch` | Save images extracted from the PDF alongside the markdown. |
| `retries` | `large`, `watch` | Max attempts per page before logging the failure and moving on. |
| `cooldown` | `large`, `watch` | Seconds to pause between page conversions. Set `0` to disable. |
| `log_file` | all | Write logs to this file in addition to the terminal. `null` = terminal only. |
| `verbose` | all | Show debug-level output. |
| `quiet` | all | Suppress everything except errors. |

---

## Commands

All commands run through `scripts/run.sh`:

```
./scripts/run.sh <command> [options]
```

| Command | Description |
|---|---|
| `install` | Create virtualenv and install dependencies |
| `init-config` | Write a default `config.json` |
| `convert` | Convert a single PDF or a batch folder (full CLI control) |
| `large` | Split a large PDF page by page, convert each, resume on crash |
| `split` | Split a PDF into individual page PDFs only (config-driven) |
| `watch` | Watch a folder and auto-convert any new PDFs (config-driven) |
| `server` | Start the FastAPI HTTP server |

---

### `convert` — Single file or batch

Full CLI control. Does not read paths from `config.json`.

```bash
# Convert a single PDF
./scripts/run.sh convert --input file.pdf

# Save to a specific directory
./scripts/run.sh convert --input file.pdf --output out/

# Convert only pages 1–10 and page 15
./scripts/run.sh convert --input file.pdf --page-range 1-10,15

# Convert all PDFs in a folder
./scripts/run.sh convert --input folder/ --batch

# Output as HTML instead of markdown
./scripts/run.sh convert --input file.pdf --output-format html

# Skip files that are already converted
./scripts/run.sh convert --input file.pdf --no-overwrite

# Skip image extraction
./scripts/run.sh convert --input file.pdf --no-images
```

---

### `large` — Large PDF (split → convert per page → resume)

Best for large PDFs that crash or run out of memory when converted all at once. Reads `pdf_path`, `pages_dir`, and `markdown_dir` from `config.json`. CLI flags override config.

```bash
# Use pdf_path, pages_dir, markdown_dir from config.json
./scripts/run.sh large

# Override the input PDF
./scripts/run.sh large --input big.pdf

# Preview what would happen without converting anything
./scripts/run.sh large --dry-run

# Only convert pages 1–20
./scripts/run.sh large --page-range 1-20

# Merge all pages into one markdown file with a table of contents
./scripts/run.sh large --merge

# Change retry attempts and cooldown
./scripts/run.sh large --retries 5 --cooldown 60

# Keep the split page PDFs after conversion
./scripts/run.sh large --keep-pages

# Skip image extraction
./scripts/run.sh large --no-images
```

**Resume after crash:** re-run the exact same command. Already-converted pages are detected and skipped automatically.

**Outputs written to `markdown_dir`:**

| File | Description |
|---|---|
| `<stem>_page_NNNN.md` | One markdown file per page |
| `<stem>_metadata.json` | Full conversion metadata (written at start, updated at end) |
| `<stem>_errors.log` | Details of every failed page (only created if there are failures) |
| `<stem>.md` | Merged file with TOC (only when `merge: true`) |

---

### `split` — Split PDF into page PDFs only

Reads all settings from `config.json`. No path arguments accepted.

**Required config keys:**

```json
{
  "pdf_path":   "/path/to/your.pdf",
  "pages_dir":  "output/pages",
  "page_range": null,
  "overwrite":  false
}
```

```bash
./scripts/run.sh split

# Use a different config file
./scripts/run.sh split --config /path/to/other-config.json

# Show debug output
./scripts/run.sh split --verbose
```

Output files are zero-padded: `<stem>_page_0001.pdf`, `<stem>_page_0002.pdf`, …

---

### `watch` — Auto-convert new PDFs in a folder

Reads all settings from `config.json`. No path arguments accepted. Waits for each file to finish writing before converting.

**Required config keys:**

```json
{
  "watch_dir":    "/path/to/incoming/pdfs",
  "markdown_dir": "output/markdown",
  "large":        false,
  "merge":        false,
  "extract_images": true,
  "retries":      3,
  "cooldown":     30
}
```

```bash
./scripts/run.sh watch

# Use a different config file
./scripts/run.sh watch --config /path/to/other-config.json

# Show debug output
./scripts/run.sh watch --verbose
```

Set `"large": true` in `config.json` to run each detected PDF through the page-by-page pipeline instead of the single-pass converter.

Press `Ctrl+C` to stop.

---

### `server` — HTTP API

```bash
# Start on localhost:8000
./scripts/run.sh server

# Expose on all interfaces
./scripts/run.sh server --host 0.0.0.0 --port 8000
```

**Endpoints:**

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check and uptime |
| `POST` | `/convert` | Upload PDF → returns markdown text |
| `POST` | `/convert/file` | Upload PDF → saves to disk, returns metadata |
| `GET` | `/docs` | Swagger UI |

**Example with curl:**

```bash
# Convert and get markdown back directly
curl -X POST http://localhost:8000/convert \
  -F "file=@document.pdf" \
  -F "output_format=markdown"

# Convert and save to disk
curl -X POST http://localhost:8000/convert/file \
  -F "file=@document.pdf" \
  -F "output_dir=output/"
```

---

## Logging Options

Available on all commands:

| Flag | Description |
|---|---|
| `--config PATH` | Use a different config file instead of `./config.json` |
| `--verbose` / `-v` | Show debug output (overrides `verbose` in config) |
| `--quiet` / `-q` | Suppress everything except errors (overrides `quiet` in config) |
| `--log-file PATH` | Write logs to a file (overrides `log_file` in config) |

---

## Metadata File

Every `large` run writes `<stem>_metadata.json` to `markdown_dir` at the **start** of the run and finalizes it when done.

```json
{
  "pdf": {
    "name": "document.pdf",
    "path": "/absolute/path/to/document.pdf",
    "size_bytes": 8421740,
    "total_pages": 49
  },
  "run": {
    "started_at": "2026-06-05T10:00:00+00:00",
    "finished_at": "2026-06-05T11:23:45+00:00",
    "duration_seconds": 5025.3,
    "config": { "..." }
  },
  "output": {
    "pages_dir": "output/pages/document",
    "markdown_dir": "output/markdown"
  },
  "summary": {
    "total": 49,
    "succeeded": 47,
    "skipped": 0,
    "failed": 2
  },
  "pages": [
    {
      "page": 1,
      "source_pdf": "document_page_0001.pdf",
      "output_md": "document_page_0001.md",
      "status": "done",
      "duration_seconds": 18.4,
      "size_bytes": 3210,
      "error": null
    }
  ]
}
```

---

## Tips

- **Large PDFs crashing?** Use `./scripts/run.sh large`. It converts one page at a time and picks up where it left off if interrupted.
- **PC overheating?** Increase `cooldown` in `config.json` (e.g. `60` for a one-minute break between pages).
- **Pages failing?** Increase `retries` in `config.json`. Failures are logged to `<stem>_errors.log` and conversion continues to the next page.
- **Want one output file?** Set `"merge": true` in `config.json` or pass `--merge` to `large`.
- **Watching a drop folder?** Set `"watch_dir"` and `"large": true` in `config.json`, then run `./scripts/run.sh watch`.
- **Want HTML or JSON?** Pass `--output-format html` or `--output-format json` to `convert`, or set `"output_format"` in `config.json` for `large`.
- **Multiple config files?** Use `--config path/to/config.json` on any command to switch between projects.
