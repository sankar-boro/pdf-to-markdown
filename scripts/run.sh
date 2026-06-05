#!/bin/bash
set -euo pipefail

# Project root is one level up from scripts/
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$ROOT/venv"

# ── Helpers ───────────────────────────────────────────────────────────────────

usage() {
    cat <<EOF
Usage: $(basename "$0") <command> [options]

Commands:
  convert       Convert a single PDF to markdown
  large         Split a large PDF into pages and convert each (resumable)
  split         Split a PDF into individual page PDFs
  watch         Watch a folder and auto-convert new PDFs
  server        Start the FastAPI HTTP server
  init-config   Write a default config.yaml
  install       Create venv and install dependencies

Options are passed directly to the underlying script.
Run $(basename "$0") <command> --help for full options.

Examples:
  $(basename "$0") install
  $(basename "$0") convert --input file.pdf
  $(basename "$0") convert --input file.pdf --output out/ --page-range 1-10
  $(basename "$0") large   --input big.pdf
  $(basename "$0") large   --input big.pdf --merge
  $(basename "$0") large   --input big.pdf --page-range 1-20 --dry-run
  $(basename "$0") split   --input file.pdf --output out/pages/
  $(basename "$0") watch   --input-dir pdfs/ --output-dir output/
  $(basename "$0") server  --host 0.0.0.0 --port 8000
  $(basename "$0") init-config
EOF
}

log() { echo "[run.sh] $*"; }
die() { echo "[run.sh] ERROR: $*" >&2; exit 1; }

# ── Venv activation ───────────────────────────────────────────────────────────

activate_venv() {
    if [[ ! -d "$VENV" ]]; then
        die "Virtual environment not found at $VENV. Run:  $(basename "$0") install"
    fi
    # shellcheck disable=SC1091
    source "$VENV/bin/activate"
}

# ── Commands ──────────────────────────────────────────────────────────────────

cmd_install() {
    log "Creating virtual environment at $VENV ..."
    python3 -m venv "$VENV"
    # shellcheck disable=SC1091
    source "$VENV/bin/activate"
    log "Installing dependencies..."
    pip install --upgrade pip -q
    pip install -r "$ROOT/requirements.txt"
    log "Done. Activate with:  source venv/bin/activate"
}

cmd_convert() {
    activate_venv
    cd "$ROOT"
    exec python main.py "$@"
}

cmd_large() {
    activate_venv
    cd "$ROOT"
    # Allow optional 'convert' subword: run.sh large convert --input ...
    if [[ "${1:-}" == "convert" ]]; then shift; fi
    exec python -m src.convert_large "$@"
}

cmd_split() {
    activate_venv
    cd "$ROOT"
    exec python -m src.split_pdf "$@"
}

cmd_watch() {
    activate_venv
    cd "$ROOT"
    exec python -m src.watch "$@"
}

cmd_server() {
    activate_venv
    cd "$ROOT"
    exec python -m src.server "$@"
}

cmd_init_config() {
    activate_venv
    cd "$ROOT"
    exec python -m src.convert_large --init-config
}

# ── Dispatch ──────────────────────────────────────────────────────────────────

if [[ $# -eq 0 ]]; then
    usage
    exit 0
fi

COMMAND="$1"
shift

case "$COMMAND" in
    install)      cmd_install "$@" ;;
    convert)      cmd_convert "$@" ;;
    large)        cmd_large "$@" ;;
    split)        cmd_split "$@" ;;
    watch)        cmd_watch "$@" ;;
    server)       cmd_server "$@" ;;
    init-config)  cmd_init_config "$@" ;;
    -h|--help|help) usage ;;
    *)
        echo "[run.sh] Unknown command: $COMMAND"
        echo ""
        usage
        exit 1
        ;;
esac
