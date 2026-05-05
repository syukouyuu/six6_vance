import logging
import os
import sys
from datetime import date


class _StderrToLogger:
    def __init__(self, logger, original_stream):
        self.logger = logger
        self.original_stream = original_stream
        self._buffer = ""

    def write(self, message):
        self.original_stream.write(message)
        self.original_stream.flush()

        self._buffer += message
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            if line.strip():
                self.logger.error(line.rstrip())

    def flush(self):
        self.original_stream.flush()
        if self._buffer.strip():
            self.logger.error(self._buffer.rstrip())
        self._buffer = ""

    def isatty(self):
        return self.original_stream.isatty()

    @property
    def encoding(self):
        return getattr(self.original_stream, "encoding", None)


def setup_six6_logging(module_name, base_dir):
    """
    Standard logging setup for six6 modules.
    Supports Plan A: dated file logs, stdout mirroring, stderr capture,
    and uncaught exception tracebacks.
    Note: No automatic cleanup is performed; logs are isolated by date.
    """
    log_dir = os.path.join(os.path.abspath(base_dir), "log")
    os.makedirs(log_dir, exist_ok=True)
    
    # Filename format: YYYY-MM-DD_module.log
    log_file = os.path.join(log_dir, f"{date.today()}_{module_name}.log")
    
    formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s', '%Y-%m-%d %H:%M:%S')
    
    # File Handler (Append mode, no rotation management since filename includes date)
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    
    # Stream Handler mirrors logger output to stdout
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Robustness: Clear existing handlers to prevent duplicate logging
    if root_logger.handlers:
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
            
    root_logger.addHandler(file_handler)
    root_logger.addHandler(stream_handler)

    module_logger = logging.getLogger(module_name)
    # Preserve original stderr output while also writing stderr lines to the daily file.
    sys.stderr = _StderrToLogger(module_logger, sys.__stderr__)
    
    # Critical: Capture unhandled exceptions into the log file for VPS troubleshooting
    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        root_logger.error("❌ Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

    sys.excepthook = handle_exception
    
    return module_logger
