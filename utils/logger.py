"""Logging utilities for console and per-PDB file logs."""

import logging
from pathlib import Path
from typing import Optional


class PipelineLogger:
    """Provide unified logging with optional per-task log files."""

    def __init__(self, level: str = "INFO"):
        self.logger = logging.getLogger("production_pipeline")
        self.logger.handlers.clear()
        self.logger.setLevel(getattr(logging, level.upper(), logging.INFO))
        self.logger.propagate = False
        self._file_handler: Optional[logging.Handler] = None

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        self.logger.addHandler(console_handler)

    def set_pdb_log_file(self, log_path: str):
        """Attach a file handler for the current PDB run."""
        self.clear_pdb_log_file()
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_path, mode="w", encoding="utf-8")
        file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        self._file_handler = file_handler
        self.logger.addHandler(file_handler)

    def clear_pdb_log_file(self):
        """Detach and close the active per-PDB log file handler."""
        if self._file_handler is not None:
            self.logger.removeHandler(self._file_handler)
            self._file_handler.close()
            self._file_handler = None

    def info(self, message):
        self.logger.info(message)

    def success(self, message):
        self.logger.info(f"\033[92m{message}\033[0m")

    def warning(self, message):
        self.logger.warning(message)

    def error(self, message):
        self.logger.error(f"\033[91m{message}\033[0m")
