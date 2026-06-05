#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

source "$ROOT/venv/bin/activate"
cd "$ROOT"

python -m src.convert_large --input /home/sankar/Desktop/Books/ai_book.pdf --output output/ai_book/
