import logging
import sys
from pathlib import Path


def get_logger(name: str = "pdf2md") -> logging.Logger:
    return logging.getLogger(name)


def setup_logging(verbose: bool = False, quiet: bool = False, log_file: Path = None):
    if quiet:
        level = logging.ERROR
    elif verbose:
        level = logging.DEBUG
    else:
        level = logging.INFO

    fmt = logging.Formatter("[%(levelname)s] %(message)s")

    root = logging.getLogger("pdf2md")
    root.setLevel(level)
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(fmt)
    root.addHandler(handler)

    if log_file:
        log_file = Path(log_file)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        root.addHandler(file_handler)

    # Suppress noisy third-party loggers unless in verbose mode
    if not verbose:
        for noisy in ("transformers", "torch", "marker", "surya", "timm"):
            logging.getLogger(noisy).setLevel(logging.ERROR)

    return root


def add_logging_args(parser):
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--verbose", "-v", action="store_true", help="Enable verbose output")
    group.add_argument("--quiet", "-q", action="store_true", help="Suppress all output except errors")
    parser.add_argument("--log-file", default=None, metavar="PATH", help="Write logs to this file")
    return parser
