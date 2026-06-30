"""Logging configuration for AulaForge.

Console output uses Rich for readability; a plain-text file handler is added
whenever an output directory is available, so overnight batch runs leave a
record even though nothing is ever asked interactively.
"""

from __future__ import annotations

import contextlib
import logging
import sys
from pathlib import Path

from rich.logging import RichHandler

_CONSOLE_FORMAT = "%(message)s"
_FILE_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def ensure_utf8_console() -> None:
    """Best-effort: force UTF-8 on stdout/stderr.

    On Windows, the active console codepage can disagree with Python's
    stream encoding, which mangles accented course/lesson names in the
    console (mojibake) even though the underlying files are always written
    as UTF-8 explicitly. This is a no-op when the stream doesn't support
    `reconfigure` (e.g. captured by a test runner) or when reconfiguration
    fails; in that case console output may still be garbled, but it never
    crashes and disk artifacts are unaffected either way.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        with contextlib.suppress(ValueError, OSError):
            reconfigure(encoding="utf-8", errors="replace")


def setup_logging(log_dir: Path | None = None, level: int = logging.INFO) -> logging.Logger:
    """Configure the "aulaforge" logger with a Rich console handler and,
    when `log_dir` is given, a file handler writing to `log_dir/aulaforge.log`.
    """
    ensure_utf8_console()

    logger = logging.getLogger("aulaforge")
    logger.setLevel(level)
    logger.handlers.clear()
    logger.propagate = False

    console_handler = RichHandler(rich_tracebacks=True, show_path=False)
    console_handler.setFormatter(logging.Formatter(_CONSOLE_FORMAT))
    logger.addHandler(console_handler)

    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_dir / "aulaforge.log", encoding="utf-8")
        file_handler.setFormatter(logging.Formatter(_FILE_FORMAT))
        logger.addHandler(file_handler)

    return logger
