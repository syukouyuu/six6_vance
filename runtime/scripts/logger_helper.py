import logging
import os
import sys
from logging.handlers import TimedRotatingFileHandler
from datetime import date

def setup_six6_logging(module_name, base_dir):
    """
    Standard logging setup for six6 modules.
    Supports Plan A: Daily rolling logs + stdout mirroring.
    """
    log_dir = os.path.join(os.path.abspath(base_dir), "log")
    os.makedirs(log_dir, exist_ok=True)
    
    # Filename format: YYYY-MM-DD_module.log
    # Note: TimedRotatingFileHandler will handle the rotation, 
    # but we use the date in the name for immediate clarity as requested in Plan A.
    log_file = os.path.join(log_dir, f"{date.today()}_{module_name}.log")
    
    formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s', '%Y-%m-%d %H:%M:%S')
    
    # File Handler
    # We use backupCount=30 to keep one month of history on the VPS.
    file_handler = TimedRotatingFileHandler(log_file, when="midnight", interval=1, backupCount=30, encoding="utf-8")
    file_handler.setFormatter(formatter)
    
    # Stream Handler (stdout) for compatibility with external redirection (Cron >>)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Avoid duplicate handlers if setup is called multiple times
    if not root_logger.handlers:
        root_logger.addHandler(file_handler)
        root_logger.addHandler(stream_handler)
    
    return logging.getLogger(module_name)
